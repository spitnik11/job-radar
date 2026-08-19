"""Desktop launcher for Jobber. Double-click the shortcut -> starts the backend if it isn't
already running (hidden, no console), waits for it, then opens the browser. Run with pythonw.exe
so nothing flashes on screen."""

from __future__ import annotations

import socket
import subprocess
import time
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent          # backend/
PORT = 8000
URL = f"http://localhost:{PORT}"


def _up() -> bool:
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main() -> None:
    if not _up():
        pyw = HERE / ".venv" / "Scripts" / "pythonw.exe"
        py = pyw if pyw.exists() else Path("pythonw")
        # pythonw has no console: give the child real stdout/stderr (a log file) or uvicorn's
        # logging crashes at startup on the invalid inherited handles.
        log = open(HERE / "jobber.log", "a", buffering=1, encoding="utf-8")
        subprocess.Popen(
            [str(py), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=str(HERE),
            stdout=log, stderr=log,
            creationflags=0x08000000,           # CREATE_NO_WINDOW
        )
        for _ in range(60):                      # wait up to ~30s for startup
            if _up():
                break
            time.sleep(0.5)
    webbrowser.open(URL)


if __name__ == "__main__":
    main()
