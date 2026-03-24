import platform
import subprocess


class CaffeinateGuard:
    def __init__(self):
        self._process: subprocess.Popen | None = None
        self._active_tasks: int = 0
        self._is_macos = platform.system() == "Darwin"

    def acquire(self) -> None:
        self._active_tasks += 1
        if self._is_macos and self._active_tasks == 1 and self._process is None:
            self._process = subprocess.Popen(["caffeinate", "-s"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def release(self) -> None:
        self._active_tasks = max(0, self._active_tasks - 1)
        if self._active_tasks == 0 and self._process is not None:
            self._process.terminate()
            self._process.wait()
            self._process = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()

    def __del__(self):
        if self._process is not None:
            self._process.terminate()
