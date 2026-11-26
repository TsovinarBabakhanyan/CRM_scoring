# Podcast

Record an episode, run three commands, push. The episode appears on
**crmscoring.com/podcast/** and in the podcast feeds, and you get 9:16 reels
with captions for Instagram, TikTok and YouTube Shorts.

There are three shows, one per language, because podcast apps expect one
language per feed:

| Language | Feed (submit this to Apple Podcasts / Spotify) |
|---|---|
| English | `https://www.crmscoring.com/podcast/rss.xml` |
| Russian | `https://www.crmscoring.com/podcast/ru/rss.xml` |
| Armenian | `https://www.crmscoring.com/podcast/hy/rss.xml` |

A feed appears once its language has its first episode.

## One-time setup

```bash
brew install ffmpeg
.venv/bin/python -m pip install -r podcast_pipeline/requirements.txt
```

The first transcription downloads the Whisper model (a few hundred MB).

## 1a. No recording: use an AI voice

The scripts can be read by Microsoft Azure's natural voices, Armenian
included (Anahit, female, or Hayk, male). No microphone, no face.

**Get a free key (once, about 5 minutes):**

1. Go to **portal.azure.com** and sign in (or create a free Microsoft account).
2. Search for **Speech service** → **Create**.
3. Fill in: any **Resource group** name (e.g. `podcast`), **Region** `West Europe`,
   any **Name** (e.g. `crmscoring-voice`), **Pricing tier** `Free F0`.
   → **Review + create** → **Create**.
4. When it's ready: **Go to resource** → **Keys and Endpoint**. Copy **KEY 1** and the **Location/Region**.
5. Add them to the `.env` file in the project folder (it's never uploaded to GitHub):

   ```
   AZURE_SPEECH_KEY=paste-key-1-here
   AZURE_SPEECH_REGION=westeurope
   ```

The free tier reads 500,000 characters a month; one episode is about 4,000.

**Make the voice track:**

```bash
.venv/bin/python podcast_pipeline/make_voice.py podcast_pipeline/scripts/ep01-which-leads-to-call-first.hy.md
.venv/bin/python podcast_pipeline/make_voice.py podcast_pipeline/scripts/ep01-which-leads-to-call-first.ru.md --voice male
```

It prints the exact `process_episode.py` command to run next. `--voice male`
picks the male voice, `--rate -10%` reads slower. The ✂️ part of the script
becomes the reel automatically, and the show notes say the episode is read
by an AI voice. `--engine say` makes a free robotic preview with the Mac's
own voices (English and Russian only).

## 1b. Or record yourself

Scripts to read are in [scripts/](scripts), e.g. episode 1 in
[English](scripts/ep01-which-leads-to-call-first.en.md),
[Russian](scripts/ep01-which-leads-to-call-first.ru.md) and
[Armenian](scripts/ep01-which-leads-to-call-first.hy.md).

- A quiet room with soft things around (curtains, a sofa) sounds better than an empty one.
- Phone voice memo or any mic is fine; keep it a hand's width from your mouth.
- If you stumble, pause, and say the sentence again. Cut the bad take later, or leave it.
- Want reels with your face? Record video too (landscape or portrait both work).

Put recordings in `podcast_pipeline/raw/` (not saved to git).

## 2. Process: loudness + transcripts

```bash
.venv/bin/python podcast_pipeline/process_episode.py podcast_pipeline/raw/ep01-en.m4a \
  --lang en --slug ep01-which-leads-to-call-first-en --title "Which leads should you call first?"

.venv/bin/python podcast_pipeline/process_episode.py podcast_pipeline/raw/ep01-ru.m4a \
  --lang ru --slug ep01-which-leads-to-call-first-ru --title "Кому звонить первым?"

.venv/bin/python podcast_pipeline/process_episode.py podcast_pipeline/raw/ep01-hy.m4a \
  --lang hy --model large-v3 --slug ep01-which-leads-to-call-first-hy --title "Ո՞ւմ զանգել առաջինը"
```

Use `--model large-v3` (or at least `medium`) for Armenian: the small models
don't know it well. Add `--date 2026-12-01` to schedule an episode; it stays
off the site and feeds until that day.

This writes `podcast_pipeline/episodes/<slug>/`: the MP3 normalised to
-16 LUFS, an `.srt`, word timings, a plain transcript and `episode.json`.

**Then open `episode.json`** and fix it up:

```json
"summary": "Two or three sentences about the episode.",
"chapters": [
  {"time": "0:00", "title": "Too many leads, not enough hours"},
  {"time": "1:40", "title": "A 100-point scoring sheet"}
],
"links": [
  {"title": "Free lead scoring template", "url": "https://www.crmscoring.com/en/lead-scoring-template.html"}
]
```

Re-running `process_episode.py` keeps these edits.

## 3. Reels (optional)

```bash
# audio over the show cover; without --start/--end it uses the script's ✂️ part
.venv/bin/python podcast_pipeline/make_reel.py ep01-which-leads-to-call-first-en

# from your video recording
.venv/bin/python podcast_pipeline/make_reel.py ep01-which-leads-to-call-first-en \
  --video podcast_pipeline/raw/ep01-en.mp4 --start 2:05 --end 2:50
```

Reels land in `episodes/<slug>/reels/`. Find the start and end in the `.srt`
(the ✂️ part of each script is a good one). Options: `--focus 0.3` moves
the crop left, `--caption-y 1500` moves the captions down, `--image photo.jpg`
uses another picture.

## 4. Publish

```bash
.venv/bin/python podcast_pipeline/publish_feed.py
git add docs/podcast podcast_pipeline docs/sitemap.xml && git commit -m "Podcast: episode 1" && git push
```

This writes the /podcast page, the feeds, the show notes (Markdown, in
`docs/podcast/notes/` and next to each `episode.json`), copies the audio and
transcripts into `docs/podcast/`, and GitHub Pages puts it live in a minute.

## 5. Get listed (once per language)

1. **Apple Podcasts:** podcastsconnect.apple.com → **+** → **New Show** → **Add a show with an RSS feed** → paste the feed URL.
2. **Spotify:** podcasters.spotify.com → **Get started** → **Find an existing podcast** → paste the feed URL.
3. Both email a code to the feed's email (tsovinar.babakhanyan@hotmail.com) to prove it's yours.
4. **YouTube Music / others:** most apps find the show on Apple's directory by themselves.

## Episode ideas

1. Which leads should you call first? *(script ready)*
2. Buying signals: how to tell a lead is ready
3. Cleaning a messy CRM export in 15 minutes
4. Why salespeople don't trust lead scores (and how to fix it)
5. Lead scoring in Salesforce without a consultant
