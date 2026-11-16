"""Checks that everything AutoClipper needs is installed. Run doctor.bat."""
import importlib
import os
import shutil
import socket
import subprocess
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
lines, problems = [], 0


def ok(msg):
    lines.append(f"  OK    {msg}")


def bad(msg, fix):
    global problems
    problems += 1
    lines.append(f"  FIX   {msg}\n        -> {fix}")


def note(msg):
    lines.append(f"  NOTE  {msg}")


v = sys.version_info
(ok if (3, 10) <= v[:2] <= (3, 12) else lambda m: bad(m, "Run setup.bat again (it installs Python 3.12)"))(
    f"Python {v.major}.{v.minor}")

for mod, need, fix in [
    ("flask", True, "Run setup.bat again"), ("yaml", True, "Run setup.bat again"),
    ("numpy", True, "Run setup.bat again"), ("yt_dlp", True, "Run setup.bat again"),
    ("cv2", True, "Run setup.bat again"), ("pypdf", False, "PDF briefs won't work; paste briefs as text"),
    ("faster_whisper", False, "Clips will have no captions"),
    ("chat_downloader", False, "Moments found by audio only (still works)")]:
    try:
        importlib.import_module(mod)
        ok(f"library {mod}")
    except Exception as e:
        (bad if need else lambda m, f: note(f"{m} - {f}"))(f"library {mod} missing ({type(e).__name__})", fix)

if shutil.which("ffmpeg"):
    ok("FFmpeg")
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=256x256:d=0.2",
                            "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True, timeout=30)
        ok("NVIDIA GPU encoding") if r.returncode == 0 else note("GPU encoding off - uses CPU (slower, still works)")
    except Exception:
        note("GPU encoding check skipped")
else:
    bad("FFmpeg not found", "Restart your PC (so Windows sees FFmpeg), or run setup.bat again")

s = socket.socket()
try:
    s.bind(("127.0.0.1", 8765))
    ok("Port 8765 is free")
except OSError:
    note("Port 8765 in use - AutoClipper may already be running (that's fine)")
finally:
    s.close()

for f in ("app.py", "main.py", "config.yaml", os.path.join("web", "index.html")):
    (ok if os.path.exists(f) else lambda m: bad(m, "Unzip the full AutoClipper folder again"))(f"file {f}")

edge = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
if os.name == "nt":
    ok("App window: Edge/Chrome found") if any(os.path.exists(p) for p in edge) else \
        note("Edge/Chrome not found - the app opens in your default browser instead")

report = "AutoClipper check\n" + "\n".join(lines) + (
    "\n\nALL GOOD - open AutoClipper from your desktop." if problems == 0
    else f"\n\n{problems} thing(s) to fix above. Screenshot this and send it to Claude if stuck.")
print(report)
with open("doctor_report.txt", "w", encoding="utf-8") as f:
    f.write(report)
