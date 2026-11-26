"""Step 0 (instead of recording): read a script aloud with an AI voice.

    python make_voice.py scripts/ep01-which-leads-to-call-first.hy.md

Turns a script from scripts/ into raw/<slug>.mp3
with Microsoft Azure AI Speech, which has natural voices in English, Russian
and Armenian. Then run process_episode.py on that file as if you'd recorded it
(the command is printed at the end).

The language comes from the file name (.en.md, .ru.md, .hy.md); the title
and slug from the script's header. The part between the two ✂️ lines is
timed, and process_episode.py / make_reel.py use it as the reel by default.

Needs an Azure Speech key (free tier: 500,000 characters a month) in the
environment or in this folder's .env:

    AZURE_SPEECH_KEY=...
    AZURE_SPEECH_REGION=westeurope

`--engine say` uses the Mac's built-in voices instead, for a quick free
preview (English and Russian only; there's no Armenian Mac voice).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LANGUAGES, RAW, ROOT, probe_duration, require, run  # noqa: E402

# Azure neural voices: (female, male) per language.
VOICES = {
    "en": ("en-US-AvaMultilingualNeural", "en-US-AndrewMultilingualNeural"),
    "ru": ("ru-RU-SvetlanaNeural", "ru-RU-DmitryNeural"),
    "hy": ("hy-AM-AnahitNeural", "hy-AM-HaykNeural"),
}
AZURE_LOCALES = {"en": "en-US", "ru": "ru-RU", "hy": "hy-AM"}
MAC_VOICES = {"en": "Samantha", "ru": "Milena"}
PAUSE = 0.6  # seconds of silence between paragraphs
CUT = "✂️"


def parse_script(text: str) -> dict:
    """Script markdown -> {"title", "slug", "paragraphs": [str], "reel": (first, last) paragraph index}."""
    title_match = re.search(r"^#\s+(.+)$", text, re.M)
    title = title_match.group(1).strip() if title_match else ""
    if "—" in title:
        title = title.split("—", 1)[1].strip()
    slug_match = re.search(r"\*\*Slug:\*\*\s*`([^`]+)`", text)
    body = text.split("\n---\n", 1)[1] if "\n---\n" in text else text

    paragraphs: list[str] = []
    reel_start = reel_end = None
    for block in re.split(r"\n\s*\n", body):
        block = block.strip()
        if not block:
            continue
        if CUT in block:
            if reel_start is None:
                reel_start = len(paragraphs)
            else:
                reel_end = len(paragraphs) - 1
            continue
        if block.startswith("#"):
            continue
        plain = re.sub(r"\*\*|\*|`", "", block)  # bold/italics/code marks aren't read out
        plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", plain)
        # "[your name]" is for a human host; the AI voice skips that clause.
        plain = re.sub(r",?\s*[^,.!?։]*\[[^\]]+\]", "", plain)
        plain = " ".join(plain.split()).replace(" ,", ",").replace(" .", ".").replace("..", ".")
        if plain:
            paragraphs.append(plain)
    reel = (reel_start, reel_end) if reel_start is not None and reel_end is not None else None
    return {"title": title, "slug": slug_match.group(1) if slug_match else None, "paragraphs": paragraphs, "reel": reel}


def load_env() -> None:
    """Fills AZURE_* from this folder's .env if they aren't set already."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip().startswith("AZURE_SPEECH_") and value.strip():
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


def ssml(text: str, lang: str, voice: str, rate: str) -> str:
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{AZURE_LOCALES[lang]}">'
        f'<voice name="{voice}"><prosody rate="{rate}">{escape(text)}</prosody></voice></speak>'
    )


def azure_speak(text: str, lang: str, voice: str, rate: str, out: Path) -> None:
    import requests

    key, region = os.environ.get("AZURE_SPEECH_KEY"), os.environ.get("AZURE_SPEECH_REGION")
    if not (key and region):
        raise SystemExit("Set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION (see README.md), "
                         "or use --engine say for a Mac preview.")
    resp = requests.post(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
            "User-Agent": "crmscoring-podcast",
        },
        data=ssml(text, lang, voice, rate).encode("utf-8"),
        timeout=120,
    )
    if resp.status_code != 200:
        raise SystemExit(f"Azure Speech answered {resp.status_code}: {resp.text[:300]}")
    out.write_bytes(resp.content)


def mac_speak(text: str, lang: str, out: Path) -> None:
    if lang not in MAC_VOICES:
        raise SystemExit("The Mac has no voice for this language; use Azure.")
    aiff = out.with_suffix(".aiff")
    subprocess.run(["say", "-v", MAC_VOICES[lang], "-o", str(aiff), text], check=True)
    run([require("ffmpeg"), "-hide_banner", "-y", "-i", str(aiff), "-ar", "24000", "-ac", "1", str(out)])


def silence(out: Path, seconds: float) -> None:
    run([require("ffmpeg"), "-hide_banner", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
         "-t", f"{seconds}", "-c:a", "pcm_s16le", str(out)])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("script", type=Path, help="a script from scripts/")
    parser.add_argument("--lang", choices=LANGUAGES, help="default: from the file name (.en.md, .ru.md, .hy.md)")
    parser.add_argument("--voice", default="female",
                        help="female, male, or an exact Azure voice name (e.g. hy-AM-HaykNeural)")
    parser.add_argument("--rate", default="-5%", help="speaking speed, e.g. -10%%, 0%%, +5%%")
    parser.add_argument("--engine", choices=("azure", "say"), default="azure")
    args = parser.parse_args(argv)

    lang = args.lang or next((code for code in LANGUAGES if args.script.name.endswith(f".{code}.md")), None)
    if not lang:
        raise SystemExit("Can't tell the language from the file name; pass --lang")
    script = parse_script(args.script.read_text(encoding="utf-8"))
    slug = script["slug"] or args.script.stem.replace(".", "-")
    voice = {"female": VOICES[lang][0], "male": VOICES[lang][1]}.get(args.voice, args.voice)
    load_env()

    RAW.mkdir(exist_ok=True)
    out = RAW / f"{slug}.mp3"
    starts: list[float] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        gap = tmp_dir / "gap.wav"
        silence(gap, PAUSE)
        parts, elapsed = [], 0.0
        for i, paragraph in enumerate(script["paragraphs"]):
            print(f"  {i + 1}/{len(script['paragraphs'])} {paragraph[:70]}…", flush=True)
            wav = tmp_dir / f"p{i:03d}.wav"
            if args.engine == "azure":
                azure_speak(paragraph, lang, voice, args.rate, wav)
            else:
                mac_speak(paragraph, lang, wav)
            starts.append(elapsed)
            elapsed += probe_duration(wav) + PAUSE
            parts += [wav, gap]
        starts.append(elapsed)
        listing = tmp_dir / "parts.txt"
        listing.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
        run([require("ffmpeg"), "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
             "-c:a", "libmp3lame", "-b:a", "128k", str(out)])

    sidecar = {"title": script["title"], "lang": lang, "voice": voice if args.engine == "azure" else "mac",
               "ai_voice": True}
    # When each paragraph is spoken: process_episode.py turns this and the
    # script's words into an exact transcript, no speech recognition needed.
    sidecar["segments"] = [
        {"start": round(starts[i], 3), "end": round(starts[i + 1] - PAUSE, 3), "text": paragraph}
        for i, paragraph in enumerate(script["paragraphs"])
    ]
    if script["reel"]:
        first, last = script["reel"]
        sidecar["reel"] = {"start": round(starts[first], 2), "end": round(starts[last + 1] - PAUSE, 2)}
    out.with_suffix(".json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    model = " --model large-v3" if lang == "hy" else ""
    print(f"\nVoice track: {out} ({elapsed:.0f}s)")
    if "reel" in sidecar:
        print(f"Reel window: {sidecar['reel']['start']:.1f}s – {sidecar['reel']['end']:.1f}s")
    print("Next:\n  python process_episode.py "
          f"{out.relative_to(ROOT)} --lang {lang}{model} --slug {slug} --title {json.dumps(script['title'], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
