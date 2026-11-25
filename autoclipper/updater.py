"""Self-updater: pulls the newest AutoClipper from GitHub and keeps your data.

Checks  https://raw.githubusercontent.com/<repo>/main/VERSION
If newer, downloads the repo zip, replaces the program files, and keeps:
config.yaml settings, campaigns/, clips/, state.json, posted.json, .venv/, temp/
"""
import io
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

KEEP = {"config.yaml", "campaigns", "clips", "state.json", "posted.json", ".venv", "temp", "hooks_history.json",
        "posts.json", "performance.json", "learned.json", "learn_stamp.json",
        "doctor_report.txt", "app_error.txt", "youtube_token.json", "client_secret.json", ".git"}
UA = {"User-Agent": "AutoClipper-updater"}


def local_version(root=".") -> str:
    try:
        with open(os.path.join(root, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0"


def _v(s: str) -> tuple:
    out = []
    for p in s.strip().lstrip("v").split("."):
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out)


def _get(url: str, timeout=20) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def check(repo: str, branch: str = "main") -> dict:
    """Return {current, latest, available, notes}."""
    cur = local_version()
    try:
        latest = _get(f"https://raw.githubusercontent.com/{repo}/{branch}/VERSION").decode().strip()
    except Exception as e:
        return {"current": cur, "latest": None, "available": False, "error": f"can't check ({e})"}
    notes = ""
    try:
        notes = _get(f"https://raw.githubusercontent.com/{repo}/{branch}/CHANGELOG.md").decode()[:3000]
    except Exception:
        pass
    return {"current": cur, "latest": latest, "available": _v(latest) > _v(cur), "notes": notes}


def _merge_config(old_path: str, new_text: str) -> str:
    """Keep the user's values; add any new settings from the update."""
    import yaml
    try:
        with open(old_path, encoding="utf-8") as f:
            old = yaml.safe_load(f) or {}
    except OSError:
        return new_text
    new = yaml.safe_load(new_text) or {}
    missing = {k: v for k, v in new.items() if k not in old}
    with open(old_path, encoding="utf-8") as f:
        text = f.read()
    if missing:
        text += "\n# ---- added by update ----\n" + yaml.safe_dump(missing, sort_keys=False, allow_unicode=True)
    return text


def apply(repo: str, branch: str = "main", root: str = ".") -> dict:
    """Download and install the update. Returns {ok, version, deps_changed}."""
    data = _get(f"https://github.com/{repo}/archive/refs/heads/{branch}.zip", timeout=120)
    z = zipfile.ZipFile(io.BytesIO(data))
    top = z.namelist()[0].split("/")[0]
    old_req = open(os.path.join(root, "requirements.txt"), encoding="utf-8").read() \
        if os.path.exists(os.path.join(root, "requirements.txt")) else ""
    new_cfg_text = None
    for name in z.namelist():
        rel = name[len(top) + 1:]
        if not rel or rel.endswith("/"):
            continue
        first = rel.split("/")[0]
        if rel == "config.yaml":
            new_cfg_text = z.read(name).decode("utf-8")
            continue
        if first in KEEP and first != "campaigns":
            continue
        if first == "campaigns" and not rel.startswith("campaigns/_TEMPLATE/"):
            continue  # never touch the user's campaigns
        dest = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(z.read(name))
    if new_cfg_text is not None:
        cfg_path = os.path.join(root, "config.yaml")
        merged = _merge_config(cfg_path, new_cfg_text) if os.path.exists(cfg_path) else new_cfg_text
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(merged)
    new_req = open(os.path.join(root, "requirements.txt"), encoding="utf-8").read() \
        if os.path.exists(os.path.join(root, "requirements.txt")) else ""
    deps = new_req != old_req
    if deps:  # install one by one so an optional library failing doesn't block the rest
        for line in new_req.splitlines():
            pkg = line.strip()
            if pkg and not pkg.startswith("#"):
                subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"])
    return {"ok": True, "version": local_version(root), "deps_changed": deps}
