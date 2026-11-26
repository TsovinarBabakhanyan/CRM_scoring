# CRM Scoring Podcast

Everything for the podcast lives in this one folder. It doesn't use or change
anything else in the CRM Scoring project, so you can **move the whole
`podcast` folder anywhere** (another disk, its own GitHub repository) and it
keeps working.

From a script (read by an AI voice, or by you), three commands give you:

- the episode audio, normalised to podcast loudness (-16 LUFS)
- transcripts (`.srt` and `.txt`)
- 9:16 reels with captions for Instagram, TikTok and YouTube Shorts
- show notes and one RSS feed per language (English, Russian, Armenian),
  which is what Apple Podcasts and Spotify read

## What's in the folder

| Path | What |
|---|---|
| `scripts/` | episode scripts to read, per language |
| `raw/` | voice tracks or your recordings (stays on your computer) |
| `episodes/<slug>/` | each episode: `episode.json`, transcripts, reels |
| `public/` | **what you upload**: feeds, audio, transcripts, cover |
| `podcast.json` | show names, descriptions, email, where `public/` is hosted |
| `.env` | your Azure key (private, never uploaded) |
| `cover.png` | 3000x3000 show cover |

## One-time setup

In Terminal, inside this folder:

```bash
brew install ffmpeg
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then put your Azure key in .env
```

The first transcription downloads the Whisper speech model (Armenian uses
the large one, about 3 GB).

**Azure key** (for the AI voice; free tier, 500,000 characters a month, one
episode is about 4,000): portal.azure.com → **Speech service** → **Create**
(Pricing tier **Free F0**; if a region says it isn't accepting new customers,
pick another, e.g. North Europe) → **Go to resource** → **Keys and Endpoint**.
Put KEY 1 and the region in `.env`.

## Make an episode

All commands are run inside this folder.

**1. Voice track** — an AI voice reads the script:

```bash
.venv/bin/python make_voice.py scripts/ep01-which-leads-to-call-first.hy.md
```

`--voice male` for the male voice (English Andrew, Russian Dmitry, Armenian
Hayk; female is Ava, Svetlana, Anahit), `--rate -10%` to read slower. It
prints the next command. *Recording yourself instead?* Save the file in
`raw/` and skip to step 2.

**2. Loudness and transcripts:**

```bash
.venv/bin/python process_episode.py raw/ep01-which-leads-to-call-first-hy.mp3 \
  --lang hy --model large-v3 --slug ep01-which-leads-to-call-first-hy --title "Ո՞ւմ զանգել առաջինը"
```

Use `--model large-v3` for Armenian; `small` is fine for English and Russian.
`--date 2026-12-01` schedules the episode: it stays out of the feed until
that day. Then open `episodes/<slug>/episode.json` and write a good
`summary`, and optionally `chapters` and `links`:

```json
"chapters": [{"time": "0:00", "title": "Too many leads"}, {"time": "1:40", "title": "A 100-point sheet"}],
"links": [{"title": "Free lead scoring template", "url": "https://www.crmscoring.com/en/lead-scoring-template.html"}]
```

**3. Reel:**

```bash
.venv/bin/python make_reel.py ep01-which-leads-to-call-first-hy
```

Without `--start`/`--end` it uses the script's ✂️ part. The reel is saved in
`episodes/<slug>/reels/`. With your own video: `--video my-video.mp4`.

**4. Feeds:**

```bash
.venv/bin/python publish_feed.py
```

This fills `public/`. Upload the contents of `public/` to the address in
`podcast.json` → `feed_url`, keeping the folder structure.

## Hosting `public/` (once)

The feeds and audio need a permanent public address. The free, simple way:

1. On github.com, create a new **public** repository, e.g. `crmscoring-podcast`.
2. Upload everything inside `public/` to it (**Add file → Upload files**, drag the folder contents in).
3. Repository **Settings → Pages** → Source: **Deploy from a branch**, branch `main`, folder `/ (root)` → **Save**.
4. After a minute it's at `https://<your-github-name>.github.io/crmscoring-podcast/`.
   Put that address in `podcast.json` as `feed_url`, run `publish_feed.py` again and re-upload.

Your feeds are then:

| Language | Feed |
|---|---|
| English | `<feed_url>rss.xml` |
| Russian | `<feed_url>ru/rss.xml` |
| Armenian | `<feed_url>hy/rss.xml` |

## Get listed (once per language)

1. **Apple Podcasts:** podcastsconnect.apple.com → **+** → **New Show** → **Add a show with an RSS feed** → paste the feed.
2. **Spotify:** creators.spotify.com → **Get started** → **Find an existing podcast** → paste the feed.
3. Both send a code to the email in `podcast.json` to prove the show is yours.

## Tests

```bash
.venv/bin/pip install pytest && .venv/bin/python -m pytest -q tests
```

## Episode ideas

1. Which leads should you call first? *(scripts ready, en / ru / hy)*
2. Buying signals: how to tell a lead is ready
3. Cleaning a messy CRM export in 15 minutes
4. Why salespeople don't trust lead scores (and how to fix it)
5. Lead scoring in Salesforce without a consultant
