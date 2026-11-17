# What's new

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
