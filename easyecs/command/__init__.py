import datetime
import json
from os.path import dirname
import subprocess
import time
import boto3
import signal
import pyinotify
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


class CopyThreadedNotifier(pyinotify.ThreadedNotifier):
    def __init__(
        self,
        watch_manager,
        volume,
        default_proc_fun=None,
        read_freq=0,
        threshold=0,
        timeout=None,
    ):
        super().__init__(watch_manager, default_proc_fun, read_freq, threshold, timeout)
        input = volume.split(":")[0]
        watch_manager.add_watch(input, pyinotify.IN_MODIFY, rec=True, auto_add=True)


class Identity(pyinotify.ProcessEvent):
    def __init__(self, volume, port, pevent=None, **kwargs):
        super().__init__(pevent, **kwargs)
        self.volume = volume
        self.port = port
        self.input = volume.split(":")[0]
        self.output = volume.split(":")[1]
        self.input_dirname = dirname(self.input)
        self.output_dirname = dirname(self.output)
        self.last_event = datetime.datetime.now().timestamp()

    def process_default(self, event):
        delta = datetime.datetime.now().timestamp() - self.last_event
        if delta >= 1:
            cmd_nc_local = ["nc", "-N", "127.0.0.1", self.port]
            if self.input_dirname.startswith("/"):
                cmd_input_dirname = self.input_dirname[1:]
            else:
                cmd_input_dirname = self.input_dirname
            tar_cmd = [
                "tar",
                "-czvf",
                "-",
                self.input,
                f"--transform=s,{cmd_input_dirname}/,{self.output_dirname}/,",
            ]
            proc_tar_local = subprocess.run(
                tar_cmd,
                start_new_session=True,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                cmd_nc_local,
                start_new_session=True,
                input=proc_tar_local.stdout,
                stdout=subprocess.DEVNULL,
            )
            self.last_event = datetime.datetime.now().timestamp()


def run_sync_thread(parsed_containers, ecs_manifest):
    containers = ecs_manifest.task_definition.containers
    for container in containers:
        if len(container.volumes) > 0:
            container_name = container.name
            port = parsed_containers[container_name].get("netcat_port", None)
            for volume in container.volumes:
                wm1 = pyinotify.WatchManager()
                s1 = pyinotify.Stats()  # Stats is a subclass of ProcessEvent
                notifier1 = CopyThreadedNotifier(
                    wm1, volume, default_proc_fun=Identity(volume, port, pevent=s1)
                )
                notifier1.daemon = True
                notifier1.start()


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
        f"bash -c 'while true; do rm -f /tmp/copy.tar.gz; nc -l {random_port} >"
        " /tmp/copy.tar.gz; fc=$(cat /tmp/copy.tar.gz | tar -ztf - | head -c1); if ["
        " $fc = . ]; then cat /tmp/copy.tar.gz | tar -xzf -; else cat /tmp/copy.tar.gz"
        " | tar -xzf - -C /; fi; done'"
    ]
    parameters_nc_server = {"command": command_server}
    ssm_nc_server = client.start_session(
        Target=target,
        DocumentName="AWS-StartInteractiveCommand",
        Parameters=parameters_nc_server,
    )
    cmd_nc_server = generate_ssm_cmd(ssm_nc_server, aws_region, aws_account, target)
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
