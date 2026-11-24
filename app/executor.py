"""Execução sem shell, com limite combinado de saída e grupo de processos."""
import os
import selectors
import signal
import subprocess
import threading
import time


class Job:
    def __init__(self):
        self.cancel = threading.Event()
        self.process = None


def terminate(process):
    if not process:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run(argv, *, cwd=None, timeout=30, output_limit=131072, job=None, env=None):
    job = job or Job()
    started = time.monotonic()
    result = {"stdout": "", "stderr": "", "exit_code": None, "reason": "completed"}
    if job.cancel.is_set():
        return {**result, "reason": "interrupted", "duration": 0}
    chunks = {"stdout": bytearray(), "stderr": bytearray()}
    total = 0
    process = None
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=env, shell=False, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        job.process = process
        with selectors.DefaultSelector() as selector:
            for name, pipe in (("stdout", process.stdout), ("stderr", process.stderr)):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, name)
            while selector.get_map():
                if job.cancel.is_set():
                    result["reason"] = "interrupted"
                    break
                if time.monotonic() - started > timeout:
                    result["reason"] = "timeout"
                    break
                for key, _ in selector.select(0.05):
                    chunk = os.read(key.fileobj.fileno(), min(8192, output_limit - total + 1))
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    room = output_limit - total
                    chunks[key.data].extend(chunk[:room])
                    total += len(chunk)
                    if total > output_limit:
                        result["reason"] = "output_limit"
                        break
                if result["reason"] != "completed":
                    break
            # A process can close its output pipes and still keep running.
            while result["reason"] == "completed" and process.poll() is None:
                if job.cancel.is_set():
                    result["reason"] = "interrupted"
                elif time.monotonic() - started > timeout:
                    result["reason"] = "timeout"
                else:
                    job.cancel.wait(0.05)
        if result["reason"] != "completed":
            terminate(process)
        result["exit_code"] = process.wait(timeout=3)
    except (OSError, subprocess.SubprocessError) as exc:
        terminate(process)
        if process:
            process.wait()
        result["reason"] = "error"
        result["error"] = str(exc)
    finally:
        if process:
            # Also stop descendants that inherited the group after the parent exits.
            terminate(process)
            process.stdout.close()
            process.stderr.close()
        job.process = None
    result.update({k: bytes(v).decode("utf-8", errors="replace") for k, v in chunks.items()})
    result["duration"] = round(time.monotonic() - started, 3)
    return result
