"""Runs the clipping loop in the background so the app can start/stop it."""
import threading
import time
from collections import deque
from datetime import datetime, timedelta

import main as core


class Engine:
    def __init__(self):
        self.logs = deque(maxlen=800)
        self.seq = 0
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self.state = "stopped"          # stopped | idle | working | stopping
        self.last_check = None
        self.next_check = None
        self.busy_with = ""
        self.test_running = False
        self.camp_status = {}           # campaign name -> latest activity line
        self._current = None            # campaign currently being worked on
        core.LOG_HOOKS.append(self._on_log)
        core.STOP_CHECK[0] = self._stop.is_set

    # ---------------------------------------------------------------- logs
    def _on_log(self, line: str):
        with self._lock:
            self.seq += 1
            self.logs.append((self.seq, line))
        body = line.split("] ", 1)[1] if "] " in line else line
        if body.startswith("["):
            name = body[1:body.find("]")]
            self._current = name
            self.camp_status[name] = {"text": body[len(name) + 3:], "time": line[1:20]}
            self.busy_with = body[:90]
        elif self._current and body.startswith("   "):
            self.camp_status[self._current] = {"text": body.strip(), "time": line[1:20]}

    def log(self, msg: str):
        core.log(msg)

    def logs_since(self, n: int):
        with self._lock:
            return [{"n": i, "line": l} for i, l in self.logs if i > n]

    # ---------------------------------------------------------------- control
    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.running:
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        if not self.running:
            return False
        self.state = "stopping"
        self._stop.set()
        self._wake.set()
        self.log("Stopping after the current clip...")
        return True

    def check_now(self):
        if not self.running:
            return self.start()
        self._wake.set()
        return True

    def _loop(self):
        self.log("Engine started.")
        state = core.load_state()
        while not self._stop.is_set():
            cfg = core.load_cfg()
            out_dir = cfg.get("output_folder", "clips")
            self.state = "working"
            self.last_check = datetime.now()
            try:
                jobs = core.build_jobs(cfg)
                if not jobs:
                    self.log("No campaigns yet. Add one in the Campaigns tab.")
                more = True
                while more and not self._stop.is_set():   # each campaign gets a turn
                    more = False
                    for job in jobs:
                        if self._stop.is_set():
                            break
                        more = bool(core.run_job(job, state, out_dir)) or more
                core.gallery.build(out_dir)
            except Exception as e:
                self.log(f"error: {e}")
            if self._stop.is_set():
                break
            mins = max(5, cfg.get("check_every_minutes", 30))
            self.next_check = datetime.now() + timedelta(minutes=mins)
            self.state = "idle"
            self.busy_with = ""
            self._wake.clear()
            self._wake.wait(timeout=mins * 60)
        self.state = "stopped"
        self.next_check = None
        self.busy_with = ""
        self.log("Engine stopped.")

    # ---------------------------------------------------------------- test runs
    def run_test(self, video_path: str, campaign_name: str | None):
        if self.test_running:
            return False

        def work():
            self.test_running = True
            try:
                import sys
                argv = ["main.py", "--test", video_path] + (["--campaign", campaign_name] if campaign_name else [])
                old = sys.argv
                sys.argv = argv
                try:
                    core.main()
                finally:
                    sys.argv = old
            except Exception as e:
                self.log(f"test failed: {e}")
            finally:
                self.test_running = False
        threading.Thread(target=work, daemon=True).start()
        return True

    def status(self):
        return {
            "state": self.state if self.running else "stopped",
            "last_check": self.last_check.isoformat(timespec="minutes") if self.last_check else None,
            "next_check": self.next_check.isoformat(timespec="minutes") if self.next_check else None,
            "busy_with": self.busy_with,
            "test_running": self.test_running,
        }


ENGINE = Engine()
