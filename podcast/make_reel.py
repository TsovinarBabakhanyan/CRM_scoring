"""Step 2: a 9:16 reel (1080x1920) from part of an episode, with captions burned in.

    # from a video recording of the episode
    python make_reel.py ep01-what-is-lead-scoring --video episode.mp4 --start 1:05 --end 1:50

    # audio-only episode: the episode's MP3 over a still image (default: the show cover)
    python make_reel.py ep01-what-is-lead-scoring --start 65 --end 110

Writes episodes/<slug>/reels/<slug>-<start>-<end>.mp4, ready for
Instagram Reels, TikTok and YouTube Shorts.

A video is scaled to fill 1080x1920 and the middle is cropped out (use
--focus to move the crop left or right); a still picture is fitted whole. Captions come from the episode's
word timestamps (<slug>.words.json from process_episode.py), 2-4 words at a
time. Each caption is drawn as an image and laid over the video with ffmpeg's
overlay filter, so it works with any ffmpeg build -- including ones without
libass/freetype -- and Armenian and Russian letters render with the chosen font.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, caption_chunks, episode_dir, load_episode, probe_duration, require, run  # noqa: E402

WIDTH, HEIGHT = 1080, 1920
# Fonts that cover Latin, Cyrillic and Armenian, tried in order.
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansArmenian-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
ACCENT = (179, 64, 31)  # the site's accent colour


def parse_time(value: str) -> float:
    """'95', '1:35' or '0:01:35.5' -> seconds."""
    total = 0.0
    for part in value.split(":"):
        total = total * 60 + float(part)
    return total


def crop_filter(focus: float) -> str:
    """Scale to cover 1080x1920, then crop; focus 0 = left edge, 0.5 = centre, 1 = right edge."""
    focus = min(1.0, max(0.0, focus))
    return (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT}:(iw-{WIDTH})*{focus}:(ih-{HEIGHT})/2,setsar=1"
    )


def still_filter() -> str:
    """A still picture (the square cover) is fitted, not cropped: full width,
    near the top, on the site's background colour, leaving room for captions."""
    return (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:200:color=0xF6F1E6,setsar=1"
    )


def find_font(explicit: str | None) -> str:
    for candidate in ([explicit] if explicit else []) + FONT_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    raise SystemExit("No font with Armenian/Cyrillic letters found; pass one with --font path/to/font.ttf")


def wrap(text: str, font, max_width: int, draw) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and draw.textlength(trial, font=font) > max_width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def render_caption(text: str, font_path: str, out: Path, size: int = 78) -> None:
    """One caption as a transparent 1080-wide PNG: white bold text on a dark rounded box."""
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(font_path, size)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines = wrap(text, font, WIDTH - 200, probe)
    line_h = int(size * 1.25)
    widths = [probe.textlength(line, font=font) for line in lines]
    pad_x, pad_y = 36, 24
    box_w = int(max(widths)) + 2 * pad_x
    box_h = line_h * len(lines) + 2 * pad_y
    image = Image.new("RGBA", (WIDTH, box_h + 20), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    left = (WIDTH - box_w) // 2
    draw.rounded_rectangle([left, 10, left + box_w, 10 + box_h], radius=28, fill=(20, 16, 10, 200))
    for i, (line, w) in enumerate(zip(lines, widths)):
        x = (WIDTH - w) / 2
        y = 10 + pad_y + i * line_h
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0, 255))
    image.save(out)


def build_filter(base: str, caption_count: int, captions: list[dict], y: int) -> tuple[str, str]:
    """Video filter graph: [0:v] cropped, then each caption PNG overlaid while it's spoken."""
    parts = [f"[0:v]{base}[v0]"]
    last = "v0"
    for i, cue in enumerate(captions[:caption_count]):
        nxt = f"v{i + 1}"
        parts.append(
            f"[{last}][{i + 2}:v]overlay=x=0:y={y}:enable='between(t,{cue['start']:.3f},{cue['end']:.3f})'[{nxt}]"
        )
        last = nxt
    return ";".join(parts), last


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("slug", help="episode id (folder in episodes)")
    parser.add_argument("--start", help="clip start, e.g. 65 or 1:05 (default: the script's ✂️ part)")
    parser.add_argument("--end", help="clip end, e.g. 110 or 1:50")
    parser.add_argument("--video", type=Path, help="video recording of the episode (default: audio over --image)")
    parser.add_argument("--image", type=Path, help="still picture for audio-only reels (default: show cover)")
    parser.add_argument("--audio", type=Path, help="sound for the reel (default: the episode's normalised MP3)")
    parser.add_argument("--focus", type=float, default=0.5, help="horizontal crop position, 0 (left) .. 1 (right)")
    parser.add_argument("--font", help="font file for captions")
    parser.add_argument("--font-size", type=int, default=78)
    parser.add_argument("--caption-y", type=int,
                        help="top of the captions in pixels from the top (default: 1300 on video, 1400 on a still)")
    parser.add_argument("--no-captions", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    episode = load_episode(args.slug)
    if args.start and args.end:
        start, end = parse_time(args.start), parse_time(args.end)
    elif episode.get("reel"):
        start, end = episode["reel"]["start"], episode["reel"]["end"]
    else:
        raise SystemExit("Pass --start and --end (this episode has no ✂️ reel part marked).")
    if end <= start:
        raise SystemExit("--end must be after --start")
    if end - start > 180:
        raise SystemExit("Reels can be at most 3 minutes; pick a shorter window.")

    folder = episode_dir(args.slug)
    audio = args.audio or folder / episode["audio"]
    out = args.out or folder / "reels" / f"{args.slug}-{int(start)}-{int(end)}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)

    captions: list[dict] = []
    if not args.no_captions:
        words_file = folder / f"{args.slug}.words.json"
        if not words_file.exists():
            raise SystemExit(f"No {words_file.name}; run process_episode.py first or pass --no-captions")
        captions = caption_chunks(json.loads(words_file.read_text(encoding="utf-8")), start, end)

    ffmpeg = require("ffmpeg")
    length = end - start
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        if args.video:
            inputs = ["-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(args.video)]
            audio_map = "0:a:0?"
        else:
            image = args.image or ROOT / "cover.png"
            if not image.exists():
                raise SystemExit(f"No picture at {image}; pass --image")
            if probe_duration(audio) < end:
                raise SystemExit("The clip goes past the end of the episode.")
            inputs = [
                "-loop", "1", "-framerate", "30", "-t", f"{length:.3f}", "-i", str(image),
                "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(audio),
            ]
            audio_map = "1:a:0"
        # Captions are inputs 2.. (input 1 is the audio, or a silent placeholder for video).
        if args.video:
            inputs += ["-f", "lavfi", "-t", "0.1", "-i", "anullsrc"]

        font = find_font(args.font) if captions else None
        for i, cue in enumerate(captions):
            png = tmp_dir / f"cap{i:04d}.png"
            render_caption(cue["text"], font, png, args.font_size)
            inputs += ["-loop", "1", "-t", f"{length:.3f}", "-i", str(png)]

        base = crop_filter(args.focus) if args.video else still_filter()
        caption_y = args.caption_y if args.caption_y is not None else (1300 if args.video else 1400)
        graph, last = build_filter(base + ",fps=30", len(captions), captions, caption_y)
        run([
            ffmpeg, "-hide_banner", "-y", *inputs,
            "-filter_complex", graph, "-map", f"[{last}]", "-map", audio_map,
            "-t", f"{length:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
            "-movflags", "+faststart",
            str(out),
        ])
    print(f"Reel: {out} ({length:.0f}s, {len(captions)} captions)")


if __name__ == "__main__":
    main()
