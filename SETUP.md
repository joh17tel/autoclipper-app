# AutoClipper v5.2 — The App

AutoClipper is now an app with its own window. You never touch files or code. Everything happens in five tabs:

| Tab | What you do there |
|---|---|
| **📊 Dashboard** | Start/Stop the engine, see clips ready, the next check time, and live activity |
| **🎬 Clips** | Watch each clip, copy captions, download video and thumbnail, mark Posted, delete duds |
| **📋 Campaigns** | Add a campaign: paste the brief, upload logo/footage/examples, see what was understood, fix it |
| **🧪 Test a video** | Run any gaming video through a campaign's rules to check quality |
| **⚙️ Settings** | Clips per stream, check interval, captions, zoom, cold open, phone access |

---

## Install (one time, about 15 minutes)
1. Unzip to an easy folder, like `C:\AutoClipper`.
2. Double-click **setup.bat**. If it installs Python, close it and run setup.bat again. Wait for "Done".
3. Double-click **create_desktop_shortcut.bat**. You now have an **AutoClipper** icon on your desktop.
4. Optional: double-click **install_autostart.bat** so the engine starts in the background whenever you log in.
5. Turn off PC sleep: Settings → System → Power → Sleep = **Never**.

## Daily use
1. Open **AutoClipper** from the desktop. A black window opens first (the engine), then the app window opens within a few seconds. **Keep the black window open.** You can minimize it.
2. Go to **Clips**, filtered to **Not posted**.
3. For each good clip: **⬇ Video** → **Copy caption** → post in TikTok/YouTube → **✓ Mark posted**. Delete the duds.

## Add a campaign (5 minutes)
1. **Campaigns → + New campaign**.
2. Type a name, then paste the **entire brief** from the Whop/Vyro campaign page, links and all. Or upload it as PDF/DOCX.
3. Optional: add the campaign's logo, footage they give you, or example clips they like.
4. **Create campaign**. Check the "What AutoClipper understood" box:
   - streamers watched, hashtags, clip length, platforms, disclosure, logo
   - "Rules you'll check yourself" = things only a human can judge
5. Wrong? Edit the brief and press **Save & re-read brief**, or fix it under **Advanced: edit campaign.yaml**.

AutoClipper starts checking a new campaign right away. Its **Latest activity** line (top of the campaign page) shows what it is doing, e.g. "new stream found", "live right now - will clip after it ends", or "no new streams".

## Post from your phone (optional)
**Settings → Phone access → on**, then restart the app. The Dashboard shows an address like `http://192.168.1.5:8765`. Open it on your phone (same Wi-Fi) to download clips and copy captions straight into TikTok. Anyone on your Wi-Fi can open it, so only use this on your home network.

---

## What happens automatically
- Checks each campaign's streamers every 30 minutes and waits until each stream ends.
- Downloads only the audio, finds hype moments (loudness + chat), then downloads just those parts.
- Makes several clips per stream (about 3 per hour of stream, max 12).
- Each clip: facecam on top when found, karaoke captions, title bar hook, cold open, punch-in zoom, campaign logo, disclosure tag.
- Writes captions with the campaign's hashtags, @tags and #ad at the start, and checks them (✓ / ✗ FIX).
- Clips any footage you upload to a campaign.

## Troubleshooting
- **Nothing shows / app doesn't open:** double-click **doctor.bat**. It checks everything and tells you what to fix. Send a screenshot of it to Claude if stuck.
- **The black window shows an error:** screenshot it and send it to Claude. The error is also saved in `app_error.txt`.
- **App window doesn't appear but the black window says "running":** go to `http://127.0.0.1:8765` in Edge or Chrome.
- **"can't reach the site":** check your internet. The app retries on the next check.
- **"link not found":** the streamer link in the brief is wrong. Fix it in the campaign.
- **Facecam not detected:** in the campaign's campaign.yaml, set the streamer's `facecam:` to e.g. `[0.0, 0.66, 0.25, 0.34]` (x, y, width, height as fractions of the screen; this example is a bottom-left cam).
- **Captions say "using CPU":** fine, just slower.
- **Something else:** copy the red lines from Live activity and paste them to Claude.
