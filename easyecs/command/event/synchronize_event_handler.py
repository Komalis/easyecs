import datetime
import hashlib
import os
from os.path import dirname, basename
from pathlib import Path
import subprocess
import time
import boto3
from watchdog.events import FileSystemEvent, FileSystemEventHandler
import tarfile
import socket
import paramiko
from scp import SCPClient

from easyecs.helpers.color import Color


def create_tar_for_sync(input, output_dirname, port, volumes_excludes):
    input_path = Path(input)
    with tarfile.open(f"/tmp/{port}.copy.tar.gz", "w:gz") as f:
        if input_path.is_dir():
            for root, dirs, files in os.walk(input_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, input_path)
                    archive_name = os.path.join(output_dirname, rel_path)
                    found_exclude = False
                    for volume_exclude in volumes_excludes:
                        if volume_exclude in full_path:
                            found_exclude = True
                            break
                    if not found_exclude:
                        f.add(full_path, arcname=archive_name)
        else:
            filename = basename(input)
            f.add(input, arcname=f"{output_dirname}/{filename}")


def netcat(hostname, port, content, input, output):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    retry = 0
    MAX_RETRY = 3
    while retry < MAX_RETRY:
        try:
            s.connect((hostname, port))
            s.sendall(content)
            s.shutdown(socket.SHUT_WR)
            data = s.recv(1024)
            print(
                f"\n{Color.GRAY}Synchronized {input} to {output} !{Color.END}", end=""
            )
            if len(data) == 0:
                break
            print("Received:", repr(data))
            s.close()
        except Exception:
            retry += 1
            time.sleep(1)


def sftp(
    target,
    aws_region,
    aws_account,
    hostname,
    port,
    username,
    password,
    input,
    output,
    volumes_excludes,
):
    from easyecs.command import generate_ssm_cmd

    DEBUG_EASYECS = os.environ.get("DEBUG_EASYECS", None)
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname, port=port, username=username, password=password)

        with SCPClient(ssh.get_transport()) as scp:
            if DEBUG_EASYECS:
                print(
                    f"\n{Color.GRAY}SFTP synchronizing {input} to"
                    f" {output} ...{Color.END}",
                    end="",
                )
            tar_name = hashlib.md5(input.encode()).hexdigest()
            create_tar_for_sync(input, output, tar_name, volumes_excludes)
            if os.path.isdir(input):
                scp.put(f"/tmp/{tar_name}.copy.tar.gz", "/tmp")
                command_server = [f"""
                    bash -c '
                        set -x
                        set -u
                        fc=$(cat /tmp/{tar_name}.copy.tar.gz | tar -ztf - | head -c1)
                        if [ $fc = . ]
                        then
                            cat /tmp/{tar_name}.copy.tar.gz | tar -xzf -
                        else
                            tar -xzf /tmp/{tar_name}.copy.tar.gz -C /
                        fi
                        rm /tmp/{tar_name}.copy.tar.gz
                        '
                    """]  # noqa
                client = boto3.client("ssm")
                parameters_nc_server = {"command": command_server}
                ssm_nc_server = client.start_session(
                    Target=target,
                    DocumentName="AWS-StartInteractiveCommand",
                    Parameters=parameters_nc_server,
                )
                cmd_nc_server = generate_ssm_cmd(
                    ssm_nc_server, aws_region, aws_account, target
                )
                stdout = None if DEBUG_EASYECS else subprocess.DEVNULL
                subprocess.Popen(
                    cmd_nc_server,
                    start_new_session=True,
                    stdin=subprocess.PIPE,
                    stdout=stdout,
                )
            else:
                scp.put(input, output)
            print(
                f"\n{Color.GRAY}Synchronized {input} to {output} !{Color.END}", end=""
            )
    except Exception as e:
        if DEBUG_EASYECS:
            print(f"\n{Color.RED}SFTP synchronization failed: {e}{Color.END}", end="")


class SynchronizeEventHandler(FileSystemEventHandler):
    def __init__(self, volume, port, volumes_excludes):
        super().__init__()
        self.volume = volume
        self.port = port
        self.input = volume.split(":")[0]
        self.output = volume.split(":")[1]
        self.input_dirname = dirname(self.input)
        self.output_dirname = dirname(self.output)
        self.last_event = datetime.datetime.now().timestamp()
        self.volumes_excludes = volumes_excludes

    def synchronize(self):
        port = int(self.port)
        create_tar_for_sync(
            self.input, self.output_dirname, port, self.volumes_excludes
        )
        f = open(f"/tmp/{port}.copy.tar.gz", "rb")
        data = f.read()
        netcat("127.0.0.1", port, data, self.input, self.output_dirname)

    def dispatch(self, event: FileSystemEvent):
        delta = datetime.datetime.now().timestamp() - self.last_event
        if delta >= 1:
            event_src = event.src_path
            if event.event_type in ["modified", "created", "moved", "deleted"]:
                if not os.path.isdir(event_src):
                    if os.path.isdir(self.input):
                        if os.path.abspath(self.input) in os.path.abspath(event_src):
                            self.synchronize()
                            super().dispatch(event)
                            self.last_event = datetime.datetime.now().timestamp()
                    else:
                        if os.path.abspath(event_src) in os.path.abspath(self.input):
                            self.synchronize()
                            super().dispatch(event)
                            self.last_event = datetime.datetime.now().timestamp()


class SynchronizeSFTPEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        target,
        aws_region,
        aws_account,
        volume,
        volumes_excludes,
        port,
        username,
        password,
    ):
        super().__init__()
        self.target = target
        self.aws_region = aws_region
        self.aws_account = aws_account
        self.volume = volume
        self.input = volume.split(":")[0]
        self.output = volume.split(":")[1]
        self.input_dirname = dirname(self.input)
        self.output_dirname = dirname(self.output)
        self.last_event = datetime.datetime.now().timestamp()
        self.volumes_excludes = volumes_excludes
        self.port = port
        self.username = username
        self.password = password

    def synchronize(self):
        sftp(
            self.target,
            self.aws_region,
            self.aws_account,
            "127.0.0.1",
            self.port,
            self.username,
            self.password,
            self.input,
            self.output_dirname,
            self.volumes_excludes,
        )

    def dispatch(self, event: FileSystemEvent):
        delta = datetime.datetime.now().timestamp() - self.last_event
        if delta >= 1:
            event_src = event.src_path
            if event.event_type in ["modified", "created", "moved", "deleted"]:
                if not os.path.isdir(event_src):
                    if os.path.isdir(self.input):
                        if os.path.abspath(self.input) in os.path.abspath(event_src):
                            self.synchronize()
                            super().dispatch(event)
                            self.last_event = datetime.datetime.now().timestamp()
                    else:
                        if os.path.abspath(event_src) in os.path.abspath(self.input):
                            self.synchronize()
                            super().dispatch(event)
                            self.last_event = datetime.datetime.now().timestamp()
