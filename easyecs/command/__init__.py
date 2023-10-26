import json
import os
import subprocess
import time
import boto3
import signal
from watchdog.observers import Observer
from easyecs.command.event.synchronize_event_handler import SynchronizeEventHandler
from easyecs.helpers.color import Color
from easyecs.helpers.common import generate_random_port, is_port_in_use
from easyecs.helpers.loader import Loader

from easyecs.helpers.signal import override_sigint

port_forward_pids = []
threads = []
popen_procs_port_forward = []
popen_procs_exec_command = []


def create_port_forwards(ecs_manifest, aws_region, aws_account, parsed_containers):
    containers = ecs_manifest.task_definition.containers
    for container in containers:
        container_name = container.name
        container_ports = container.port_forward
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
            port = parsed_containers[container_name].get("netcat_port", None)
            for volume in container.volumes:
                event_handler = SynchronizeEventHandler(volume, port)
                observer.schedule(event_handler, ".", recursive=True)
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


def run_nc_command(parsed_containers, aws_region, aws_account, container_name):
    random_port = generate_random_port()
    parsed_containers[container_name]["netcat_port"] = random_port
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
    # command_server = [
    # f"bash -c 'while true; do nc -l {random_port} | tar -xzf -; done'"
    # ]
    command_server = [
        f"bash -c 'while true; do nc -q1 -v -l {random_port} > /tmp/copy.tar.gz.tmp; cp"
        " /tmp/copy.tar.gz.tmp /tmp/copy.tar.gz; fc=$(cat /tmp/copy.tar.gz | tar -ztf"
        " - | head -c1); if [ $fc = . ]; then cat /tmp/copy.tar.gz | tar -xzf -; else"
        " cat /tmp/copy.tar.gz | tar -xzf - -C /; fi; done'"
    ]
    parameters_nc_server = {"command": command_server}
    ssm_nc_server = client.start_session(
        Target=target,
        DocumentName="AWS-StartInteractiveCommand",
        Parameters=parameters_nc_server,
    )
    cmd_nc_server = generate_ssm_cmd(ssm_nc_server, aws_region, aws_account, target)
    DEBUG_EASYECS = os.environ.get("DEBUG_EASYECS", None)
    if DEBUG_EASYECS:
        proc_nc_server = subprocess.Popen(
            cmd_nc_server,
            start_new_session=True,
            stdin=subprocess.PIPE,
        )
    else:
        proc_nc_server = subprocess.Popen(
            cmd_nc_server,
            start_new_session=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
        )
    popen_procs_port_forward.append(proc_nc_server)


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


def run_nc_commands(parsed_containers, aws_region, aws_account, ecs_manifest):
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
            if not has_nc:
                loader.stop_error()
                print(
                    f"{Color.YELLOW}In order to use volumes on container"
                    f" {container_name}, you need to install netcat command on the"
                    f" container and on the host machine!{Color.END}"
                )
            else:
                run_nc_command(
                    parsed_containers, aws_region, aws_account, container_name
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
