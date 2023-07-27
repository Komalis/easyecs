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
            print(
                f"\r{self.desc} {c} {Color.GRAY}[{floor(self.time)}s]{Color.END}",
                flush=True,
                end="",
            )
            sleep(self.timeout)
            self.time += self.timeout

    def __enter__(self):
        self.start()

    def stop(self):
        self.done = True
        cols = get_terminal_size((80, 20)).columns
        print("\r" + " " * cols, end="", flush=True)
        print(f"\r{self.end} [{floor(self.time)}s]", flush=True)

    def stop_error(self):
        self.done = True
        cols = get_terminal_size((80, 20)).columns
        print("\r" + " " * cols, end="", flush=True)
        print(f"\r{self.error}", flush=True)

    def __exit__(self, exc_type, exc_value, tb):
        # handle exceptions with those variables ^
        self.stop()
