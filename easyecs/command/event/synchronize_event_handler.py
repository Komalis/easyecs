import datetime
import os
from os.path import dirname, basename
import time
from watchdog.events import FileSystemEvent, FileSystemEventHandler
import tarfile
import socket

from easyecs.helpers.color import Color


def create_tar_for_sync(input, output_dirname, port):
    with tarfile.open(f"/tmp/{port}.copy.tar.gz", "w:gz") as f:
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


class SynchronizeEventHandler(FileSystemEventHandler):
    def __init__(self, volume, port):
        super().__init__()
        self.volume = volume
        self.port = port
        self.input = volume.split(":")[0]
        self.output = volume.split(":")[1]
        self.input_dirname = dirname(self.input)
        self.output_dirname = dirname(self.output)
        self.last_event = datetime.datetime.now().timestamp()

    def synchronize(self):
        port = int(self.port)
        create_tar_for_sync(self.input, self.output_dirname, port)
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
