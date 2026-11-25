"""Self-tuning clip rules: the system researches, critiques its own clips, and rewrites its rules.

Every calibration (daily, or "Check now" on Insights) it looks at three kinds of evidence:
  1. SELF-CRITIQUE  - the retention warnings on its own recent clips (late payoff, dragging
                      endings, leftover pauses). A problem in many clips -> the matching rule tightens.
  2. YOUR VIEWS     - what the learner found from your posted clips' views (payoff timing, length,
                      time after the payoff). Proven winners move the rules toward them.
  3. THE WEB        - what top clips of your streamers look like right now (length, title style
                      from YouTube; buzz from Reddit).

Safety: only the selection/editing numbers below can change, each inside a safe range and by a small
step per calibration. Core functions are never touched. Every change is written to the changelog
in rules.json with the date, old -> new value, why, and the evidence. "Reset rules" undoes it all.
Campaign briefs always win over these rules.
"""
import json
import os
import re
import statistics
from datetime import datetime

RULES = "rules.json"

# name: (default, min, max, max step per calibration, plain description)
TUNABLE = {
    "max_payoff_seconds":    (10.0, 6.0, 14.0, 1.0, "no cold open: payoff must land by this second"),
    "clip_before_peak":      (18.0, 10.0, 22.0, 1.0, "seconds of build-up kept before the big moment"),
    "clip_after_peak":       (9.0, 4.0, 12.0, 1.0, "seconds of reaction kept after the big moment"),
    "dead_air_seconds":      (1.2, 0.6, 2.0, 0.1, "gaming: cut quiet stretches longer than this"),
    "dead_air_seconds_talk": (0.7, 0.4, 1.2, 0.1, "IRL/talk: cut pauses longer than this"),
    "max_clip_seconds":      (30.0, 15.0, 45.0, 3.0, "longest a clip can be"),
    "hook_max_words":        (9.0, 4.0, 12.0, 1.0, "longest on-screen hook (words)"),
    "question_hook_bias":    (1.0, 0.6, 1.6, 0.15, "how much question-style hooks are preferred"),
}
MIN_REVIEWED = 6        # recent clips needed before self-critique changes anything
WARN_SHARE = 0.4        # a warning on 40%+ of recent clips = a pattern worth fixing
MIN_VIEW_CLIPS = 3      # clips per group before trusting your view data


def _load():
    try:
        with open(RULES, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"values": {}, "changelog": []}


def _save(r):
    tmp = RULES + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)
    os.replace(tmp, RULES)


def current() -> dict:
    vals = _load().get("values", {})
    return {k: vals.get(k, d[0]) for k, d in TUNABLE.items()}


def changed_only() -> dict:
    return dict(_load().get("values", {}))


def changelog(limit=50) -> list:
    return list(reversed(_load().get("changelog", [])))[:limit]


def reset():
    r = _load()
    r["values"] = {}
    r["changelog"].append({"date": datetime.now().isoformat(timespec="minutes"), "rule": "all",
                           "old": None, "new": "defaults", "why": "reset by you", "evidence": ""})
    _save(r)


def apply(cfg: dict) -> dict:
    """Self-tuned values replace defaults. Turn off with auto_tune_rules: false."""
    if not cfg.get("auto_tune_rules", True) or not cfg.get("self_learning", True):
        return cfg
    m = dict(cfg)
    m.update(changed_only())
    return m


def _move(r, key, direction, why, evidence, log, cfg_base):
    """Nudge one rule a single safe step up (+1) or down (-1)."""
    d, lo, hi, step, desc = TUNABLE[key]
    vals = r.setdefault("values", {})
    old = float(vals.get(key, cfg_base.get(key, d)))
    new = round(min(hi, max(lo, old + direction * step)), 2)
    if new == old:
        return False
    vals[key] = new
    r.setdefault("changelog", []).append({"date": datetime.now().isoformat(timespec="minutes"), "rule": key,
                                          "old": old, "new": new, "why": why, "evidence": evidence,
                                          "description": desc})
    r["changelog"] = r["changelog"][-200:]
    log(f"Rules: {key} {old} -> {new} ({why})")
    return True


def _recent_metas(out_dir, n=40):
    import glob
    metas = []
    for mp in glob.glob(os.path.join(out_dir, "**", "meta.json"), recursive=True):
        try:
            with open(mp, encoding="utf-8") as f:
                m = json.load(f)
            if m.get("retention"):
                metas.append(m)
        except Exception:
            pass
    metas.sort(key=lambda m: m.get("created", ""), reverse=True)
    return metas[:n]


def _lift(findings, feat, value):
    for row in findings.get(feat, []):
        if row["value"] == value and row["clips"] >= MIN_VIEW_CLIPS:
            return row["lift"]
    return None


def title_style(titles: list[str]) -> dict:
    """Measurable style of a set of titles (used on competitor top clips vs the rest)."""
    if not titles:
        return {}
    words = [len(re.findall(r"[\w']+", t)) for t in titles]
    return {"words": round(statistics.median(words), 1),
            "question": round(sum("?" in t for t in titles) / len(titles), 2),
            "caps": round(sum(bool(re.search(r"\b[A-Z]{3,}\b", t)) for t in titles) / len(titles), 2)}


def calibrate(cfg: dict, learned: dict, log=print) -> list:
    """One research -> critique -> rule-update pass. Returns the changes made."""
    if not cfg.get("auto_tune_rules", True):
        return []
    r = _load()
    before = len(r.get("changelog", []))
    base = {k: cfg.get(k, d[0]) for k, d in TUNABLE.items()}
    done = set()   # one change per rule per calibration

    def move(key, direction, why, evidence):
        if key not in done and _move(r, key, direction, why, evidence, log, base):
            done.add(key)

    # 1) SELF-CRITIQUE: patterns in my own recent clips
    # only judge clips made under the CURRENT rules (made after the last rule change),
    # so one bad batch can't push a rule again and again
    since = max((c["date"] for c in r.get("changelog", [])), default="")
    metas = [m for m in _recent_metas(cfg.get("output_folder", "clips")) if m.get("created", "") > since]
    if len(metas) >= MIN_REVIEWED:
        n = len(metas)
        def share(pattern):
            return sum(any(re.search(pattern, w) for w in m["retention"].get("warnings", [])) for m in metas) / n
        s_late, s_drag, s_pause, s_slow = share(r"^payoff at"), share(r"after the payoff"), \
            share(r"pauses over"), share(r"first 2s|slow start")
        if s_late >= WARN_SHARE:
            move("clip_before_peak", -1, "payoff lands late in many of my clips", f"{s_late:.0%} of last {n} clips")
            move("max_payoff_seconds", -1, "payoff lands late in many of my clips", f"{s_late:.0%} of last {n} clips")
        if s_drag >= WARN_SHARE:
            move("clip_after_peak", -1, "endings drag after the payoff", f"{s_drag:.0%} of last {n} clips")
        if s_pause >= WARN_SHARE:
            move("dead_air_seconds", -1, "too many pauses left in clips", f"{s_pause:.0%} of last {n} clips")
            move("dead_air_seconds_talk", -1, "too many pauses left in clips", f"{s_pause:.0%} of last {n} clips")
        if s_slow >= WARN_SHARE:
            move("max_payoff_seconds", -1, "slow first seconds in many clips", f"{s_slow:.0%} of last {n} clips")
        avg = statistics.mean(m["retention"].get("score", 100) for m in metas)
        r["last_review"] = {"date": datetime.now().isoformat(timespec="minutes"), "clips": n,
                            "avg_score": round(avg, 1),
                            "late_payoff": round(s_late, 2), "dragging_end": round(s_drag, 2),
                            "pauses": round(s_pause, 2), "slow_start": round(s_slow, 2)}

    # 2) YOUR VIEWS: what actually got more views
    # only act on views when there's NEW data since the last time (no pushing on the same evidence)
    measured = int((learned or {}).get("measured_clips") or 0)
    f = (learned or {}).get("findings") or {} if measured >= int(r.get("views_seen", 0)) + 4 else {}
    if f:
        r["views_seen"] = measured
    early, late = _lift(f, "payoff timing", "payoff 3-8s"), _lift(f, "payoff timing", "payoff 8-12s")
    if early and late:
        if early >= late * 1.15:
            move("max_payoff_seconds", -1, "your clips with an earlier payoff got more views", f"{early}x vs {late}x")
        elif late >= early * 1.15:
            move("max_payoff_seconds", +1, "your clips with a longer build-up got more views", f"{late}x vs {early}x")
    short_t, long_t = _lift(f, "after payoff", "ends 0-6s after"), _lift(f, "after payoff", "ends 6s+ after")
    if short_t and long_t:
        if short_t >= long_t * 1.15:
            move("clip_after_peak", -1, "your clips that end soon after the payoff got more views", f"{short_t}x vs {long_t}x")
        elif long_t >= short_t * 1.15:
            move("clip_after_peak", +1, "your clips with a longer reaction got more views", f"{long_t}x vs {short_t}x")
    qa, qb = _lift(f, "hook style", "question"), _lift(f, "hook style", "statement")
    if qa and qb:
        if qa >= qb * 1.15:
            move("question_hook_bias", +1, "question hooks got more views on your posts", f"{qa}x vs {qb}x")
        elif qb >= qa * 1.15:
            move("question_hook_bias", -1, "statement hooks got more views on your posts", f"{qb}x vs {qa}x")

    # 3) THE WEB: what top clips of your streamers look like right now
    res = (learned or {}).get("research") or {}
    tops = [x for x in res.values() if x.get("top_style") and x.get("rest_style")
            and x.get("scanned", "") > r.get("web_seen", "")]
    if tops:
        r["web_seen"] = max(x["scanned"] for x in tops)
    if tops:
        tw = statistics.median(x["top_style"]["words"] for x in tops)
        cur_w = float(r.get("values", {}).get("hook_max_words", base["hook_max_words"]))
        if tw + 2 < cur_w:
            move("hook_max_words", -1, "top clips of your streamers use shorter titles", f"top titles ~{tw:.0f} words")
        elif tw > cur_w:
            move("hook_max_words", +1, "top clips of your streamers use longer titles", f"top titles ~{tw:.0f} words")
        q_top = statistics.mean(x["top_style"]["question"] for x in tops)
        q_rest = statistics.mean(x["rest_style"]["question"] for x in tops)
        if q_top >= q_rest + 0.15:
            move("question_hook_bias", +1, "top clips use question titles more than the rest",
                 f"{q_top:.0%} vs {q_rest:.0%} of titles")
        elif q_rest >= q_top + 0.15:
            move("question_hook_bias", -1, "top clips use question titles less than the rest",
                 f"{q_top:.0%} vs {q_rest:.0%} of titles")

    r["last_calibration"] = datetime.now().isoformat(timespec="minutes")
    _save(r)
    return r.get("changelog", [])[before:]


def last_review() -> dict:
    return _load().get("last_review") or {}
