"""Self-improvement loop (free, runs on your PC).

1. TRACK   - you paste the link after posting a clip; every few hours AutoClipper reads
             its views/likes/comments (public numbers, via yt-dlp).
2. LEARN   - compares clips against each other: which hook types, hook lines, lengths,
             cold open on/off, viewer picks vs deep cuts, and posting hours get more views.
3. APPLY   - future clips lean toward what works, while still trying alternatives
             (a small share of clips keep experimenting so it doesn't get stuck).

Files: posts.json (your links), performance.json (view history), learned.json (what it learned)
"""
import json
import math
import os
import random
import statistics
import time
from datetime import datetime, timedelta

POSTS = "posts.json"
PERF = "performance.json"
LEARNED = "learned.json"
MIN_CLIPS = 8          # need at least this many measured clips before trusting anything
PRIOR = 3.0            # shrink small samples toward "average" (avoids overreacting to 1 lucky clip)


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


# ------------------------------------------------------------------ 1. track
def add_link(clip_id: str, platform: str, url: str) -> None:
    posts = _load(POSTS, {})
    posts.setdefault(clip_id, {})[platform] = {"url": url.strip(), "posted_at": datetime.now().isoformat(timespec="minutes")}
    _save(POSTS, posts)


def links_for(clip_id: str) -> dict:
    return _load(POSTS, {}).get(clip_id, {})


def fetch_stats(log=print, max_age_days: int = 30) -> int:
    """Read current public numbers for every tracked post (skips ones older than max_age_days)."""
    import yt_dlp
    posts, perf = _load(POSTS, {}), _load(PERF, {})
    n = 0
    for cid, plats in posts.items():
        for plat, p in plats.items():
            try:
                age = datetime.now() - datetime.fromisoformat(p["posted_at"])
            except Exception:
                continue
            if age > timedelta(days=max_age_days) or plat == "instagram":
                continue  # Instagram numbers need a login; enter them by hand if you want
            try:
                with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "noplaylist": True}) as y:
                    info = y.extract_info(p["url"], download=False)
                row = {"t": datetime.now().isoformat(timespec="minutes"), "age_h": round(age.total_seconds() / 3600, 1),
                       "views": info.get("view_count") or 0, "likes": info.get("like_count") or 0,
                       "comments": info.get("comment_count") or 0}
                perf.setdefault(cid, {}).setdefault(plat, []).append(row)
                n += 1
            except Exception as e:
                log(f"   (couldn't read stats for a {plat} post: {str(e).splitlines()[0][:80]})")
            time.sleep(1.5)   # be polite to the sites
    _save(PERF, perf)
    return n


def set_manual_views(clip_id: str, platform: str, views: int) -> None:
    perf = _load(PERF, {})
    perf.setdefault(clip_id, {}).setdefault(platform, []).append(
        {"t": datetime.now().isoformat(timespec="minutes"), "age_h": 48, "views": int(views), "likes": 0, "comments": 0})
    _save(PERF, perf)


# ------------------------------------------------------------------ 2. learn
def _length_bucket(sec):
    if not sec:
        return None
    return "under 15s" if sec < 15 else "15-20s" if sec < 20 else "20-25s" if sec < 25 else "25-30s" if sec <= 31 else "30s+"


def _payoff_bucket(t):
    if t is None:
        return None
    return "payoff 0-3s" if t <= 3 else "payoff 3-8s" if t <= 8 else "payoff 8-12s" if t <= 12 else "payoff 12s+"


def _tail_bucket(t):
    if t is None:
        return None
    return "ends 0-6s after" if t <= 6 else "ends 6s+ after"


def _rscore_bucket(v):
    if v is None:
        return None
    return "self-check 90+" if v >= 90 else "self-check 70-89" if v >= 70 else "self-check <70"


def _features(meta: dict, post_time: str | None) -> dict:
    f = {
        "hook type": meta.get("hook_kind"),
        "hook line": meta.get("hook_template") if meta.get("hook_kind") == "template" else None,
        "length": _length_bucket(meta.get("length_sec")),
        "cold open": "on" if meta.get("cold_open") else "off" if meta.get("cold_open") is not None else None,
        "source": meta.get("source"),
        "layout": meta.get("layout"),
        "category": meta.get("category"),
        "streamer": meta.get("channel"),
        "payoff timing": _payoff_bucket((meta.get("retention") or {}).get("payoff_at")),
        "retention score": _rscore_bucket((meta.get("retention") or {}).get("score")),
        "after payoff": _tail_bucket((meta.get("retention") or {}).get("after_payoff")),
        "hook style": ("question" if str(meta.get("hook", "")).rstrip().endswith("?") else "statement")
                      if meta.get("hook") else None,
    }
    if post_time:
        try:
            f["posting hour"] = f"{datetime.fromisoformat(post_time).hour:02d}:00"
        except Exception:
            pass
    return {k: v for k, v in f.items() if v}


def _score_post(rows: list) -> float | None:
    """Views at ~48h (or the latest reading, scaled up if the post is younger)."""
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r.get("age_h", 0))
    at = [r for r in rows if r.get("age_h", 0) >= 40]
    r = at[0] if at else rows[-1]
    v = float(r.get("views") or 0)
    age = max(1.0, float(r.get("age_h") or 1))
    if age < 40:          # young post: rough projection, capped
        v *= min(2.0, (48 / age) ** 0.5)
    eng = (r.get("likes", 0) + 3 * r.get("comments", 0)) / max(v, 1)
    return v * (1 + min(eng, 0.2))


def learn(clips_meta: dict) -> dict:
    """clips_meta: {clip_id: meta}. Writes learned.json and returns it."""
    perf, posts = _load(PERF, {}), _load(POSTS, {})
    # one number per clip: its views relative to the median of that platform (so TikTok vs YouTube is fair)
    per_plat = {}
    for cid, plats in perf.items():
        for plat, rows in plats.items():
            s = _score_post(rows)
            if s is not None:
                per_plat.setdefault(plat, []).append((cid, s))
    rel = {}
    for plat, items in per_plat.items():
        med = statistics.median([s for _, s in items]) or 1
        for cid, s in items:
            rel.setdefault(cid, []).append(math.log((s + 50) / (med + 50)))   # log ratio vs typical
    clip_scores = {cid: sum(v) / len(v) for cid, v in rel.items()}

    groups = {}
    for cid, sc in clip_scores.items():
        meta = clips_meta.get(cid)
        if not meta:
            continue
        first_post = min((p.get("posted_at") for p in posts.get(cid, {}).values() if p.get("posted_at")), default=None)
        for feat, val in _features(meta, first_post).items():
            groups.setdefault(feat, {}).setdefault(val, []).append(sc)

    findings = {}
    for feat, vals in groups.items():
        rows = []
        for val, scores in vals.items():
            n = len(scores)
            shrunk = sum(scores) / (n + PRIOR)                # small samples pulled toward 0 (= average)
            rows.append({"value": val, "clips": n, "lift": round(math.exp(shrunk), 2)})
        rows.sort(key=lambda r: r["lift"], reverse=True)
        findings[feat] = rows

    out = {"updated": datetime.now().isoformat(timespec="minutes"), "measured_clips": len(clip_scores),
           "ready": len(clip_scores) >= MIN_CLIPS, "findings": findings}
    out["actions"] = _decide(out) if out["ready"] else {}
    old = _load(LEARNED, {})
    out["research"] = old.get("research", {})
    out["web"] = old.get("web", {})
    _save(LEARNED, out)
    return out


def _best(findings, feat, min_clips=3, margin=1.1):
    rows = [r for r in findings.get(feat, []) if r["clips"] >= min_clips]
    if len(rows) < 2:
        return None
    best, worst = rows[0], rows[-1]
    return best["value"] if best["lift"] >= worst["lift"] * margin else None


def _decide(learned: dict) -> dict:
    f = learned["findings"]
    a = {}
    lb = _best(f, "length")
    if lb:
        a["max_clip_seconds"] = {"under 15s": 16, "15-20s": 21, "20-25s": 26, "25-30s": 30, "30s+": 30}[lb]
    co = _best(f, "cold open")
    if co:
        a["cold_open"] = co == "on"
    src = {r["value"]: r for r in f.get("source", []) if r["clips"] >= 3}
    if "viewer clip" in src and "auto-detected" in src:
        ratio = src["viewer clip"]["lift"] / max(src["auto-detected"]["lift"], 0.01)
        a["viewer_clip_share"] = 0.75 if ratio > 1.35 else 0.25 if ratio < 0.74 else 0.5
    hk = {r["value"]: r["lift"] for r in f.get("hook type", []) if r["clips"] >= 2}
    if hk:
        a["hook_type_weights"] = hk
    hl = {r["value"]: r["lift"] for r in f.get("hook line", []) if r["clips"] >= 2}
    if hl:
        a["hook_line_weights"] = hl
    hr = _best(f, "posting hour", min_clips=2)
    if hr:
        a["best_posting_hour"] = int(hr[:2])
    return a


def learned() -> dict:
    return _load(LEARNED, {})


# ------------------------------------------------------------------ 3. apply
def apply_to_cfg(cfg: dict) -> dict:
    """Settings the learner is confident about override the defaults (unless turned off)."""
    if not cfg.get("self_learning", True):
        return cfg
    a = learned().get("actions") or {}
    m = dict(cfg)
    for k in ("max_clip_seconds", "viewer_clip_share"):
        if k in a:
            m[k] = a[k]
    if "cold_open" in a:
        m["cold_open"] = a["cold_open"]
    return m


def experiment(cfg: dict, rnd: random.Random | None = None) -> dict:
    """Keep testing: a share of clips randomly flip cold open, so the learner always has comparisons."""
    rnd = rnd or random
    m = dict(cfg)
    if cfg.get("self_learning", True) and rnd.random() < float(cfg.get("explore_rate", 0.25)):
        m["cold_open"] = not cfg.get("cold_open", True)
        m["_experiment"] = "cold open flipped"
    return m


def hook_weight(kind: str, template: str | None) -> float:
    a = learned().get("actions") or {}
    w = float((a.get("hook_type_weights") or {}).get(kind, 1.0))
    if template:
        w *= float((a.get("hook_line_weights") or {}).get(template, 1.0))
    return w
