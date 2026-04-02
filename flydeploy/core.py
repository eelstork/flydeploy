"""Core utilities: subprocess execution, prompting, and logging."""

import subprocess
import threading
from datetime import datetime
from pathlib import Path

_log_file = None


def open_log(log_path, history_dir=None):
    """Open a log file, rotating any existing log into history_dir.

    If history_dir is given and a previous log exists, the old log is
    moved there with a timestamp suffix before a new log is started.
    """
    global _log_file
    log_path = Path(log_path)

    if log_path.exists() and history_dir is not None:
        history_dir = Path(history_dir)
        date_str = None
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("Deploy run:"):
                date_str = (line.replace("Deploy run:", "").strip()
                            .replace(" ", "_").replace(":", "-"))
                break
        if not date_str:
            ts = datetime.fromtimestamp(log_path.stat().st_mtime)
            date_str = ts.strftime("%Y-%m-%d_%H-%M-%S")
        history_dir.mkdir(exist_ok=True)
        log_path.rename(history_dir / f"setup_log_{date_str}.txt")

    _log_file = log_path.open("w", encoding="utf-8")
    _log_file.write(f"Deploy run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    _log_file.write(f"{'=' * 60}\n")


def close_log():
    """Close the current log file."""
    global _log_file
    if _log_file:
        _log_file.close()
        _log_file = None


def _log(text):
    if _log_file:
        _log_file.write(text)
        _log_file.flush()


def run(cmd, *, cwd=None, capture=False, passthrough=False):
    """Run a shell command with logging and output teeing.

    capture=True:     return CompletedProcess with stdout/stderr captured.
    passthrough=True: let subprocess inherit the terminal (for interactive
                      fly commands like postgres create).
    default:          tee stdout to console and log file.
    """
    if capture:
        return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)

    _log(f"\n$ {' '.join(str(c) for c in cmd)}\n")

    if passthrough:
        _log("(interactive -- output not captured in log)\n")
        return subprocess.run(cmd, cwd=cwd, text=True)

    proc = subprocess.Popen(cmd, cwd=cwd, text=True,
                            stdout=subprocess.PIPE, stderr=None)

    def _reader():
        for line in proc.stdout:
            print(line, end="", flush=True)
            _log(line)

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    proc.wait()
    t.join()
    return proc


def prompt(msg, *, required=True, default=None, secret=False):
    """Prompt for user input.

    default: shown as [***] when secret=True, else [value].
             For secrets, accepting the default returns None (meaning
             "keep existing -- do not update").
             For plain fields, returns the default string.
    required: if True and no default, re-prompt until a value is given.
    """
    if default is not None:
        hint = f" [{'***' if secret else default}]"
    else:
        hint = ""
    while True:
        value = input(f"{msg}{hint}: ").strip()
        if value:
            return value
        if default is not None:
            return None if secret else default
        if not required:
            return ""
        print("  (required -- please enter a value)")
