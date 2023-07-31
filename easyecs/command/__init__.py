import json
import subprocess
from threading import Event, Thread
import time
import boto3
import signal
import inotify.adapters
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
        ssm_cmd = [
            "session-manager-plugin",
            json.dumps(ssm_response),
            aws_region,
            "StartSession",
            aws_account,
            json.dumps(dict(Target=target)),
            "https://ssm.eu-west-1.amazonaws.com",
        ]
        process = subprocess.Popen(
            ssm_cmd,
            start_new_session=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
        )
        popen_procs_port_forward.append(process)


class StoppableThread(Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self, port, root, exclude, *args, **kwargs):
        super(StoppableThread, self).__init__(*args, **kwargs)
        self.port = port
        self.root = root
        self.exclude = exclude
        self._stop = Event()

    def stop(self):
        self._stop.set()

    def stopped(self):
        return self._stop.isSet()

    def run(self):
        sync_events = set(["IN_CLOSE_WRITE"])
        i = inotify.adapters.InotifyTree(self.root)
        cmd_tar_local = ["tar"]
        for file in self.exclude:
            cmd_tar_local += file
        cmd_tar_local += [
            "-cvzf",
            "-",
            self.root,
        ]
        cmd_nc_local = ["nc", "-N", "127.0.0.1", self.port]
        proc_tar_local = subprocess.run(
            cmd_tar_local,
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
        while True:
            if self.stopped():
                return
            events = i.event_gen(yield_nones=False, timeout_s=0.1)
            for event in events:
                (_, type_names, path, filename) = event
                if set(type_names).issubset(sync_events):
                    proc_tar_local = subprocess.run(
                        cmd_tar_local,
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


def run_sync_thread(parsed_containers, ecs_manifest):
    containers = ecs_manifest.task_definition.containers
    for container in containers:
        synchronize = container.synchronize
        if synchronize:
            container_name = container.name
            root = synchronize.root
            exclude = [["--exclude", filename] for filename in synchronize.exclude]
            port = parsed_containers[container_name].get("netcat_port", None)
            if port:
                cmd_tar_local = ["tar"]
                for file in exclude:
                    cmd_tar_local += file
                cmd_tar_local += [
                    "-cvzf",
                    "-",
                    root,
                ]
                cmd_nc_local = ["nc", "-N", "127.0.0.1", port]
                proc_tar_local = subprocess.run(
                    cmd_tar_local,
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
                t = StoppableThread(port, root, exclude)
                threads.append(t)
                t.start()


def execute_command(ecs_manifest, parsed_containers, aws_region, aws_account):
    containers = ecs_manifest.task_definition.containers
    catchable_sigs = set(signal.Signals) - {signal.SIGKILL, signal.SIGSTOP}
    ssm_client = boto3.client("ssm")
    found_tty = False
    tty_cmd = ""
    for container in containers:
        command = container.command
        if command:
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
    command_server = [
        f"bash -c 'while true; do nc -l {random_port} | tar -xzf -; done'"
    ]
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
        synchronize = container.synchronize
        if synchronize:
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
