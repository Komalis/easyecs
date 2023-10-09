import datetime
from os.path import dirname, basename
from watchdog.events import FileSystemEvent, FileSystemEventHandler
import tarfile
import socket


def create_tar_for_sync(input, output_dirname):
    with tarfile.open("/tmp/copy.tar.gz", "w:gz") as f:
        filename = basename(input)
        f.add(input, arcname=f"{output_dirname}/{filename}")


def netcat(hostname, port, content):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((hostname, port))
    s.sendall(content)
    s.shutdown(socket.SHUT_WR)
    while 1:
        data = s.recv(1024)
        if len(data) == 0:
            break
        print("Received:", repr(data))
    s.close()


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
        create_tar_for_sync(self.input, self.output_dirname)
        f = open("/tmp/copy.tar.gz", "rb")
        data = f.read()
        netcat("127.0.0.1", int(self.port), data)

    def dispatch(self, event: FileSystemEvent):
        delta = datetime.datetime.now().timestamp() - self.last_event
        if delta >= 1:
            event_src = event.src_path
            if event.event_type in ["modified", "created", "moved", "deleted"]:
                if event.is_directory:
                    if self.input in event_src:
                        self.synchronize()
                        super().dispatch(event)
                        self.last_event = datetime.datetime.now().timestamp()
                else:
                    if basename(event_src) in basename(self.input):
                        self.synchronize()
                        super().dispatch(event)
                        self.last_event = datetime.datetime.now().timestamp()
