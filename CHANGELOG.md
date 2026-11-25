# What's new

## 6.7.0 - Retention self-check + tighter pacing
- Every clip gets a self-check score (0-100) with plain warnings: slow first 2s, late payoff, dragging ending, long pauses
- No cold open? The clip now starts so the payoff lands by 10s (was ~18s)
- IRL/talk clips cut pauses from 0.7s (gaming stays at 1.2s)
- The learner now compares payoff timing and self-check scores against your real views
- RULES.md documents the rules and a dated changelog of why they changed

## 6.6.0 - Web research (learns from what's going viral right now)
- New: every 3 hours it checks Reddit (r/LivestreamFail + all of Reddit) for your streamers' most upvoted posts this week
- Trending moments that link a Twitch/Kick/YouTube clip are clipped FIRST, with the post title as the hook idea (each one only once)
- Buzz words from viral post titles help pick the most hooky quotes for captions
- Insights tab: new "Trending now on the web" panel with links, upvotes and buzz words
- Settings: web research on/off, how often, and how many trending moments per streamer

## v6.5.0 — Self-learning
- New 📈 Insights tab: AutoClipper now learns from results and adjusts itself
- Paste the link after you post a clip (posting plan, or "Post links" on each clip). Every 6 hours it reads
  the views, likes and comments of your TikTok/YouTube posts (Instagram: type views in by hand)
- It compares your clips and learns what gets more views: hook type (quote / fan title / template),
  individual hook lines, clip length, cold open on/off, viewer picks vs deep cuts, posting time
- Once 8+ clips are measured, it applies what works: hook choice, clip length, cold open,
  viewer-pick share. 25% of clips keep experimenting so it doesn't get stuck on early luck
- Daily research: scans other clippers' YouTube clips of your streamers - how long the top ones are
  (nudges your clip length) and which words their best titles use (counted as "hooky" in your quotes)
- Settings: self-learning on/off, experiment share

## v6.4.0 — IRL streams + better hooks
- Category per campaign: 🎮 Gaming, 🚶 IRL (e.g. JasonTheWeen), 🎙 Talk/podcast
  - picked automatically from the brief, or choose it in the campaign page / new campaign form
  - IRL & talk: the person fills the whole screen (crop follows their face), longer setup for stories,
    IRL-style hooks, titles, questions and hashtags (#irl #irlstream)
- Kick support for viewer clips: uses the most-viewed clips Kick viewers made (like Twitch)
- Hooks no longer repeat: every hook is checked against your last 200 across all campaigns,
  and the same opening ("STREAMER couldn't...") can't appear twice in a row
- Hooks pull the punchiest real quote from the clip ("wait wait wait are you serious"),
  shown in quotation marks; titles are now written differently from the on-screen hook
- Much bigger hook banks (25+ per category)
- Streamer names keep the brief's capitalisation (JasonTheWeen, not jasontheween)

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
