"""AutoClipper — watches streamers and turns every new stream into ready-to-post clips.

For each clip you get a folder with:
    clip.mp4        vertical 1080x1920 video with captions
    thumbnail.jpg   vertical cover image with hook text
    caption.txt     YouTube title + description, TikTok caption
And one page to work from:  clips/index.html  (preview, copy captions, download)

Usage:  python main.py                  loop forever (normal)
        python main.py --once           one check, then exit
        python main.py --test FILE.mp4  clip a local video (no downloading)
"""
import json
import os
import sys
import time
from datetime import datetime

import yaml

from autoclipper import campaign, captions, copywriter, detect, gallery, layout, learn, render, research, rules, sources, trends

STATE = "state.json"


def load_cfg():
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"done_vods": []}


def save_state(s):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)


LOG_HOOKS = []          # the app's live log listens here
STOP_CHECK = [lambda: False]   # the app can ask a running job to stop early


import queue as _queue
import threading as _threading
_PRINTQ = _queue.Queue()


def _printer():
    while True:
        line = _PRINTQ.get()
        try:
            print(line, flush=True)
        except Exception:
            pass


_threading.Thread(target=_printer, daemon=True).start()


def _drain():
    import time as _t
    for _ in range(50):
        if _PRINTQ.empty():
            break
        _t.sleep(0.02)


import atexit as _atexit
_atexit.register(_drain)


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    _PRINTQ.put(line)          # printing happens in the background, so it can never freeze the app
    for h in LOG_HOOKS:
        try:
            h(line)
        except Exception:
            pass


def should_stop() -> bool:
    try:
        return bool(STOP_CHECK[0]())
    except Exception:
        return False


def short_err(e) -> str:
    """Readable one-line error for the activity log."""
    t = str(e).replace("ERROR: ", "").splitlines()[0] if str(e) else type(e).__name__
    if "Unable to connect" in t or "Failed to resolve" in t or "timed out" in t:
        return "can't reach the site (check your internet)"
    if "404" in t or "does not exist" in t:
        return "link not found (check the streamer link)"
    return t[:140]


def safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:40]


# ---------------------------------------------------------------- clipping
def max_body(cfg) -> float:
    """Longest a clip may be before the cold open is added."""
    cold = 1.4 if cfg.get("cold_open", True) else 0.0
    return float(cfg.get("max_clip_seconds", 30)) - cold - 0.5


def pick_highlights(cfg, audio, chat, extra=None):
    dur = len(audio)
    n = detect.clip_count(dur, cfg.get("clips_per_hour", 3),
                          cfg.get("min_clips_per_stream", 3), cfg.get("max_clips_per_stream", 12))
    args = (audio, chat, n, cfg["clip_before_peak"], cfg["clip_after_peak"],
            cfg["min_gap_between_clips"])
    kw = {"extra": extra, "max_len": max_body(cfg),
          "min_before": int(cfg.get("min_build_up", 10)), "min_after": int(cfg.get("min_reaction", 5))}
    picks = detect.find_highlights(*args, min_score=1.5, **kw)
    if len(picks) < n:  # quiet stream: relax the bar to still get enough clips
        picks = detect.find_highlights(*args, min_score=0.8, **kw)
    return n, picks


def resolve_facecam(setting, sample_clip):
    """config facecam: "auto" (detect), "none", or [x, y, w, h] as fractions."""
    if setting in (None, "none", False):
        return None
    w, h = layout.probe_size(sample_clip)
    if isinstance(setting, (list, tuple)) and len(setting) == 4:
        return layout.from_fractions(setting, w, h)
    return layout.detect_facecam(sample_clip)


def disclosure_for(cfg, channel: dict | None):
    """Global disclosure settings, overridable per channel (disclosure: false to skip)."""
    d = dict(cfg.get("disclosure") or {})
    if channel and "disclosure" in channel:
        ov = channel["disclosure"]
        if ov is False:
            d["enabled"] = False
        elif isinstance(ov, dict):
            d.update(ov)
    return d


PAD = 5  # extra seconds downloaded on each side so cuts can snap to whole sentences


def snap_bounds(words, want_s, want_e, lo, hi):
    """Move the in/out points to natural pauses so a clip never starts or ends mid-sentence.
    In-point snaps to the START of the phrase around it (keeps the setup);
    out-point snaps to the END of the phrase (keeps the full reaction)."""
    if not words:
        return want_s, want_e
    ins = [words[0]["start"] - 0.15] + [words[i + 1]["start"] - 0.15 for i in range(len(words) - 1)
                                        if words[i + 1]["start"] - words[i]["end"] >= 0.30]
    outs = [words[i]["end"] + 0.15 for i in range(len(words) - 1)
            if words[i + 1]["start"] - words[i]["end"] >= 0.30] + [words[-1]["end"] + 0.15]
    cand_s = [x for x in ins if want_s - 4.0 <= x <= want_s + 0.5]
    s = max(cand_s) if cand_s else want_s
    # if we're mid-phrase, prefer that phrase's start even if it's a bit earlier
    if not cand_s:
        earlier = [x for x in ins if x <= want_s]
        if earlier and want_s - earlier[-1] <= 6.0:
            s = earlier[-1]
    cand_e = [x for x in outs if want_e - 0.5 <= x <= want_e + 3.0]
    e = min(cand_e) if cand_e else want_e
    for w in words:  # never cut inside a word
        if w["start"] < s < w["end"]:
            s = w["start"] - 0.05
        if w["start"] < e < w["end"]:
            e = w["end"] + 0.10
    return max(lo, s), min(hi, e)


def finish_clip(cfg, raw, cdir, streamer, hashtags, want_s, want_e, peak, cam, disc,
                used_hooks, score, source_info, hook_hint=None, category="gaming"):
    """raw -> snapped, normalized, vertical clip + thumbnail + captions + checks."""
    temps = []
    follow_x = None
    cfg = learn.experiment(cfg)   # a share of clips try the alternative, so the learner can compare
    dur = layout.probe_duration(raw) or (want_e + PAD)
    on = (disc or {}).get("enabled", False)
    disc_text = disc.get("on_screen_text", "Paid partnership") if on else None
    disc_tag = disc.get("caption_tag", "#ad") if on else ""
    use_caps = cfg.get("captions", True)

    # Retention rule (v6.7): without a cold open, the payoff must land within max_payoff_seconds,
    # or viewers swipe before it (Shorts/TikTok decide in ~2s, payoff expected by ~10s)
    if not cfg.get("cold_open", True):
        want_s = max(want_s, peak - float(cfg.get("max_payoff_seconds", 10)))
    # 1) transcribe once (padded), snap the cut to sentence boundaries
    words_all = captions.transcribe_words(raw, cfg.get("whisper_model", "small")) if use_caps else []
    s, e = snap_bounds(words_all, max(0.0, want_s), min(dur, want_e), 0.0, dur)
    cap = max_body(cfg)
    if e - s > cap:  # keep the payoff + reaction, shave the build-up
        s = max(s, e - cap)
        if peak < s + 2:
            s, e = max(0.0, peak - 2), max(0.0, peak - 2) + cap
    trimmed = os.path.join(cdir, "trim.mp4")
    render.cut(raw, s, e, trimmed, normalize=cfg.get("normalize_audio", True))
    temps.append(trimmed)
    words = [{"word": w["word"], "start": w["start"] - s, "end": w["end"] - s}
             for w in words_all if w["start"] >= s - 0.05 and w["end"] <= e + 0.1]
    peak_t = min(max(peak - s, 0.5), max(e - s - 0.5, 0.5))

    dead_removed = 0.0
    # cut dead air (quiet stretches with no talking and no action) to keep the pace up
    if cfg.get("cut_dead_air", True):
        gap = float(cfg.get("dead_air_seconds", 1.2))
        if category in ("irl", "talk"):   # talking content: pauses feel slow sooner than gameplay
            gap = min(gap, float(cfg.get("dead_air_seconds_talk", 0.7)))
        quiet = [(a, b) for a, b in detect.silences(trimmed, min_len=gap)
                 if b - a >= gap and not (a - 2.5 <= peak_t <= b + 2.5)
                 and not any(a < w["start"] < b for w in words)]
        if quiet:
            clip_len = layout.probe_duration(trimmed)
            keep, cur = [], 0.0
            for a, b in quiet:
                a2, b2 = a + 0.25, b - 0.25          # leave a little breathing room
                if a2 - cur > 0.3:
                    keep.append((cur, a2))
                cur = max(cur, b2)
            if clip_len - cur > 0.3:
                keep.append((cur, clip_len))
            removed = clip_len - sum(b - a for a, b in keep)
            if removed >= 0.5 and sum(b - a for a, b in keep) >= 8:
                tight = os.path.join(cdir, "tight.mp4")
                render.keep_segments(trimmed, keep, tight)
                temps.append(tight)
                dead_removed = removed

                def remap(t):
                    out = 0.0
                    for a, b in keep:
                        if t >= b:
                            out += b - a
                        elif t >= a:
                            return out + (t - a)
                        else:
                            return out
                    return out
                words = [{"word": w["word"], "start": remap(w["start"]), "end": remap(w["end"])} for w in words]
                peak_t = remap(peak_t)
                trimmed = tight

    # 2) cold open: flash the payoff first
    src = trimmed
    if cfg.get("cold_open", True) and (e - s) > 8:
        opened = os.path.join(cdir, "opened.mp4")
        a = max(0.0, peak_t - 0.3)
        added = render.cold_open(trimmed, peak_t, opened)
        temps.append(opened)
        teaser = [{"word": w["word"], "start": w["start"] - a, "end": w["end"] - a}
                  for w in words if a <= w["start"] and w["end"] <= a + added]
        words = teaser + [{"word": w["word"], "start": w["start"] + added, "end": w["end"] + added}
                          for w in words]
        src, peak_t = opened, peak_t + added

    if category in ("irl", "talk") and not cam and cfg.get("irl_layout", "follow") == "follow":
        follow_x = layout.face_center_x(src)
        follow_x = 0.5 if follow_x is None else follow_x   # no face found: centre crop
    hist = copywriter.load_history()
    hot = research.hot_words_for(streamer, learn.learned().get("research")) \
        | trends.hot_words(learn.learned().get("web"), streamer)
    meta = copywriter.write_copy(streamer, words, peak_t, hashtags, seed=f"{cdir}",
                                 used=used_hooks, disclosure_tag=disc_tag, hook_hint=hook_hint,
                                 question=cfg.get("comment_question", True),
                                 category=category, history=hist, extra_hype=hot,
                                 weight_fn=learn.hook_weight if cfg.get("self_learning", True) else None,
                                 max_words=int(cfg.get("hook_max_words", 9)),
                                 question_bias=float(cfg.get("question_hook_bias", 1.0)))
    copywriter.save_history(hist)
    ass = os.path.join(cdir, "captions.ass")
    temps.append(ass)
    render.write_ass(words, ass, meta["hook"] if cfg.get("hook_on_video", True) else None,
                     split=bool(cam), disclosure=disc_text,
                     disclosure_seconds=float((disc or {}).get("seconds", 3)))
    render.make_vertical(src, os.path.join(cdir, "clip.mp4"), ass, cam,
                         peak_t if cfg.get("zoom_on_peak", True) else None, cfg.get("watermark"), follow_x)
    tass = os.path.join(cdir, "thumb.ass")
    temps.append(tass)
    render.write_thumb_ass(tass, meta["hook"], streamer, split=bool(cam))
    render.make_thumbnail(src, peak_t, os.path.join(cdir, "thumbnail.jpg"), tass, cam, follow_x)

    camp = cfg.get("campaign") or {}
    meta.update({"channel": streamer, "score": round(score, 2), **source_info,
                 "length_sec": round(layout.probe_duration(os.path.join(cdir, "clip.mp4")), 1),
                 "layout": "facecam" if cam else ("person" if follow_x is not None else "gameplay"),
                 "category": category,
                 "cold_open": src != trimmed,
                 "experiment": cfg.get("_experiment"),
                 "created": datetime.now().isoformat(timespec="minutes"),
                 "campaign": camp.get("name", "General"),
                 "platforms": camp.get("platforms", ["tiktok", "youtube"]),
                 "manual_rules": camp.get("manual_rules", [])})
    meta["retention"] = retention_review(words, peak_t, meta["length_sec"], src != trimmed,
                                         dead_removed, bool(meta.get("hook")) and cfg.get("hook_on_video", True),
                                         float(cfg.get("max_payoff_seconds", 10)),
                                         float(cfg.get("clip_after_peak", 9)) + 3)
    meta["checks"] = campaign.check_clip(meta, cfg) + [
        {"ok": False, "text": f"Retention: {w}"} for w in meta["retention"]["warnings"]]
    with open(os.path.join(cdir, "caption.txt"), "w", encoding="utf-8") as f:
        f.write(copywriter.caption_txt(meta))
    with open(os.path.join(cdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    for p in temps:
        if os.path.exists(p):
            os.remove(p)
    return meta


def retention_review(words, peak_t, length, cold_open, dead_removed, hook_text, max_payoff=10.0, max_tail=12.0):
    """Self-critique of a finished clip against short-form retention rules (see RULES.md).
    Score 0-100; warnings name what a viewer would swipe on."""
    first_word = words[0]["start"] if words else None
    score, warn = 100, []
    if not hook_text and (first_word is None or first_word > 1.5) and not cold_open:
        score -= 25
        warn.append("nothing grabs attention in the first 2s (no hook text, no early talking, no cold open)")
    elif first_word is not None and first_word > 2.5 and not cold_open:
        score -= 10
        warn.append(f"first words at {first_word:.1f}s - slow start")
    if peak_t > max_payoff + 0.5 and not cold_open:
        score -= 25
        warn.append(f"payoff at {peak_t:.0f}s - viewers expect it by ~{max_payoff:.0f}s")
    if length and length > 35:
        score -= 10
        warn.append(f"{length:.0f}s long - needs very strong middle to keep 70% watching")
    tail = (length or 0) - peak_t
    if tail > max_tail:
        score -= 15
        warn.append(f"{tail:.0f}s after the payoff - ending drags, hurts completion/rewatch")
    gaps = [b["start"] - a["end"] for a, b in zip(words, words[1:])]
    long_gaps = sum(1 for g in gaps if g > 2.0)
    if long_gaps >= 2:
        score -= 10
        warn.append(f"{long_gaps} pauses over 2s still in the clip")
    return {"score": max(0, score), "first_words_at": first_word, "payoff_at": round(peak_t, 1),
            "after_payoff": round(tail, 1), "dead_air_cut": round(dead_removed, 1), "warnings": warn}


def _log_clip(i, meta, where=""):
    bad = [c["text"] for c in meta["checks"] if not c["ok"]]
    log(f"   clip {i:02d} {where}| {meta['length_sec']}s | retention {meta.get('retention', {}).get('score', '-')} | {meta['hook']}"
        + (f"  !! check: {'; '.join(bad)}" if bad else ""))


def clip_stream(cfg, get_part, audio_path, stream_dir, streamer, hashtags, chat=None,
                facecam_setting="auto", disc=None, extra=None):
    """Find every highlight in one stream and build a ready-to-post folder for each."""
    audio = detect.audio_energy_per_second(audio_path)
    target, picks = pick_highlights(cfg, audio, chat, extra)
    log(f"   stream length {len(audio)//60} min -> target {target} clips, found {len(picks)}")
    os.makedirs(stream_dir, exist_ok=True)
    made, used_hooks = 0, set()
    cam, cam_checked = None, False
    for i, (start, end, score, peak_abs) in enumerate(sorted(picks, key=lambda p: p[0]), 1):
        if should_stop():
            log("   stopping (requested)")
            break
        cdir = os.path.join(stream_dir, f"clip_{i:02d}")
        if os.path.exists(os.path.join(cdir, "meta.json")):
            continue  # already done (resume after a crash)
        os.makedirs(cdir, exist_ok=True)
        raw = os.path.join(cdir, "raw.mp4")
        try:
            g0 = max(0, start - PAD)
            raw = get_part(g0, end + PAD, raw)
            cat = cfg.get("category", "gaming")
            if not cam_checked:  # find the webcam once per stream
                cam = resolve_facecam(facecam_setting if cat == "gaming" or isinstance(facecam_setting, list)
                                      else "none", raw)
                cam_checked = True
                log(f"   category: {cat} | layout: " + ("facecam on top + gameplay" if cam else
                    ("crop on the person" if cat != "gaming" else "gameplay only")))
            meta = finish_clip(cfg, raw, cdir, streamer, hashtags, start - g0, end - g0,
                               peak_abs - g0, cam, disc or {}, used_hooks, score,
                               {"start_sec": start, "end_sec": end, "source": "auto-detected"},
                               category=cat)
            made += 1
            _log_clip(i, meta, f"@ {start//3600}:{start%3600//60:02d}:{start%60:02d} score {score:.1f} ")
        except Exception as e:
            log(f"   clip {i:02d} failed: {short_err(e)}")
        finally:
            if os.path.exists(raw):
                os.remove(raw)
    return made


def clip_viewer_clips(cfg, ch, m_name, state, base, hashtags, disc):
    """Twitch/Kick clips made by the streamer's own viewers = human-picked best moments."""
    from autoclipper import detect as _d
    url = ch["url"]
    try:
        clips = sources.top_viewer_clips(url, cfg.get("viewer_clips_range", "7d"), 40)
    except Exception as e:
        log(f"[{m_name}] {ch.get('name')}: couldn't read viewer clips - {short_err(e)}")
        return 0, 0
    min_views = int(cfg.get("viewer_clips_min_views", 25))
    fresh = [c for c in clips if (c.get("view_count") or 0) >= min_views
             and f"{m_name}:vclip:{c['id']}" not in state["done_vods"]]
    # the #1-2 clips of the week are what every clipper posts; start a little deeper to stand out
    skip_top = int(cfg.get("skip_top_viewer_clips", 1))
    if len(fresh) > skip_top + 2:
        fresh = fresh[skip_top:] + fresh[:skip_top]
    limit = int(cfg.get("max_clips_per_stream", 12))
    if not clips:
        return 0, 0
    log(f"[{m_name}] {ch.get('name')}: {len(clips)} viewer clips this week, {len(fresh)} new worth making")
    if not fresh:
        return 0, len(clips)
    out = os.path.join(base, f"{datetime.now():%Y-%m-%d}_{safe(ch.get('name') or m_name)}_viewerclips")
    os.makedirs(out, exist_ok=True)
    made, used = 0, set()
    cam, cam_checked = None, False
    for i, c in enumerate(fresh[:limit], 1):
        if should_stop():
            break
        key = f"{m_name}:vclip:{c['id']}"
        cdir = os.path.join(out, f"clip_{safe(str(c['id']))[:24]}")
        os.makedirs(cdir, exist_ok=True)
        raw = os.path.join(cdir, "raw.mp4")
        try:
            raw = sources.download_clip(c["url"], raw)
            dur = layout.probe_duration(raw)
            cat = cfg.get("category", "gaming")
            if not cam_checked:
                fc = ch.get("facecam", "auto")
                cam = resolve_facecam(fc if cat == "gaming" or isinstance(fc, list) else "none", raw)
                cam_checked = True
                log(f"   category: {cat} | layout: " + ("facecam on top + gameplay" if cam else
                    ("crop on the person" if cat != "gaming" else "gameplay only")))
            energy = _d.audio_energy_per_second(raw)
            peak = float(energy.argmax()) if len(energy) else dur * 0.7
            # viewer clips often run long: keep up to the target length, ending after the peak
            target = cfg["clip_before_peak"] + cfg["clip_after_peak"]
            ws = max(0.0, peak - cfg["clip_before_peak"]) if dur > target + 4 else 0.0
            we = min(dur, peak + cfg["clip_after_peak"]) if dur > target + 4 else dur
            meta = finish_clip(cfg, raw, cdir, ch.get("name") or m_name, hashtags, ws, we, peak,
                               cam, disc or {}, used, float(c.get("view_count") or 0),
                               {"source": "viewer clip", "source_url": c["url"],
                                "source_views": c.get("view_count"), "source_title": c.get("title")},
                               hook_hint=c.get("title"), category=cat)
            made += 1
            state["done_vods"].append(key)
            _log_clip(i, meta, f"(viewer clip, {c.get('view_count')} views) ")
        except Exception as e:
            log(f"   viewer clip failed: {short_err(e)}")
        finally:
            if os.path.exists(raw):
                os.remove(raw)
        save_state(state)
    return made, len(clips)


def clip_web_trending(cfg, ch, m_name, state, base, hashtags, disc):
    """Clips of this streamer that are blowing up on Reddit right now = proven viral moments."""
    from autoclipper import detect as _d
    cname = ch.get("name") or m_name
    items = trends.trending_clips(learn.learned().get("web"), cname)
    fresh = [p for p in items if f"{m_name}:web:{p['permalink']}" not in state["done_vods"]]
    limit = int(cfg.get("web_trending_clips_per_check", 2))
    if not fresh or limit <= 0:
        return 0
    log(f"[{m_name}] {cname}: {len(fresh)} trending moments on the web - clipping the top {min(limit, len(fresh))}")
    out = os.path.join(base, f"{datetime.now():%Y-%m-%d}_{safe(cname)}_trending")
    os.makedirs(out, exist_ok=True)
    made, used, cat = 0, set(), cfg.get("category", "gaming")
    for i, p in enumerate(fresh[:limit], 1):
        if should_stop():
            break
        key = f"{m_name}:web:{p['permalink']}"
        cdir = os.path.join(out, f"clip_{i:02d}_{safe(p['title'])[:30]}")
        os.makedirs(cdir, exist_ok=True)
        raw = os.path.join(cdir, "raw.mp4")
        try:
            raw = sources.download_clip(p["clip_url"], raw)
            dur = layout.probe_duration(raw)
            if dur > 600:
                raise RuntimeError("linked video is a full stream, not a clip")
            fc = ch.get("facecam", "auto")
            cam = resolve_facecam(fc if cat == "gaming" or isinstance(fc, list) else "none", raw)
            energy = _d.audio_energy_per_second(raw)
            peak = float(energy.argmax()) if len(energy) else dur * 0.7
            target = cfg["clip_before_peak"] + cfg["clip_after_peak"]
            ws = max(0.0, peak - cfg["clip_before_peak"]) if dur > target + 4 else 0.0
            we = min(dur, peak + cfg["clip_after_peak"]) if dur > target + 4 else dur
            meta = finish_clip(cfg, raw, cdir, cname, hashtags, ws, we, peak, cam, disc or {}, used,
                               float(p.get("score") or 0),
                               {"source": "web trending", "source_url": p["clip_url"], "thread": p["permalink"],
                                "source_score": p.get("score"), "source_title": p.get("title")},
                               hook_hint=p.get("title"), category=cat)
            made += 1
            _log_clip(i, meta, f"(trending on Reddit, {p.get('score')} upvotes) ")
        except Exception as e:
            log(f"   trending clip skipped: {short_err(e)}")
        finally:
            state["done_vods"].append(key)   # never retry the same thread
            if os.path.exists(raw):
                os.remove(raw)
        save_state(state)
    return made


def build_jobs(cfg, include_disabled=False):
    """One job per campaign folder, plus config.yaml's own channels (if any)."""
    cfg = rules.apply(cfg)          # rules the system tuned itself (RULES.md)
    cfg = learn.apply_to_cfg(cfg)   # settings the learner is confident about
    jobs = []
    for folder in campaign.discover(cfg.get("campaigns_folder", "campaigns")):
        try:
            camp = campaign.load_campaign(folder)
        except Exception as e:
            log(f"campaign {os.path.basename(folder)}: can't load ({e})")
            continue
        if not camp.get("enabled", True) and not include_disabled:
            continue
        m = campaign.merged_cfg(cfg, camp, folder)
        jobs.append({"name": m["campaign"]["name"], "cfg": m, "folder": folder,
                     "subject": camp.get("subject"),
                     "channels": camp.get("streamers") or [],
                     "footage": campaign.footage_files(folder)})
    if cfg.get("channels"):
        m = campaign.merged_cfg(cfg, {"name": "General"}, ".")
        jobs.append({"name": "General", "cfg": m, "folder": ".", "channels": cfg["channels"], "footage": []})
    return jobs


def run_job(job, state, out_dir, budget=1):
    """Do up to `budget` new streams (or one viewer-clip batch per streamer) for this campaign,
    then return so the next campaign gets its turn. Returns True if work is left over."""
    left = {"n": budget, "more": False}

    def take():
        if left["n"] <= 0:
            left["more"] = True
            return False
        left["n"] -= 1
        return True
    m, jname = job["cfg"], job["name"]
    tmp = "temp"
    base = os.path.join(out_dir, safe(jname))

    # 1) streamers to watch
    for ch in job["channels"]:
        if not ch.get("url"):
            continue
        cname = ch.get("name") or jname
        m = job["cfg"]  # fresh settings for every streamer
        if ch.get("category") in copywriter.CATEGORIES and ch["category"] != m.get("category"):
            m = campaign.apply_category(dict(m), ch["category"], {})   # this streamer is a different type
        r = (learn.learned().get("research") or {}).get(cname.lower())
        lacts = learn.learned().get("actions") or {}
        if r and r.get("top_median_seconds") and "max_clip_seconds" not in lacts \
                and not (m.get("campaign") or {}).get("max_seconds") and m.get("self_learning", True):
            m = dict(m)   # what's working for other clippers of this streamer
            m["max_clip_seconds"] = float(min(30, max(15, r["top_median_seconds"] + 3)))
        tags = campaign.campaign_tags(m, ch.get("hashtags", ""))
        # 1a0) moments already going viral on the web (Reddit) - fastest proven wins
        if m.get("web_research", True) and not ch.get("_web_done") \
                and trends.trending_clips(learn.learned().get("web"), cname) and take():
            ch["_web_done"] = True
            if clip_web_trending(m, ch, jname, state, base, tags, disclosure_for(m, ch)):
                gallery.build(out_dir)
        # 1a) Twitch: clips the streamer's viewers already made = human-picked best moments
        if m.get("use_viewer_clips", True) and sources.has_viewer_clips(ch["url"]) \
                and not ch.get("_vclips_done") and take():
            share = float(m.get("viewer_clip_share", 0.5))
            mv = dict(m)
            mv["max_clips_per_stream"] = max(1, round(int(m.get("max_clips_per_stream", 12)) * share))
            made_v, total_v = clip_viewer_clips(mv, ch, jname, state, base, tags, disclosure_for(m, ch))
            ch["_vclips_done"] = True   # once per round
            gallery.build(out_dir)
            if total_v and m.get("prefer_viewer_clips", False):
                continue  # viewer clips only
            if total_v:
                # the rest come from deeper cuts in the full stream: moments other clippers miss
                m = dict(m)
                m["max_clips_per_stream"] = max(2, round(int(m.get("max_clips_per_stream", 12)) * (1 - share)))
                m["min_clips_per_stream"] = min(int(m.get("min_clips_per_stream", 3)), m["max_clips_per_stream"])
        try:
            vods = sources.latest_vods(ch["url"], m.get("latest_vods_to_check", 2))
        except Exception as e:
            log(f"[{jname}] {cname}: couldn't read channel - {short_err(e)}")
            continue
        if not vods:
            log(f"[{jname}] {cname}: no past streams found on that page yet")
        new_found = False
        for v in vods:
            if should_stop():
                return
            key = f"{jname}:{cname}:{v['id']}"
            if key in state["done_vods"]:
                continue
            new_found = True
            if not take():
                log(f"[{jname}] {cname}: another new stream is queued - other campaigns go first")
                break
            try:
                info = sources.vod_info(v["url"])
            except Exception as e:
                log(f"[{jname}] {cname}: skipped a video - {short_err(e)}")
                continue
            if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
                log(f"[{jname}] {cname}: live right now - will clip it after the stream ends")
                continue
            log(f"[{jname}] {cname}: new stream '{(v['title'] or '')[:60]}'")
            try:
                audio = sources.download_audio(v["url"], tmp, safe(v["id"]))
                dur = int(info.get("duration") or 0)
                chat = detect.chat_counts_per_second(v["url"], dur) if m.get("use_chat") else None
                heat = detect.heatmap_per_second(info.get("heatmap"), dur)  # YouTube "most replayed"
                if heat is not None:
                    log("   using YouTube 'most replayed' data to find moments")
                stream_dir = os.path.join(base, f"{datetime.now():%Y-%m-%d}_{safe(cname)}_{safe(v['id'])}")
                get_part = lambda s, e, p, url=v["url"]: sources.download_section(url, s, e, p)
                n = clip_stream(m, get_part, audio, stream_dir, cname, tags, chat,
                                ch.get("facecam", "auto"), disclosure_for(m, ch), heat)
                log(f"   done: {n} clips ready")
                if m.get("cleanup_sources", True) and os.path.exists(audio):
                    os.remove(audio)
                if not should_stop():  # unfinished streams get resumed next time
                    state["done_vods"].append(key)
            except Exception as e:
                log(f"   failed, will retry next round: {short_err(e)}")
            save_state(state)
            gallery.build(out_dir)
        if vods and not new_found and left["n"] > 0:
            log(f"[{jname}] {cname}: no new streams - latest ones are already clipped. Waiting for the next stream.")

    if not job["channels"] and not job["footage"]:
        log(f"[{jname}] nothing to clip yet - add stream links to the brief or upload footage")

    m = job["cfg"]
    # 2) footage the campaign gave you (materials/footage)
    for f in job["footage"]:
        if should_stop():
            return
        key = f"{jname}:file:{os.path.basename(f)}:{int(os.path.getmtime(f))}"
        if key in state["done_vods"]:
            continue  # already clipped
        if not take():
            break
        log(f"[{jname}] campaign footage: {os.path.basename(f)}")
        name = (job["channels"][0].get("name") if job["channels"] else None) or job.get("subject") or jname
        stream_dir = os.path.join(base, f"footage_{safe(os.path.splitext(os.path.basename(f))[0])}")
        get_part = lambda s, e, p, src=f: (render.cut(src, s, e, p), p)[1]
        try:
            n = clip_stream(m, get_part, f, stream_dir, name, campaign.campaign_tags(m), None,
                            "auto", m.get("disclosure"))
            log(f"   done: {n} clips ready")
            if not should_stop():
                state["done_vods"].append(key)
        except Exception as e:
            log(f"   failed: {e}")
        save_state(state)
        gallery.build(out_dir)
    return left["more"]


# ---------------------------------------------------------------- run
def arg_after(flag):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def main():
    if not render.ffmpeg_ok():
        sys.exit("ffmpeg not found — run setup.bat first.")
    cfg = load_cfg()
    out_dir = cfg.get("output_folder", "clips")
    os.makedirs(out_dir, exist_ok=True)

    if "--brief" in sys.argv:  # re-read every campaign brief and show what was found
        for folder in campaign.discover(cfg.get("campaigns_folder", "campaigns")):
            data = campaign.build_campaign_yaml(folder)
            print(f"\n=== {data['name']} ===")
            print(yaml.safe_dump({k: v for k, v in data.items() if not k.startswith("_")},
                                 sort_keys=False, allow_unicode=True))
        return

    src = arg_after("--test")
    if src:
        jobs = build_jobs(cfg, include_disabled=True)
        want = arg_after("--campaign")
        job = next((j for j in jobs if want and want.lower() in
                    (j["name"].lower(), os.path.basename(j["folder"]).lower())), None) \
            or (jobs[0] if jobs else None)
        m = job["cfg"] if job else campaign.merged_cfg(cfg, {"name": "General"}, ".")
        ch0 = job["channels"][0] if job and job["channels"] else {}
        name = ch0.get("name") or (job.get("subject") if job else None) or (job["name"] if job else "Streamer")
        stream_dir = os.path.join(out_dir, safe(job["name"] if job else "General"),
                                  f"TEST_{safe(os.path.splitext(os.path.basename(src))[0])}")
        get_part = lambda s, e, p: (render.cut(src, s, e, p), p)[1]
        log(f"Test using campaign: {job['name'] if job else 'General'}")
        n = clip_stream(m, get_part, src, stream_dir, name,
                        campaign.campaign_tags(m, ch0.get("hashtags", "")), None,
                        ch0.get("facecam", "auto"), disclosure_for(m, ch0))
        page = gallery.build(out_dir)
        log(f"{n} clips made. Open {os.path.abspath(page)}")
        return

    state = load_state()
    log("AutoClipper running. Leave this window open.")
    while True:
        try:
            jobs = build_jobs(cfg)  # re-read so new briefs/campaigns are picked up
            if not jobs:
                log("No campaigns or channels yet. Add a folder in 'campaigns' (see SETUP.md).")
            more = True
            while more and not should_stop():   # round-robin: one stream per campaign per pass
                more = False
                for job in jobs:
                    more = bool(run_job(job, state, out_dir)) or more
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log(f"error: {e}")
        if "--once" in sys.argv:
            break
        time.sleep(max(5, cfg.get("check_every_minutes", 30)) * 60)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------- learning cycle
def learning_cycle(cfg, force=False):
    """Read views of your posts, learn what works, and scan what other clippers post."""
    if not cfg.get("self_learning", True) and not force:
        return
    out_dir = cfg.get("output_folder", "clips")
    stamp = learn._load("learn_stamp.json", {})
    now = time.time()
    if force or now - stamp.get("stats", 0) > float(cfg.get("learn_every_hours", 6)) * 3600:
        n = learn.fetch_stats(log)
        metas = {}
        import glob as _g
        for mp in _g.glob(os.path.join(out_dir, "**", "meta.json"), recursive=True):
            try:
                with open(mp, encoding="utf-8") as f:
                    metas[os.path.relpath(os.path.dirname(mp), out_dir).replace("\\", "/")] = json.load(f)
            except Exception:
                pass
        res = learn.learn(metas)
        stamp["stats"] = now
        log(f"Learning: read {n} post stats, {res['measured_clips']} clips measured"
            + ("" if res["ready"] else f" (needs {learn.MIN_CLIPS}+ to start adjusting)"))
    if force or now - stamp.get("research", 0) > 24 * 3600:
        names = set()
        for job in build_jobs(cfg):
            for ch in job["channels"]:
                if ch.get("name"):
                    names.add(ch["name"])
        L = learn.learned()
        L.setdefault("research", {})
        for nm in sorted(names):
            try:
                r = research.scan(nm)
                if r:
                    L["research"][nm.lower()] = r
                    log(f"Research: {nm} - top clips by other clippers average {r['top_median_seconds']}s; "
                        f"hot words: {', '.join(r['hot_words'][:5]) or '-'}")
            except Exception as e:
                log(f"Research: couldn't scan {nm} ({short_err(e)})")
        learn._save(learn.LEARNED, L)
        stamp["research"] = now
    if cfg.get("web_research", True) and (force or now - stamp.get("web", 0) > float(cfg.get("web_research_hours", 3)) * 3600):
        names = {ch["name"] for job in build_jobs(cfg) for ch in job["channels"] if ch.get("name")}
        L = learn.learned()
        L.setdefault("web", {})
        for nm in sorted(names):
            try:
                r = trends.scan_streamer(nm)
                if r:
                    L["web"][nm.lower()] = r
                    n_clips = sum(1 for p in r["trending"] if p.get("clip_url"))
                    log(f"Web: {nm} - {r['posts']} trending posts, {n_clips} with clips; "
                        f"buzz words: {', '.join(r['hot_words'][:5]) or '-'}")
                else:
                    log(f"Web: nothing trending about {nm} this week")
            except Exception as e:
                log(f"Web: couldn't scan {nm} ({short_err(e)})")
        learn._save(learn.LEARNED, L)
        stamp["web"] = now
    if force or now - stamp.get("rules", 0) > 24 * 3600:
        try:   # research -> self-critique -> rewrite the rules (bounded, logged in rules.json)
            ch = rules.calibrate(cfg, learn.learned(), log)
            rv = rules.last_review()
            log(f"Rules: calibrated - {len(ch)} change(s)"
                + (f"; my last {rv['clips']} clips average self-check {rv['avg_score']}" if rv else ""))
        except Exception as e:
            log(f"Rules: calibration failed ({short_err(e)})")
        stamp["rules"] = now
    learn._save("learn_stamp.json", stamp)
