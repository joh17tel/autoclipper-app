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

from autoclipper import campaign, captions, copywriter, detect, gallery, layout, render, sources

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


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
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
def pick_highlights(cfg, audio, chat):
    dur = len(audio)
    n = detect.clip_count(dur, cfg.get("clips_per_hour", 3),
                          cfg.get("min_clips_per_stream", 3), cfg.get("max_clips_per_stream", 12))
    args = (audio, chat, n, cfg["clip_before_peak"], cfg["clip_after_peak"],
            cfg["min_gap_between_clips"])
    picks = detect.find_highlights(*args, min_score=1.5)
    if len(picks) < n:  # quiet stream: relax the bar to still get enough clips
        picks = detect.find_highlights(*args, min_score=0.8)
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


def clip_stream(cfg, get_part, audio_path, stream_dir, streamer, hashtags, chat=None,
                facecam_setting="auto", disc=None):
    """Find every highlight in one stream and build a ready-to-post folder for each."""
    audio = detect.audio_energy_per_second(audio_path)
    target, picks = pick_highlights(cfg, audio, chat)
    log(f"   stream length {len(audio)//60} min -> target {target} clips, found {len(picks)}")
    os.makedirs(stream_dir, exist_ok=True)
    disc = disc or {}
    on = disc.get("enabled", False)
    disc_text = disc.get("on_screen_text", "Paid partnership") if on else None
    disc_tag = disc.get("caption_tag", "#ad") if on else ""
    made, used_hooks = 0, set()
    cam, cam_checked = None, False
    for i, (start, end, score) in enumerate(sorted(picks, key=lambda p: p[0]), 1):
        if should_stop():
            log("   stopping (requested)")
            break
        cdir = os.path.join(stream_dir, f"clip_{i:02d}")
        if os.path.exists(os.path.join(cdir, "meta.json")):
            continue  # already done (resume after a crash)
        os.makedirs(cdir, exist_ok=True)
        temps = []
        try:
            raw = get_part(start, end, os.path.join(cdir, "raw.mp4"))
            temps.append(raw)
            peak_t = float(min(cfg["clip_before_peak"], max(end - start - 1, 0)))

            if not cam_checked:  # find the webcam once per stream
                cam = resolve_facecam(facecam_setting, raw)
                cam_checked = True
                log(f"   layout: {'facecam on top + gameplay' if cam else 'gameplay only'}")

            if cfg.get("cold_open", True):
                opened = os.path.join(cdir, "opened.mp4")
                added = render.cold_open(raw, peak_t, opened)
                temps.append(opened)
                src, peak_t = opened, peak_t + added
            else:
                src = raw

            words = (captions.transcribe_words(src, cfg.get("whisper_model", "small"))
                     if cfg.get("captions", True) else [])
            meta = copywriter.write_copy(streamer, words, peak_t, hashtags,
                                         seed=f"{cdir}", used=used_hooks,
                                         disclosure_tag=disc_tag)

            ass = os.path.join(cdir, "captions.ass")
            temps.append(ass)
            render.write_ass(words, ass, meta["hook"] if cfg.get("hook_on_video", True) else None,
                             split=bool(cam), disclosure=disc_text,
                             disclosure_seconds=float(disc.get("seconds", 3)))
            render.make_vertical(src, os.path.join(cdir, "clip.mp4"), ass, cam,
                                 peak_t if cfg.get("zoom_on_peak", True) else None,
                                 cfg.get("watermark"))

            tass = os.path.join(cdir, "thumb.ass")
            temps.append(tass)
            render.write_thumb_ass(tass, meta["hook"], streamer, split=bool(cam))
            render.make_thumbnail(src, peak_t, os.path.join(cdir, "thumbnail.jpg"), tass, cam)

            camp = cfg.get("campaign") or {}
            meta.update({"channel": streamer, "score": round(score, 2),
                         "start_sec": start, "end_sec": end,
                         "length_sec": round(layout.probe_duration(os.path.join(cdir, "clip.mp4")), 1),
                         "layout": "facecam" if cam else "gameplay",
                         "created": datetime.now().isoformat(timespec="minutes"),
                         "campaign": camp.get("name", "General"),
                         "platforms": camp.get("platforms", ["tiktok", "youtube"]),
                         "manual_rules": camp.get("manual_rules", [])})
            meta["checks"] = campaign.check_clip(meta, cfg)
            with open(os.path.join(cdir, "caption.txt"), "w", encoding="utf-8") as f:
                f.write(copywriter.caption_txt(meta))
            with open(os.path.join(cdir, "meta.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
            made += 1
            bad = [c["text"] for c in meta["checks"] if not c["ok"]]
            log(f"   clip {i:02d} @ {start//3600}:{start%3600//60:02d}:{start%60:02d} "
                f"score {score:.1f} | {meta['length_sec']}s | {meta['hook']}"
                + (f"  !! check: {'; '.join(bad)}" if bad else ""))
        except Exception as e:
            log(f"   clip {i:02d} failed: {short_err(e)}")
        finally:
            for p in temps:
                if p and os.path.exists(p):
                    os.remove(p)
    return made


def build_jobs(cfg, include_disabled=False):
    """One job per campaign folder, plus config.yaml's own channels (if any)."""
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


def run_job(job, state, out_dir):
    m, jname = job["cfg"], job["name"]
    tmp = "temp"
    base = os.path.join(out_dir, safe(jname))

    # 1) streamers to watch
    for ch in job["channels"]:
        if not ch.get("url"):
            continue
        cname = ch.get("name") or jname
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
                stream_dir = os.path.join(base, f"{datetime.now():%Y-%m-%d}_{safe(cname)}_{safe(v['id'])}")
                get_part = lambda s, e, p, url=v["url"]: sources.download_section(url, s, e, p)
                n = clip_stream(m, get_part, audio, stream_dir, cname,
                                campaign.campaign_tags(m, ch.get("hashtags", "")), chat,
                                ch.get("facecam", "auto"), disclosure_for(m, ch))
                log(f"   done: {n} clips ready")
                if m.get("cleanup_sources", True) and os.path.exists(audio):
                    os.remove(audio)
                if not should_stop():  # unfinished streams get resumed next time
                    state["done_vods"].append(key)
            except Exception as e:
                log(f"   failed, will retry next round: {short_err(e)}")
            save_state(state)
            gallery.build(out_dir)
        if vods and not new_found:
            log(f"[{jname}] {cname}: no new streams - latest ones are already clipped. Waiting for the next stream.")

    if not job["channels"] and not job["footage"]:
        log(f"[{jname}] nothing to clip yet - add stream links to the brief or upload footage")

    # 2) footage the campaign gave you (materials/footage)
    for f in job["footage"]:
        if should_stop():
            return
        key = f"{jname}:file:{os.path.basename(f)}:{int(os.path.getmtime(f))}"
        if key in state["done_vods"]:
            continue  # already clipped
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
            for job in jobs:
                run_job(job, state, out_dir)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log(f"error: {e}")
        if "--once" in sys.argv:
            break
        time.sleep(max(5, cfg.get("check_every_minutes", 30)) * 60)


if __name__ == "__main__":
    main()
