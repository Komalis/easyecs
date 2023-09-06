import datetime
from os.path import dirname
import subprocess
from watchdog.events import FileSystemEvent, FileSystemEventHandler


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
                    if event_src in self.input:
                        self.synchronize()
                        super().dispatch(event)
                        self.last_event = datetime.datetime.now().timestamp()
