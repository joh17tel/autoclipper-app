# What's new

## v6.3.1
- Campaigns now take turns: one stream per campaign at a time, so a new campaign no longer waits
  behind a long stream from another campaign
- Briefs with single-video links now work (YouTube watch/live/youtu.be links, Twitch and Kick VOD links)

## v6.3.0 — Longer, fuller clips
- Clips now grow with the action, up to 30 seconds: a quick spike gets ~16s, a long fight gets the whole
  thing (build-up + every big beat + the full reaction)
- Picks moments with several exciting beats over a single loud spike
- Cuts dead air (quiet stretches with no talking and no action) inside clips to keep the pace up;
  the pause right before the big moment is kept for suspense
- Campaign briefs still win: "under 15s" or "at least 20s" are respected
- New Settings: longest clip length, dead-air cutting

## v6.2.0
- Half viewer picks, half deeper cuts: fewer duplicate-content flags (everyone clips the #1 moment)
- Skips the week's single most-viewed viewer clip by default (the one every clipper posts)
- Posting plan in Clips: best clips to post today, Instagram first then TikTok 2.5h later then YouTube,
  timed for US evenings (your mornings) or PH evenings - tick each platform as you post
- Captions now end with a question ("Rate this play 1-10") to get comments
- New Settings: posting audience, posts per day, viewer-clip share, caption questions

## v6.1.0 — Quality upgrade
- Twitch: uses the clips the streamer's own viewers made (the most-viewed ones) as the source of moments,
  instead of guessing from loudness. Their clip title becomes the hook. Tagged "viewer pick" in Clips.
- YouTube: uses the "Most replayed" graph to find the moments people re-watch
- Cuts snap to whole sentences: clips start at the beginning of a phrase (keeps the setup)
  and end after the reaction finishes, never mid-word
- Loudness evened out to -14 LUFS (TikTok/Shorts standard), so no more quiet or blown-out clips
- Keeps 60fps when the stream is 60fps; higher quality encoding
- Downloads extra seconds around each moment so the setup is never cut off

## v6.0.2
- Fixed: "Create campaign" got stuck when the name started with a symbol (like "$8,500 ...")
- Campaigns hidden by that bug are recovered automatically
- Pasted brief AND uploaded PDF/DOCX are now both read (before, the PDF replaced the pasted text)
- Clicking inside the black window can no longer freeze the app
- Better detection of brief rules to check yourself ("No ...", "Keep ...", "Hook ...")

## v6.0.1
- Updates now come from github.com/joh17tel/autoclipper-app
- Update source can be changed in Settings

## v6.0.0
- Self-updating: new versions install automatically when AutoClipper starts
- Settings → Updates: check and install updates with one click
- Dashboard shows a banner when an update is ready

## v5.2
- Campaigns start checking right away; "Latest activity" line per campaign
- Warnings when a campaign has nothing to clip or the engine is stopped

## v5.1
- Reliable setup (finds the real Python 3.12), doctor.bat checker, clear startup errors

## v5.0
- Desktop app with Dashboard, Clips, Campaigns, Test and Settings tabs
