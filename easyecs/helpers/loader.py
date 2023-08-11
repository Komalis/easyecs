from itertools import cycle
from math import floor
from shutil import get_terminal_size
from threading import Thread
from time import sleep

from easyecs.helpers.color import Color


class Loader:
    def __init__(self, desc="Loading...", end="Done!", error="Error!", timeout=0.1):
        """
        A loader-like context manager

        Args:
            desc (str, optional): The loader's description. Defaults to "Loading...".
            end (str, optional): Final print. Defaults to "Done!".
            timeout (float, optional): Sleep time between prints. Defaults to 0.1.
        """
        self.desc = desc
        self.end = end
        self.error = error
        self.timeout = timeout
        self.time = 0
        self.metadata = None

        self._thread = Thread(target=self._animate, daemon=True)
        self.steps = ["⢿", "⣻", "⣽", "⣾", "⣷", "⣯", "⣟", "⡿"]
        self.done = False

    def start(self):
        self._thread.start()
        return self

    def _animate(self):
        for c in cycle(self.steps):
            if self.done:
                break
            if not self.metadata:
                print(
                    f"\r{self.desc} {c} {Color.GRAY}[{floor(self.time)}s]{Color.END}",
                    flush=True,
                    end="",
                )
            else:
                print(f"\r{self.metadata}", flush=True)
                self.metadata = None
            sleep(self.timeout)
            self.time += self.timeout

    def __enter__(self):
        self.start()

    def set_metadata(self, metadata):
        self.metadata = metadata

    def stop(self):
        self.done = True
        cols = get_terminal_size((80, 20)).columns
        print("\r" + " " * cols, end="", flush=True)
        if not self.metadata:
            print(f"\r{self.end} [{floor(self.time)}s]", flush=True)
        else:
            print(f"\r{self.metadata}", flush=True)
            print(f"\r{self.end} [{floor(self.time)}s]")
            self.metadata = None

    def stop_error(self):
        self.done = True
        cols = get_terminal_size((80, 20)).columns
        print("\r" + " " * cols, end="", flush=True)
        if not self.metadata:
            print(f"\r{self.error}", flush=True)
        else:
            print(f"\r{self.metadata}", flush=True)
            print(f"\r{self.error}")
            self.metadata = None

    def __exit__(self, exc_type, exc_value, tb):
        # handle exceptions with those variables ^
        self.stop()
