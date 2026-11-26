"""Shared bits of the podcast pipeline: paths, settings, ffmpeg and caption timing."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

# Everything lives inside this folder, so it can be moved out of the
# CRM Scoring project and used on its own.
ROOT = Path(__file__).resolve().parent
EPISODES = ROOT / "episodes"
RAW = ROOT / "raw"
PUBLIC = ROOT / "public"  # what gets uploaded to the podcast host (see README)
SETTINGS_FILE = ROOT / "podcast.json"

LANGUAGES = ("en", "ru", "hy")


def settings() -> dict:
    return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))


def episode_dir(slug: str) -> Path:
    return EPISODES / slug


def load_episode(slug: str) -> dict:
    return json.loads((episode_dir(slug) / "episode.json").read_text(encoding="utf-8"))


def save_episode(episode: dict) -> Path:
    folder = episode_dir(episode["slug"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "episode.json"
    path.write_text(json.dumps(episode, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def require(tool: str) -> str:
    found = shutil.which(tool)
    if not found:
        raise SystemExit(f"{tool} isn't installed. On a Mac: brew install ffmpeg")
    return found


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    """Runs a command; on failure shows its last lines of output and stops."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = "\n".join((result.stderr or result.stdout).strip().splitlines()[-15:])
        raise SystemExit(f"{Path(cmd[0]).name} failed:\n{tail}")
    return result


def probe_duration(path: Path) -> float:
    out = run([require("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)]).stdout
    return float(json.loads(out)["format"]["duration"])


def srt_time(seconds: float) -> str:
    """12.3456 -> 00:00:12,346"""
    ms = max(0, int(round(seconds * 1000)))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def clock(seconds: float) -> str:
    """Chapter-style time: 75 -> 1:15, 3725 -> 1:02:05."""
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def to_srt(cues: list[dict]) -> str:
    """cues: [{"start": s, "end": s, "text": str}] -> SRT text."""
    blocks = []
    for i, cue in enumerate(cues, 1):
        blocks.append(f"{i}\n{srt_time(cue['start'])} --> {srt_time(cue['end'])}\n{cue['text'].strip()}\n")
    return "\n".join(blocks)


def align_script(segments: list[dict]) -> tuple[list[dict], list[dict]]:
    """Exact transcript for an episode read from a script.

    segments: [{"start", "end", "text"}] per paragraph, as make_voice.py
    timed them. Each paragraph is split into sentences and words, and its
    time shared out in proportion to their length -- a reading voice keeps
    an even pace, so this is close enough for captions, and the words are
    exactly the script's. Returns (cues, words) like a transcription.
    """
    import re

    cues, words = [], []
    for seg in segments:
        sentences = [s for s in re.split(r"(?<=[.!?…։])\s+", seg["text"].strip()) if s]
        total = sum(len(s) + 1 for s in sentences) or 1
        t = seg["start"]
        span = seg["end"] - seg["start"]
        for sentence in sentences:
            length = span * (len(sentence) + 1) / total
            cues.append({"start": round(t, 3), "end": round(t + length, 3), "text": sentence})
            tokens = sentence.split()
            weight = sum(len(w) + 1 for w in tokens) or 1
            wt = t
            for token in tokens:
                dur = length * (len(token) + 1) / weight
                words.append({"start": round(wt, 3), "end": round(wt + dur, 3), "word": token})
                wt += dur
            t += length
    return cues, words


def caption_chunks(words: list[dict], start: float = 0.0, end: float | None = None,
                   max_words: int = 4, max_chars: int = 22, max_gap: float = 0.6) -> list[dict]:
    """Groups word timestamps into short on-screen captions for a clip.

    Only words inside [start, end) are used, and times come back relative to
    `start`. A caption ends after max_words or max_chars, at a pause longer
    than max_gap, or after a word ending a sentence.
    """
    picked = [w for w in words if w["end"] > start and (end is None or w["start"] < end)]
    chunks: list[dict] = []
    current: list[dict] = []

    def flush():
        if current:
            text = " ".join(w["word"].strip() for w in current).strip()
            clip_end = end if end is not None else current[-1]["end"]
            chunks.append({
                "start": max(0.0, current[0]["start"] - start),
                "end": min(clip_end, current[-1]["end"]) - start,
                "text": text,
            })
            current.clear()

    for word in picked:
        text = word["word"].strip()
        if not text:
            continue
        if current:
            joined = len(" ".join(w["word"].strip() for w in current)) + 1 + len(text)
            if len(current) >= max_words or joined > max_chars or word["start"] - current[-1]["end"] > max_gap:
                flush()
        current.append(word)
        if text[-1] in ".?!…։":
            flush()
    flush()
    # Keep each caption up until the next one starts, so the text doesn't flicker.
    for a, b in zip(chunks, chunks[1:]):
        if 0 < b["start"] - a["end"] < 0.35:
            a["end"] = b["start"]
    return [c for c in chunks if c["end"] > c["start"]]
