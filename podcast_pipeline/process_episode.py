"""Step 1: a raw recording -> a loudness-normalised MP3 and its transcripts.

    python podcast_pipeline/process_episode.py recording.m4a \
        --slug ep01-what-is-lead-scoring --title "What is lead scoring?" --lang en

Writes podcast_pipeline/episodes/<slug>/:
    <slug>.mp3          normalised to -16 LUFS (the podcast standard), -1.5 dBTP
    <slug>.srt          subtitles, one cue per spoken phrase
    <slug>.words.json   every word with its start/end time (make_reel.py uses it)
    <slug>.txt          plain transcript
    episode.json        title, date, duration, size ... (edit the summary and
                        chapters there, then run publish_feed.py)

Loudness uses ffmpeg's loudnorm in two passes: the first measures, the
second corrects with those measurements, which is more accurate than one pass.
Transcription uses faster-whisper on the original recording (not the MP3).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LANGUAGES, episode_dir, probe_duration, require, run, save_episode, to_srt  # noqa: E402

TARGET_LUFS = -16.0
TRUE_PEAK = -1.5
LRA = 11.0


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "episode"


def measure_loudness(source: Path) -> dict:
    """First loudnorm pass: returns ffmpeg's measured values."""
    result = run([
        require("ffmpeg"), "-hide_banner", "-nostats", "-i", str(source),
        "-af", f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA={LRA}:print_format=json",
        "-f", "null", "-",
    ])
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", result.stderr, re.S)
    if not match:
        raise SystemExit("Couldn't read ffmpeg's loudness measurement.")
    return json.loads(match.group(0))


def loudnorm_filter(measured: dict) -> str:
    return (
        f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA={LRA}"
        f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}:linear=true"
    )


def normalise(source: Path, target: Path, mono: bool = True) -> dict:
    measured = measure_loudness(source)
    run([
        require("ffmpeg"), "-hide_banner", "-y", "-i", str(source),
        "-af", loudnorm_filter(measured),
        # loudnorm works at 192 kHz internally; bring it back to 44.1 kHz.
        "-ar", "44100", "-ac", "1" if mono else "2",
        "-c:a", "libmp3lame", "-b:a", "96k" if mono else "128k",
        "-id3v2_version", "3",
        str(target),
    ])
    return measured


def first_sentences(text: str, limit: int = 280) -> str:
    """A starting summary: the opening sentences of the transcript, up to
    `limit` characters. Rewrite it in episode.json before publishing."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(mark) for mark in (". ", "? ", "! ", "։ "))
    return cut[: end + 1] if end > 80 else cut.rsplit(" ", 1)[0] + "…"


def decode_16k(source: Path):
    """The recording as 16 kHz mono float samples, which is what Whisper
    listens to. Decoded with ffmpeg, so any format ffmpeg reads works."""
    import numpy as np

    raw = subprocess.run(
        [require("ffmpeg"), "-hide_banner", "-nostdin", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
         "-f", "f32le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def transcribe(source: Path, language: str, model_size: str) -> tuple[list[dict], list[dict]]:
    """Returns (segments, words) with times in seconds."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit("faster-whisper isn't installed: pip install -r podcast_pipeline/requirements.txt")
    model = WhisperModel(model_size, device="auto", compute_type="int8")
    raw_segments, _info = model.transcribe(
        decode_16k(source), language=language, word_timestamps=True, vad_filter=True, beam_size=5
    )
    segments, words = [], []
    for seg in raw_segments:
        segments.append({"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip()})
        for w in seg.words or []:
            words.append({"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word.strip(),
                          "p": round(w.probability, 3)})
        print(f"  [{seg.start:7.1f}s] {seg.text.strip()}", flush=True)
    return segments, words


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("recording", type=Path, help="raw recording (wav, m4a, mp3, mp4, ...)")
    parser.add_argument("--title", required=True)
    parser.add_argument("--slug", help="short id used in file names and URLs (default: from the title)")
    parser.add_argument("--lang", choices=LANGUAGES, default="en", help="language spoken in the episode")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="publish date, YYYY-MM-DD")
    parser.add_argument("--model", default="small",
                        help="whisper model: tiny, base, small, medium, large-v3 (bigger = slower, better; "
                             "use medium or large-v3 for Armenian)")
    parser.add_argument("--stereo", action="store_true", help="keep stereo (default: mono, best for speech)")
    parser.add_argument("--skip-transcript", action="store_true")
    args = parser.parse_args(argv)

    if not args.recording.exists():
        raise SystemExit(f"No such file: {args.recording}")
    slug = args.slug or slugify(args.title)
    folder = episode_dir(slug)
    folder.mkdir(parents=True, exist_ok=True)
    mp3 = folder / f"{slug}.mp3"

    print(f"1/2 Normalising loudness to {TARGET_LUFS} LUFS -> {mp3.name}")
    measured = normalise(args.recording, mp3, mono=not args.stereo)
    print(f"    was {measured['input_i']} LUFS, true peak {measured['input_tp']} dBTP")

    transcript = None
    if not args.skip_transcript:
        print(f"2/2 Transcribing ({args.lang}, model {args.model}) ...")
        segments, words = transcribe(args.recording, args.lang, args.model)
        (folder / f"{slug}.srt").write_text(to_srt(segments), encoding="utf-8")
        (folder / f"{slug}.words.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
        transcript = "\n".join(s["text"] for s in segments) + "\n"
        (folder / f"{slug}.txt").write_text(transcript, encoding="utf-8")

    # Made with make_voice.py? Its notes (reel window, AI voice) sit next to the audio.
    voice_notes = {}
    sidecar = args.recording.with_suffix(".json")
    if sidecar.exists():
        voice_notes = json.loads(sidecar.read_text(encoding="utf-8"))

    old = {}
    if (folder / "episode.json").exists():
        old = json.loads((folder / "episode.json").read_text(encoding="utf-8"))
    episode = {
        "slug": slug,
        "title": args.title,
        "lang": args.lang,
        "date": args.date,
        # Kept from an earlier run so a re-process doesn't wipe your edits.
        "summary": old.get("summary") or first_sentences(transcript or ""),
        "chapters": old.get("chapters", []),
        "links": old.get("links", []),
        "reel": old.get("reel") or voice_notes.get("reel"),
        "ai_voice": bool(voice_notes.get("ai_voice") or old.get("ai_voice")),
        "duration": round(probe_duration(mp3), 2),
        "bytes": mp3.stat().st_size,
        "audio": mp3.name,
        "srt": f"{slug}.srt" if transcript else None,
        "transcript": f"{slug}.txt" if transcript else None,
    }
    path = save_episode(episode)
    print(f"Done. Edit the summary/chapters in {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path},"
          " then run publish_feed.py")


if __name__ == "__main__":
    main()
