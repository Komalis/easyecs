from hashlib import md5
import json
import os
import subprocess
import time
import boto3
import signal
from watchdog.observers import Observer
from easyecs.command.event.synchronize_event_handler import (
    SynchronizeEventHandler,
    SynchronizeSFTPEventHandler,
)
from easyecs.helpers.color import Color
from easyecs.helpers.common import generate_random_port, is_port_in_use
from easyecs.helpers.loader import Loader

from easyecs.helpers.signal import override_sigint

port_forward_pids = []
threads = []
event_handlers = []
popen_procs_port_forward = []
popen_procs_exec_command = []


def create_port_forwards(ecs_manifest, aws_region, aws_account, parsed_containers):
    containers = ecs_manifest.task_definition.containers
    for container in containers:
        container_name = container.name
        container_ports = container.port_forward
        if ecs_manifest.copy_method == "sftp":
            container_ports.append(
                f"{container.sftp_config.port}:{container.sftp_config.port}"
            )
        for container_port in container_ports:
            from_port = container_port.split(":")[0]
            to_port = container_port.split(":")[1]
            loader = Loader(
                f"Creating port forward on {container_name} container from"
                f" {from_port} to {to_port}:",
                f"Creating port forward on {container_name} container from"
                f" {from_port} to {to_port}: \u2705",
                f"Creating port forward on {container_name} container from"
                f" {from_port} to {to_port}: \u274c",
                0.05,
            )
            loader.start()
            if not is_port_in_use(int(from_port)):
                port_forward(
                    parsed_containers,
                    container_name,
                    to_port,
                    from_port,
                    aws_region,
                    aws_account,
                )
                loader.stop()
            else:
                loader.stop_error()
                print(f"{Color.RED}Port {from_port} is already in use!{Color.END}")


def port_forward(
    parsed_containers,
    container_name,
    port_number,
    local_port_number,
    aws_region,
    aws_account,
):
    container = parsed_containers.get(container_name, None)
    if container:
        target = container["ssm_target"]
        client = boto3.client("ssm")
        ssm_response = client.start_session(
            Target=target,
            DocumentName="AWS-StartPortForwardingSessionToRemoteHost",
            Parameters={
                "host": ["localhost"],
                "portNumber": [port_number],
                "localPortNumber": [local_port_number],
            },
        )
        # It has to be done like that, in a new session.
        # Otherwise a CTRL+C would kill all port forwards.
        ssm_cmd = generate_ssm_cmd(ssm_response, aws_region, aws_account, target)
        process = subprocess.Popen(
            ssm_cmd,
            start_new_session=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
        )
        popen_procs_port_forward.append(process)


def run_sync_thread(parsed_containers, ecs_manifest):
    containers = ecs_manifest.task_definition.containers
    for container in containers:
        if len(container.volumes) > 0:
            observer = Observer()
            container_name = container.name
            for volume in container.volumes:
                md5_volume = md5(volume.encode("utf-8")).hexdigest()
                port = parsed_containers[container_name].get(
                    f"netcat_port_{md5_volume}", None
                )
                _from, _ = volume.split(":")
                event_handler = SynchronizeEventHandler(
                    volume, port, container.volumes_excludes
                )
                event_handlers.append(event_handler)
                observer.schedule(event_handler, _from, recursive=True)
            observer.daemon = True
            observer.start()
            threads.append(observer)


def run_sftp_sync_thread(ecs_manifest, aws_region, aws_account, parsed_containers):
    containers = ecs_manifest.task_definition.containers
    for container in containers:
        container_name = container.name
        port = container.sftp_config.port
        username = container.sftp_config.user
        password = container.sftp_config.password
        target = parsed_containers.get(container_name)["ssm_target"]
        if len(container.volumes) > 0:
            observer = Observer()
            for volume in container.volumes:
                _from, _ = volume.split(":")
                event_handler = SynchronizeSFTPEventHandler(
                    target,
                    aws_region,
                    aws_account,
                    volume,
                    container.volumes_excludes,
                    port,
                    username,
                    password,
                )
                event_handlers.append(event_handler)
                observer.schedule(event_handler, _from, recursive=True)
            observer.daemon = True
            observer.start()
            threads.append(observer)


def execute_command(ecs_manifest, parsed_containers, aws_region, aws_account):
    containers = ecs_manifest.task_definition.containers
    catchable_sigs = set(signal.Signals) - {signal.SIGKILL, signal.SIGSTOP}
    ssm_client = boto3.client("ssm")
    found_tty = False
    tty_cmd = ""
    for container in containers:
        command = container.command
        tty = container.tty
        if command and tty:
            tty = container.tty
            container_name = container.name
            container_command = container.command
            target = parsed_containers.get(container_name)["ssm_target"]
            parameters_nc_server = {"command": [container_command]}
            ssm_container = ssm_client.start_session(
                Target=target,
                DocumentName="AWS-StartInteractiveCommand",
                Parameters=parameters_nc_server,
            )
            cmd_container = [
                "session-manager-plugin",
                json.dumps(ssm_container),
                aws_region,
                "StartSession",
                aws_account,
                json.dumps(dict(Target=target)),
                "https://ssm.eu-west-1.amazonaws.com",
            ]
            if tty:
                found_tty = True
                tty_cmd = cmd_container
            else:
                proc_nc_server = subprocess.Popen(
                    cmd_container,
                    stdin=subprocess.PIPE,
                    start_new_session=True,
                )
                popen_procs_exec_command.append(proc_nc_server)
    if found_tty:
        for sig in catchable_sigs:
            signal.signal(sig, override_sigint)
        proc_nc_server = subprocess.Popen(tty_cmd)
        while True:
            if not proc_nc_server.poll():
                proc_nc_server.wait()
                break
            time.sleep(0.1)
    return found_tty


def generate_ssm_cmd(ssm_nc_server, aws_region, aws_account, target):
    return [
        "session-manager-plugin",
        json.dumps(ssm_nc_server),
        aws_region,
        "StartSession",
        aws_account,
        json.dumps(dict(Target=target)),
        f"https://ssm.{aws_region}.amazonaws.com",
    ]


def run_sshd_command(
    parsed_containers, aws_region, aws_account, container_name, ecs_manifest
):
    containers = ecs_manifest.task_definition.containers
    for container in containers:
        if len(container.volumes) > 0:
            client = boto3.client("ssm")
            target = parsed_containers.get(container_name)["ssm_target"]
            command_server = [f"/usr/sbin/sshd -D"]  # noqa
            parameters_nc_server = {"command": command_server}
            ssm_nc_server = client.start_session(
                Target=target,
                DocumentName="AWS-StartInteractiveCommand",
                Parameters=parameters_nc_server,
            )
            cmd_nc_server = generate_ssm_cmd(
                ssm_nc_server, aws_region, aws_account, target
            )
            DEBUG_EASYECS = os.environ.get("DEBUG_EASYECS", None)
            stdout = None if DEBUG_EASYECS else subprocess.DEVNULL
            proc_nc_server = subprocess.Popen(
                cmd_nc_server,
                start_new_session=True,
                stdin=subprocess.PIPE,
                stdout=stdout,
            )
            popen_procs_port_forward.append(proc_nc_server)


def run_nc_command(
    parsed_containers, aws_region, aws_account, container_name, ecs_manifest
):
    containers = ecs_manifest.task_definition.containers
    for container in containers:
        if len(container.volumes) > 0:
            for volume in container.volumes:
                md5_volume = md5(volume.encode("utf-8")).hexdigest()
                random_port = generate_random_port()
                parsed_containers[container_name][
                    f"netcat_port_{md5_volume}"
                ] = random_port
                port_forward(
                    parsed_containers,
                    container_name,
                    random_port,
                    random_port,
                    aws_region,
                    aws_account,
                )
                client = boto3.client("ssm")
                target = parsed_containers.get(container_name)["ssm_target"]
                command_server = [f"""
                    bash -c '
                        set -x
                        set -u
                        while true
                        do
                            RANDOM_PORT={random_port}
                            RANDOM_NUMBER=$RANDOM
                            nc -v -l ${{RANDOM_PORT}} > /tmp/${{RANDOM_PORT}}.${{RANDOM_NUMBER}}.tar.gz.tmp
                            cp /tmp/${{RANDOM_PORT}}.${{RANDOM_NUMBER}}.tar.gz.tmp /tmp/${{RANDOM_PORT}}.${{RANDOM_NUMBER}}.copy.tar.gz
                            rm /tmp/${{RANDOM_PORT}}.${{RANDOM_NUMBER}}.tar.gz.tmp
                            fc=$(cat /tmp/${{RANDOM_PORT}}.${{RANDOM_NUMBER}}.copy.tar.gz | tar -ztf - | head -c1)
                            if [ $fc = . ]
                            then
                                cat /tmp/${{RANDOM_PORT}}.${{RANDOM_NUMBER}}.copy.tar.gz | tar -xzf -
                            else
                                # cat /tmp/${{RANDOM_PORT}}.${{RANDOM_NUMBER}}.copy.tar.gz | tar -xzf - -C /
                                tar -xzf /tmp/${{RANDOM_PORT}}.${{RANDOM_NUMBER}}.copy.tar.gz -C /
                            fi
                            rm /tmp/${{RANDOM_PORT}}.${{RANDOM_NUMBER}}.copy.tar.gz
                        done'
                    """]  # noqa
                parameters_nc_server = {"command": command_server}
                ssm_nc_server = client.start_session(
                    Target=target,
                    DocumentName="AWS-StartInteractiveCommand",
                    Parameters=parameters_nc_server,
                )
                cmd_nc_server = generate_ssm_cmd(
                    ssm_nc_server, aws_region, aws_account, target
                )
                DEBUG_EASYECS = os.environ.get("DEBUG_EASYECS", None)
                stdout = None if DEBUG_EASYECS else subprocess.DEVNULL
                proc_nc_server = subprocess.Popen(
                    cmd_nc_server,
                    start_new_session=True,
                    stdin=subprocess.PIPE,
                    stdout=stdout,
                )
                popen_procs_port_forward.append(proc_nc_server)


def install_netcat_command(target, aws_region, aws_account) -> None:
    client = boto3.client("ssm")
    commands_server = [["apt update"], ["apt install -y netcat-openbsd"]]
    for command_server in commands_server:
        parameters_nc_server = {"command": command_server}
        ssm_nc_server = client.start_session(
            Target=target,
            DocumentName="AWS-StartInteractiveCommand",
            Parameters=parameters_nc_server,
        )
        cmd_nc_server = [
            "session-manager-plugin",
            json.dumps(ssm_nc_server),
            aws_region,
            "StartSession",
            aws_account,
            json.dumps(dict(Target=target)),
            "https://ssm.eu-west-1.amazonaws.com",
        ]
        DEBUG_EASYECS = os.environ.get("DEBUG_EASYECS", None)
        stdout = None if DEBUG_EASYECS else subprocess.DEVNULL
        subprocess.run(
            cmd_nc_server,
            start_new_session=True,
            stdout=stdout,
        )


def install_sshd_client(
    target, aws_region, aws_account, auto_install_override, port, user, password
) -> None:
    DEBUG_EASYECS = os.environ.get("DEBUG_EASYECS", None)
    client = boto3.client("ssm")
    if len(auto_install_override) > 0:
        if DEBUG_EASYECS:
            print(f"{Color.YELLOW}Using auto install override commands:{Color.END}")
            for cmd in auto_install_override:
                print(f" - {' '.join(cmd)}")
        commands_server = auto_install_override
    else:
        commands_server = [
            ["apt update"],
            [
                "/bin/bash -c 'DEBIAN_FRONTEND=noninteractive apt install -y"
                " openssh-server'"
            ],
            [f"/bin/bash -c 'echo '{user}:{password}' | chpasswd'"],
            ["mkdir /run/sshd"],
            ["/bin/bash -c 'echo \"PermitRootLogin yes\" >> /etc/ssh/sshd_config'"],
            [f"/bin/bash -c 'echo \"Port {port}\" >> /etc/ssh/sshd_config'"],
        ]
        if DEBUG_EASYECS:
            print(f"{Color.YELLOW}Using default auto install commands:{Color.END}")
            for cmd in commands_server:
                print(f" - {' '.join(cmd)}")
    for command_server in commands_server:
        parameters_nc_server = {"command": command_server}
        ssm_nc_server = client.start_session(
            Target=target,
            DocumentName="AWS-StartInteractiveCommand",
            Parameters=parameters_nc_server,
        )
        cmd_nc_server = [
            "session-manager-plugin",
            json.dumps(ssm_nc_server),
            aws_region,
            "StartSession",
            aws_account,
            json.dumps(dict(Target=target)),
            "https://ssm.eu-west-1.amazonaws.com",
        ]
        stdout = None if DEBUG_EASYECS else subprocess.DEVNULL
        subprocess.run(
            cmd_nc_server,
            start_new_session=True,
            stdout=stdout,
        )


def check_nc_command(target, aws_region, aws_account):
    client = boto3.client("ssm")
    command_server = ["which nc"]
    parameters_nc_server = {"command": command_server}
    ssm_nc_server = client.start_session(
        Target=target,
        DocumentName="AWS-StartInteractiveCommand",
        Parameters=parameters_nc_server,
    )
    cmd_nc_server = [
        "session-manager-plugin",
        json.dumps(ssm_nc_server),
        aws_region,
        "StartSession",
        aws_account,
        json.dumps(dict(Target=target)),
        "https://ssm.eu-west-1.amazonaws.com",
    ]
    output = subprocess.check_output(cmd_nc_server, start_new_session=True)
    return "/nc" in output.decode("utf8").split("\n")[2]


def check_sshd_command(target, aws_region, aws_account):
    client = boto3.client("ssm")
    command_server = ["which sshd"]
    parameters_nc_server = {"command": command_server}
    ssm_nc_server = client.start_session(
        Target=target,
        DocumentName="AWS-StartInteractiveCommand",
        Parameters=parameters_nc_server,
    )
    cmd_nc_server = [
        "session-manager-plugin",
        json.dumps(ssm_nc_server),
        aws_region,
        "StartSession",
        aws_account,
        json.dumps(dict(Target=target)),
        "https://ssm.eu-west-1.amazonaws.com",
    ]
    output = subprocess.check_output(cmd_nc_server, start_new_session=True)
    return "/sshd" in output.decode("utf8").split("\n")[2]


def run_sftp_commands(
    parsed_containers,
    aws_region,
    aws_account,
    ecs_manifest,
    auto_install_sftp,
    auto_install_override,
):
    containers = ecs_manifest.task_definition.containers
    for container in containers:
        if len(container.volumes) > 0:
            container_name = container.name
            parsed_container = parsed_containers.get(container_name)
            ssm_target = parsed_container["ssm_target"]
            loader = Loader(
                f"Running sftp command on container {container_name} for"
                " synchronization:",
                f"Running sftp command on container {container_name} for"
                " synchronization: \u2705",
                f"Running sftp command on container {container_name} for"
                " synchronization: \u274c",
                0.05,
            )
            loader.start()
            has_sshd = check_sshd_command(ssm_target, aws_region, aws_account)
            if not has_sshd and not auto_install_sftp:
                print(
                    f"{Color.YELLOW}In order to use volumes on container"
                    f" {container_name}, you need to install openssh-server command on"
                    " the container and on the host machine!\nYou can try to install"
                    f" it on the container using --auto-install-sftp{Color.END}"
                )
            else:
                if not has_sshd and auto_install_sftp:
                    install_sshd_client(
                        ssm_target,
                        aws_region,
                        aws_account,
                        auto_install_override,
                        container.sftp_config.port,
                        container.sftp_config.user,
                        container.sftp_config.password,
                    )
                time.sleep(5)  # Wait a bit for sshd to be ready
                run_sshd_command(
                    parsed_containers,
                    aws_region,
                    aws_account,
                    container_name,
                    ecs_manifest,
                )
                run_sftp_sync_thread(
                    ecs_manifest, aws_region, aws_account, parsed_containers
                )
            loader.stop()


def run_nc_commands(
    parsed_containers, aws_region, aws_account, ecs_manifest, auto_install_nc
):
    containers = ecs_manifest.task_definition.containers
    for container in containers:
        if len(container.volumes) > 0:
            container_name = container.name
            parsed_container = parsed_containers.get(container_name)
            ssm_target = parsed_container["ssm_target"]
            loader = Loader(
                f"Running netcat command on container {container_name} for"
                " synchronization:",
                f"Running netcat command on container {container_name} for"
                " synchronization: \u2705",
                f"Running netcat command on container {container_name} for"
                " synchronization: \u274c",
                0.05,
            )
            loader.start()
            has_nc = check_nc_command(ssm_target, aws_region, aws_account)
            if not has_nc and not auto_install_nc:
                loader.stop_error()
                print(
                    f"{Color.YELLOW}In order to use volumes on container"
                    f" {container_name}, you need to install netcat command on the"
                    " container and on the host machine!\nYou can try to install it on"
                    f" the container using --auto-install-nc{Color.END}"
                )
            else:
                if not has_nc and auto_install_nc:
                    install_netcat_command(ssm_target, aws_region, aws_account)

                run_nc_command(
                    parsed_containers,
                    aws_region,
                    aws_account,
                    container_name,
                    ecs_manifest,
                )
                run_sync_thread(parsed_containers, ecs_manifest)
                loader.stop()


def run_force_new_deployment(stack_name):
    cluster_name = f"{stack_name}-cluster"
    service_name = f"{stack_name}-service"
    client = boto3.client("ecs")
    loader = Loader(
        "Force new deployment on service:",
        "Force new deployment on service: \u2705",
        "Force new deployment on service: \u274c",
        0.05,
    )
    loader.start()
    client.update_service(
        cluster=cluster_name,
        service=service_name,
        forceNewDeployment=True,
        deploymentConfiguration={"minimumHealthyPercent": 0},
    )
    waiter = client.get_waiter("services_stable")
    waiter.wait(
        cluster=cluster_name,
        services=[service_name],
        WaiterConfig={"Delay": 2, "MaxAttempts": 1000},
    )
    loader.stop()
