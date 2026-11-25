"""AutoClipper app — runs the engine and the control panel (http://127.0.0.1:8765).

Start it with AutoClipper.bat (opens as its own window).
"""
import glob
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())


def _disable_quickedit():
    """Clicking inside the black window normally FREEZES the app (Windows QuickEdit).
    Turn that off so a stray click can never hang AutoClipper."""
    if os.name != "nt":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-10)
        mode = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(mode)):
            k.SetConsoleMode(h, (mode.value & ~0x0040) | 0x0080)
    except Exception:
        pass


_disable_quickedit()

try:
    import yaml
    from flask import Flask, abort, jsonify, request, send_file, send_from_directory
    import main as core
    from autoclipper import campaign
    from autoclipper.engine import ENGINE
except Exception as _e:  # show a clear message instead of a silent crash
    import traceback
    msg = traceback.format_exc()
    with open("app_error.txt", "w", encoding="utf-8") as _f:
        _f.write(msg)
    print("\n!! AutoClipper couldn't start:\n")
    print(msg)
    print("Fix: double-click setup.bat again. If it still fails, send this window to Claude.")
    sys.exit(1)

PORT = 8765
POSTED = "posted.json"
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 ** 3   # allow big footage uploads


# ------------------------------------------------------------------ helpers
def cfg():
    return core.load_cfg()


def out_dir():
    d = cfg().get("output_folder", "clips")
    os.makedirs(d, exist_ok=True)
    return os.path.abspath(d)


def camp_root():
    d = cfg().get("campaigns_folder", "campaigns")
    os.makedirs(d, exist_ok=True)
    return os.path.abspath(d)


def inside(base: str, rel: str) -> str:
    """Join safely (no ../ tricks)."""
    p = os.path.abspath(os.path.join(base, rel))
    if not (p == base or p.startswith(base + os.sep)):
        abort(400)
    return p


def camp_dir(name: str) -> str:
    p = inside(camp_root(), os.path.basename(name))
    if not os.path.isdir(p):
        abort(404)
    return p


def load_posted():
    try:
        with open(POSTED, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_posted(p):
    with open(POSTED, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=1)


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


# ------------------------------------------------------------------ pages
@app.get("/")
def index():
    return send_file(os.path.join("web", "index.html"))


@app.get("/media/<path:rel>")
def media(rel):
    p = inside(out_dir(), rel)
    if not os.path.isfile(p):
        abort(404)
    return send_file(p, as_attachment=request.args.get("dl") == "1")


# ------------------------------------------------------------------ engine
@app.get("/api/status")
def status():
    c = cfg()
    clips = glob.glob(os.path.join(out_dir(), "**", "meta.json"), recursive=True)
    posted = load_posted()
    ids = [os.path.relpath(os.path.dirname(m), out_dir()).replace("\\", "/") for m in clips]
    phone = bool(c.get("phone_access"))
    return jsonify({
        **ENGINE.status(),
        "clips_total": len(ids),
        "clips_ready": len([i for i in ids if posted.get(i) is not True]),
        "clips_posted": len([i for i in ids if posted.get(i) is True]),
        "campaigns": len(campaign.discover(c.get("campaigns_folder", "campaigns"))),
        "phone_url": f"http://{lan_ip()}:{PORT}" if phone and lan_ip() else None,
        "check_every": c.get("check_every_minutes", 30),
    })


@app.post("/api/engine/<action>")
def engine_action(action):
    ok = {"start": ENGINE.start, "stop": ENGINE.stop, "check": ENGINE.check_now}.get(action)
    if not ok:
        abort(404)
    return jsonify({"ok": ok()})


@app.get("/api/logs")
def logs():
    return jsonify(ENGINE.logs_since(int(request.args.get("since", 0))))


# ------------------------------------------------------------------ clips
@app.get("/api/clips")
def clips():
    from autoclipper import learn
    base = out_dir()
    posted = load_posted()
    links = learn._load(learn.POSTS, {})
    items = []
    for mp in glob.glob(os.path.join(base, "**", "meta.json"), recursive=True):
        try:
            with open(mp, encoding="utf-8") as f:
                m = json.load(f)
        except Exception:
            continue
        cid = os.path.relpath(os.path.dirname(mp), base).replace("\\", "/")
        m["links"] = {k: v.get("url") for k, v in links.get(cid, {}).items()}
        m.update({"id": cid, "posted": _is_done(posted.get(cid), m.get("platforms") or ["tiktok", "youtube"]),
                  "posted_on": posted.get(cid) if isinstance(posted.get(cid), dict) else {},
                  "video": f"/media/{cid}/clip.mp4", "thumb": f"/media/{cid}/thumbnail.jpg"})
        items.append(m)
    items.sort(key=lambda m: (m.get("created", ""), m.get("score", 0)), reverse=True)
    return jsonify(items)


def _is_done(val, plats):
    if val is True:
        return True
    if isinstance(val, dict):
        return all(val.get(x) for x in plats)
    return False


@app.post("/api/clips/posted")
def mark_posted():
    """{id, posted} marks the whole clip; {id, platform, posted} marks one platform."""
    data = request.get_json(force=True)
    p = load_posted()
    cid, plat = data["id"], data.get("platform")
    if plat:
        cur = p.get(cid)
        cur = {} if not isinstance(cur, dict) else cur
        cur[plat] = bool(data.get("posted", True))
        p[cid] = cur
        try:  # all allowed platforms done -> the clip counts as posted
            with open(os.path.join(inside(out_dir(), cid), "meta.json"), encoding="utf-8") as f:
                plats = json.load(f).get("platforms") or ["tiktok", "youtube"]
            if all(cur.get(x) for x in plats):
                p[cid] = True
        except Exception:
            pass
    else:
        p[cid] = bool(data.get("posted", True))
    save_posted(p)
    return jsonify({"ok": True})


@app.post("/api/clips/link")
def clip_link():
    """Save the link of a posted clip so AutoClipper can track its views and learn from it."""
    from autoclipper import learn
    d = request.get_json(force=True)
    url = (d.get("url") or "").strip()
    if not url.startswith("http"):
        return jsonify({"error": "Paste the full link (starts with https://)"}), 400
    learn.add_link(d["id"], d["platform"], url)
    p = load_posted()   # adding a link also ticks that platform as posted
    cur = p.get(d["id"]) if isinstance(p.get(d["id"]), dict) else {}
    cur[d["platform"]] = True
    p[d["id"]] = cur
    save_posted(p)
    return jsonify({"ok": True})


@app.post("/api/clips/views")
def clip_views():
    from autoclipper import learn
    d = request.get_json(force=True)
    learn.set_manual_views(d["id"], d["platform"], int(d["views"]))
    return jsonify({"ok": True})


@app.get("/api/insights")
def insights():
    from autoclipper import learn
    L = learn.learned()
    posts = learn._load(learn.POSTS, {})
    perf = learn._load(learn.PERF, {})
    latest = {}
    for cid, plats in perf.items():
        for plat, rows in plats.items():
            if rows:
                latest.setdefault(cid, {})[plat] = rows[-1]
    tracked = sum(len(v) for v in posts.values())
    return jsonify({"learned": L, "tracked_posts": tracked, "latest": latest,
                    "min_clips": learn.MIN_CLIPS, "enabled": cfg().get("self_learning", True)})


@app.get("/api/rules")
def rules_get():
    from autoclipper import rules
    return jsonify({"current": rules.current(), "changed": rules.changed_only(),
                    "defaults": {k: v[0] for k, v in rules.TUNABLE.items()},
                    "describe": {k: v[4] for k, v in rules.TUNABLE.items()},
                    "review": rules.last_review(), "changelog": rules.changelog(),
                    "enabled": cfg().get("auto_tune_rules", True)})


@app.post("/api/rules/reset")
def rules_reset():
    from autoclipper import rules
    rules.reset()
    ENGINE.log("Rules: reset to defaults")
    return jsonify({"ok": True})


@app.post("/api/insights/refresh")
def insights_refresh():
    def work():
        try:
            core.learning_cycle(cfg(), force=True)
        except Exception as e:
            ENGINE.log(f"learning failed: {e}")
    threading.Thread(target=work, daemon=True).start()
    ENGINE.log("Learning: checking your posts' views and scanning other clippers now...")
    return jsonify({"ok": True})


@app.get("/api/plan")
def posting_plan():
    """Today's plan: best unposted clips, staggered per platform (Reels first, TikTok 2-3h later)."""
    from datetime import datetime, timedelta
    c = cfg()
    n = int(c.get("posts_per_day", 3))
    audience = str(c.get("posting_audience", "US")).upper()
    first_hour = 8 if audience == "US" else 18          # PH time: 8 AM = 7 PM New York
    base = out_dir()
    posted = load_posted()
    viewer, auto = [], []
    for mp in glob.glob(os.path.join(base, "**", "meta.json"), recursive=True):
        try:
            with open(mp, encoding="utf-8") as f:
                m = json.load(f)
        except Exception:
            continue
        cid = os.path.relpath(os.path.dirname(mp), base).replace("\\", "/")
        plats = m.get("platforms") or ["tiktok", "youtube"]
        if _is_done(posted.get(cid), plats):
            continue
        m.update({"id": cid, "thumb": f"/media/{cid}/thumbnail.jpg", "video": f"/media/{cid}/clip.mp4",
                  "done": posted.get(cid) if isinstance(posted.get(cid), dict) else {}})
        (viewer if m.get("source") == "viewer clip" else auto).append(m)
    viewer.sort(key=lambda m: m.get("source_views") or 0, reverse=True)
    auto.sort(key=lambda m: m.get("score") or 0, reverse=True)
    picks = []
    while (viewer or auto) and len(picks) < n:   # alternate viewer picks and deeper cuts
        for group in (viewer, auto):
            if group and len(picks) < n:
                picks.append(group.pop(0))
    now = datetime.now()
    start = now.replace(hour=first_hour, minute=0, second=0, microsecond=0)
    day = "Today"
    if now > start + timedelta(hours=n + 3):
        start += timedelta(days=1)
        day = "Tomorrow"
    order = [("instagram", 0), ("tiktok", 150), ("youtube", 180)]   # minutes after the slot
    plan = []
    for i, m in enumerate(picks):
        slot = start + timedelta(hours=i)
        plats = m.get("platforms") or ["tiktok", "youtube"]
        steps, offset0 = [], None
        for plat, mins in order:
            if plat not in plats:
                continue
            if offset0 is None:
                offset0 = mins
            t = slot + timedelta(minutes=mins - offset0)
            steps.append({"platform": plat, "time": t.strftime("%I:%M %p").lstrip("0"),
                          "done": bool(m["done"].get(plat))})
        plan.append({k: m.get(k) for k in ("id", "hook", "campaign", "thumb", "video", "youtube_title",
                                           "youtube_description", "tiktok_caption", "source", "source_views",
                                           "length_sec")} | {"steps": steps})
    return jsonify({"day": day, "audience": audience, "plan": plan})


@app.post("/api/clips/delete")
def delete_clip():
    cid = request.get_json(force=True)["id"]
    p = inside(out_dir(), cid)
    if os.path.isfile(os.path.join(p, "meta.json")):
        shutil.rmtree(p, ignore_errors=True)
    return jsonify({"ok": True})


@app.post("/api/clips/open")
def open_clip_folder():
    cid = request.get_json(force=True)["id"]
    p = inside(out_dir(), cid)
    if os.name == "nt" and os.path.isdir(p):
        os.startfile(p)  # opens the folder in File Explorer
    return jsonify({"ok": True})


# ------------------------------------------------------------------ campaigns
def campaign_summary(folder):
    try:
        data = campaign.load_campaign(folder)
    except Exception as e:
        data = {"error": str(e)}
    mats = os.path.join(folder, "materials")
    files = {k: [os.path.basename(x) for x in glob.glob(os.path.join(mats, k, "*"))]
             for k in ("footage", "examples")}
    files["logo"] = [os.path.basename(x) for x in glob.glob(os.path.join(mats, "logo.*"))]
    _, label = campaign.read_brief(folder)
    docs = [os.path.basename(p) for p in campaign.brief_files(folder)
            if os.path.basename(p) not in ("brief.txt", "brief.md")]
    yp = os.path.join(folder, "campaign.yaml")
    nm = (data or {}).get("name") or os.path.basename(folder)
    return {"folder": os.path.basename(folder), "data": data, "files": files, "brief_docs": docs,
            "activity": ENGINE.camp_status.get(nm), "engine": ENGINE.status()["state"],
            "brief": campaign.pasted_brief(folder), "brief_file": label,
            "yaml": open(yp, encoding="utf-8").read() if os.path.exists(yp) else ""}


@app.get("/api/campaigns")
def campaigns():
    return jsonify([campaign_summary(f) for f in campaign.discover(camp_root())])


def _save_uploads(folder):
    mats = os.path.join(folder, "materials")
    for kind in ("footage", "examples"):
        os.makedirs(os.path.join(mats, kind), exist_ok=True)
        for f in request.files.getlist(kind):
            if f and f.filename:
                f.save(os.path.join(mats, kind, os.path.basename(f.filename)))
    logo = request.files.get("logo")
    if logo and logo.filename:
        ext = os.path.splitext(logo.filename)[1].lower() or ".png"
        for old in glob.glob(os.path.join(mats, "logo.*")):
            os.remove(old)
        logo.save(os.path.join(mats, "logo" + ext))
    bf = request.files.get("brief_file")
    if bf and bf.filename:   # kept ALONGSIDE the pasted text; both are read
        ext = os.path.splitext(bf.filename)[1].lower()
        if ext in (".txt", ".md", ".pdf", ".docx"):
            for old in glob.glob(os.path.join(folder, "brief_upload.*")):
                os.remove(old)
            bf.save(os.path.join(folder, "brief_upload" + ext))


@app.post("/api/campaigns")
def create_campaign():
    name = campaign.folder_name(request.form.get("name", "").strip()) if request.form.get("name", "").strip() else ""
    if not name:
        return jsonify({"error": "Give the campaign a name."}), 400
    folder = os.path.join(camp_root(), name)
    if os.path.exists(folder):
        return jsonify({"error": "A campaign with that name already exists."}), 400
    os.makedirs(os.path.join(folder, "materials", "footage"))
    os.makedirs(os.path.join(folder, "materials", "examples"))
    text = request.form.get("brief", "")
    if text.strip():
        with open(os.path.join(folder, "brief.txt"), "w", encoding="utf-8") as f:
            f.write(text)
    _save_uploads(folder)
    if request.form.get("category") in ("gaming", "irl", "talk"):
        campaign.set_override(folder, "category", request.form["category"])
    campaign.build_campaign_yaml(folder)
    ENGINE.log(f"New campaign added: {name} - checking it now")
    ENGINE.check_now()   # start working on it right away
    return jsonify(campaign_summary(folder))


@app.post("/api/campaigns/<name>/update")
def update_campaign(name):
    folder = camp_dir(name)
    text = request.form.get("brief")
    if text is not None:   # replaces only the pasted text, not uploaded documents
        with open(os.path.join(folder, "brief.txt"), "w", encoding="utf-8") as f:
            f.write(text)
    _save_uploads(folder)
    campaign.build_campaign_yaml(folder)   # re-read the brief
    ENGINE.check_now()
    return jsonify(campaign_summary(folder))


@app.put("/api/campaigns/<name>/yaml")
def save_yaml(name):
    folder = camp_dir(name)
    text = request.get_json(force=True)["yaml"]
    try:
        yaml.safe_load(text)
    except Exception as e:
        return jsonify({"error": f"That isn't valid YAML: {e}"}), 400
    if text.startswith(campaign.AUTO_MARK):     # hand-edited now: stop auto-regeneration
        text = text.split("\n", 1)[1] if "\n" in text else ""
    with open(os.path.join(folder, "campaign.yaml"), "w", encoding="utf-8") as f:
        f.write(text)
    return jsonify(campaign_summary(folder))


@app.post("/api/campaigns/<name>/set")
def set_campaign_option(name):
    folder = camp_dir(name)
    data = request.get_json(force=True)
    if data.get("category") in ("gaming", "irl", "talk"):
        campaign.set_override(folder, "category", data["category"])
        ENGINE.log(f"Campaign {name}: category set to {data['category']}")
    return jsonify(campaign_summary(folder))


@app.post("/api/campaigns/<name>/toggle")
def toggle_campaign(name):
    folder = camp_dir(name)
    yp = os.path.join(folder, "campaign.yaml")
    with open(yp, encoding="utf-8") as f:
        raw = f.read()
    data = yaml.safe_load(raw) or {}
    data["enabled"] = not data.get("enabled", True)
    header = raw.split("\n", 2)[:2] if raw.startswith(campaign.AUTO_MARK) else []
    with open(yp, "w", encoding="utf-8") as f:
        if header:
            f.write("\n".join(header) + "\n")
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True, width=100)
    return jsonify(campaign_summary(folder))


@app.post("/api/campaigns/<name>/delete")
def delete_campaign(name):
    folder = camp_dir(name)
    shutil.rmtree(folder, ignore_errors=True)
    return jsonify({"ok": True})


@app.post("/api/campaigns/<name>/remove-file")
def remove_file(name):
    folder = camp_dir(name)
    data = request.get_json(force=True)
    kind, fname = data["kind"], os.path.basename(data["file"])
    p = os.path.join(folder, "materials", fname) if kind == "logo" else \
        os.path.join(folder, "materials", kind, fname)
    p = inside(folder, os.path.relpath(p, folder))
    if os.path.isfile(p):
        os.remove(p)
    campaign.build_campaign_yaml(folder) if open(os.path.join(folder, "campaign.yaml"), encoding="utf-8") \
        .readline().startswith(campaign.AUTO_MARK) else None
    return jsonify(campaign_summary(folder))


# ------------------------------------------------------------------ test + settings
@app.post("/api/test")
def test_video():
    f = request.files.get("video")
    if not f or not f.filename:
        return jsonify({"error": "Choose a video file."}), 400
    os.makedirs("temp", exist_ok=True)
    path = os.path.abspath(os.path.join("temp", "test_" + os.path.basename(f.filename)))
    f.save(path)
    ok = ENGINE.run_test(path, request.form.get("campaign") or None)
    if not ok:
        return jsonify({"error": "A test is already running."}), 400
    return jsonify({"ok": True})


@app.get("/api/settings")
def get_settings():
    with open("config.yaml", encoding="utf-8") as f:
        return jsonify({"yaml": f.read(), "data": cfg()})


@app.put("/api/settings")
def put_settings():
    body = request.get_json(force=True)
    with open("config.yaml", encoding="utf-8") as f:
        raw = f.read()
    if "yaml" in body:
        try:
            yaml.safe_load(body["yaml"])
        except Exception as e:
            return jsonify({"error": f"That isn't valid YAML: {e}"}), 400
        raw = body["yaml"]
    else:  # simple form fields: replace "key: value" lines, keeping comments
        import re
        for k, v in (body.get("fields") or {}).items():
            val = ("true" if v else "false") if isinstance(v, bool) else str(v)
            if isinstance(v, str) and not re.fullmatch(r"-?\d+(\.\d+)?", v):
                val = json.dumps(v)
            pat = re.compile(rf"^({re.escape(k)}:\s*)([^#\n]*?)(\s*#.*)?$", re.M)
            if pat.search(raw):
                raw = pat.sub(lambda m: m.group(1) + val + (("  " + m.group(3).strip()) if m.group(3) else ""), raw, 1)
            else:
                raw += f"\n{k}: {val}\n"
    with open("config.yaml", "w", encoding="utf-8") as f:
        f.write(raw)
    return jsonify({"ok": True, "data": cfg()})


# ------------------------------------------------------------------ updates
UPDATE_INFO = {}


def _repo():
    c = cfg()
    return c.get("update_repo") or "", c.get("update_branch") or "main"


@app.get("/api/update")
def update_check():
    from autoclipper import updater
    repo, br = _repo()
    if not repo:
        return jsonify({"current": updater.local_version(), "available": False, "error": "no update_repo set"})
    UPDATE_INFO.update(updater.check(repo, br))
    return jsonify(UPDATE_INFO)


@app.post("/api/update/apply")
def update_apply():
    from autoclipper import updater
    repo, br = _repo()
    if not repo:
        return jsonify({"error": "No update source set."}), 400
    ENGINE.log("Installing update...")
    try:
        r = updater.apply(repo, br)
    except Exception as e:
        return jsonify({"error": f"Update failed: {e}"}), 500
    ENGINE.log(f"Updated to v{r['version']}. Restarting...")
    ENGINE.stop()
    threading.Timer(1.5, lambda: os._exit(3)).start()   # AutoClipper.bat restarts us
    return jsonify(r)


def startup_update():
    """Install a newer version before starting (if auto_update is on)."""
    from autoclipper import updater
    c = cfg()
    repo, br = _repo()
    if not (repo and c.get("auto_update", True)):
        return
    info = updater.check(repo, br)
    UPDATE_INFO.update(info)
    if info.get("available"):
        print(f"Updating AutoClipper v{info['current']} -> v{info['latest']} ...")
        try:
            updater.apply(repo, br)
            print("Update installed. Restarting...")
            sys.exit(3)
        except SystemExit:
            raise
        except Exception as e:
            print(f"(update skipped: {e})")
    elif info.get("latest"):
        print(f"AutoClipper v{info['current']} is up to date.")


# ------------------------------------------------------------------ launch
def open_window(url):
    """Open as an app-style window (Edge/Chrome --app), else the default browser."""
    if os.name == "nt":
        for exe in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
            if os.path.exists(exe):
                try:
                    subprocess.Popen([exe, f"--app={url}", "--window-size=1280,860"])
                    return
                except Exception:
                    pass
    webbrowser.open(url)


def _port_open() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
            return True
    except OSError:
        return False


def _open_when_ready(url):
    """Wait until the server is really answering, then open the window."""
    for _ in range(120):          # up to ~60 seconds
        if _port_open():
            open_window(url)
            print(f"Opened the AutoClipper window. If you don't see it, go to {url} in your browser.")
            return
        time.sleep(0.5)
    print(f"The app is slow to start. Go to {url} in your browser.")


def run():
    url = f"http://127.0.0.1:{PORT}"
    if _port_open():  # already running (e.g. autostart) -> just show it
        print("AutoClipper is already running - opening its window.")
        if "--no-window" not in sys.argv:
            open_window(url)
        time.sleep(2)
        return
    startup_update()
    c = cfg()
    host = "0.0.0.0" if c.get("phone_access") else "127.0.0.1"
    if c.get("auto_start_engine", True):
        ENGINE.start()
    if "--no-window" not in sys.argv:
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    print("=" * 60)
    print(f" AutoClipper is running:  {url}")
    print(" Keep this window open - closing it stops AutoClipper.")
    if host == "0.0.0.0" and lan_ip():
        print(f" Phone (same Wi-Fi):     http://{lan_ip()}:{PORT}")
    print("=" * 60)
    import logging
    logging.getLogger("werkzeug").setLevel(logging.WARNING)   # keep this window readable
    app.run(host=host, port=PORT, threaded=True, use_reloader=False)


if __name__ == "__main__":
    try:
        run()
    except SystemExit:
        raise
    except Exception:
        import traceback
        err = traceback.format_exc()
        with open("app_error.txt", "w", encoding="utf-8") as f:
            f.write(err)
        print("\n!! AutoClipper crashed:\n" + err)
        print("Screenshot this window and send it to Claude.")
        sys.exit(1)
