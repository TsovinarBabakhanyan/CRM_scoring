"""Step 3: show notes and RSS feeds.

    python podcast_pipeline/publish_feed.py

Reads every podcast_pipeline/episodes/*/episode.json and writes the files
podcast apps read into docs/podcast/ (hosted by GitHub Pages, but not linked
from the website -- there's no podcast page on the site):

    docs/podcast/rss.xml               English feed  -> submit to Apple Podcasts / Spotify
    docs/podcast/ru/rss.xml            Russian feed
    docs/podcast/hy/rss.xml            Armenian feed
    docs/podcast/audio/<slug>.mp3      the episode audio
    docs/podcast/transcripts/<slug>.*  .srt and .txt transcripts
    docs/podcast/notes/<slug>.md       show notes in Markdown (also next to episode.json)
    docs/podcast/cover.png             3000x3000 show cover (made once if missing)

Each language is its own show, because podcast apps expect one language per
feed. An episode dated in the future stays out until that day, so you can
prepare episodes ahead and re-run this (or let a commit do it) on the day.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import shutil
import sys
from email.utils import format_datetime
from pathlib import Path
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import EPISODES, LANGUAGES, ROOT, SITE_PODCAST, settings  # noqa: E402

NS = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "podcast": "https://podcastindex.org/namespace/1.0",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)
YEREVAN = ZoneInfo("Asia/Yerevan")

# Words around the episodes, per language.
TEXT = {
    "en": {
        "chapters": "In this episode", "links": "Mentioned", "transcript": "Transcript",
        "cta_title": "Score your own leads",
        "cta": "CRM Scoring ranks every lead Hot, Warm or Cold and explains why. Upload a CRM export and see your list in a minute — free to start.",
        "cta_button": "Try it free", "template": "Get the lead scoring template",
        "listen": "Listen", "subscribe": "Subscribe (RSS)", "soon": "The first episode is coming soon.",
        "heading": "Podcast", "tab": "English",
        "ai_voice": "This episode is read by an AI voice.",
    },
    "ru": {
        "chapters": "В выпуске", "links": "Упоминается", "transcript": "Расшифровка",
        "cta_title": "Оцените свои лиды",
        "cta": "CRM Scoring делит лиды на горячие, тёплые и холодные и объясняет почему. Загрузите выгрузку из CRM и получите результат за минуту — начать можно бесплатно.",
        "cta_button": "Попробовать бесплатно", "template": "Шаблон скоринга лидов",
        "listen": "Слушать", "subscribe": "Подписаться (RSS)", "soon": "Первый выпуск скоро.",
        "heading": "Подкаст", "tab": "Русский",
        "ai_voice": "Этот выпуск озвучен голосом ИИ.",
    },
    "hy": {
        "chapters": "Այս թողարկումում", "links": "Հիշատակված", "transcript": "Տեքստը",
        "cta_title": "Գնահատեք ձեր լիդերը",
        "cta": "CRM Scoring-ը լիդերը բաժանում է թեժ, տաք և սառը և բացատրում՝ ինչու։ Վերբեռնեք CRM-ի արտահանումը և արդյունքը կունենաք մեկ րոպեում՝ սկսելն անվճար է։",
        "cta_button": "Փորձել անվճար", "template": "Լիդերի գնահատման ձևանմուշ",
        "listen": "Լսել", "subscribe": "Բաժանորդագրվել (RSS)", "soon": "Առաջին թողարկումը շուտով։",
        "heading": "Փոդքասթ", "tab": "Հայերեն",
        "ai_voice": "Այս թողարկումը կարդում է արհեստական բանականության ձայնը։",
    },
}


def site_url(cfg: dict, path: str) -> str:
    return cfg["site"].rstrip("/") + "/" + path.lstrip("/")


def cta_links(cfg: dict, lang: str) -> tuple[str, str]:
    return (site_url(cfg, f"?lang={lang}#pricing"), site_url(cfg, f"{lang}/lead-scoring-template.html"))


def load_episodes(today: dt.date) -> list[dict]:
    episodes = []
    for path in sorted(EPISODES.glob("*/episode.json")):
        episode = json.loads(path.read_text(encoding="utf-8"))
        episode["_dir"] = path.parent
        if dt.date.fromisoformat(episode["date"]) <= today:
            episodes.append(episode)
    episodes.sort(key=lambda e: (e["date"], e["slug"]), reverse=True)
    return episodes


def show_notes_md(cfg: dict, episode: dict) -> str:
    t = TEXT[episode["lang"]]
    try_url, template_url = cta_links(cfg, episode["lang"])
    lines = [f"# {episode['title']}", "", episode.get("summary", "").strip(), ""]
    if episode.get("ai_voice"):
        lines += [f"*{t['ai_voice']}*", ""]
    if episode.get("chapters"):
        lines += [f"## {t['chapters']}", ""]
        lines += [f"- {c['time']} — {c['title']}" for c in episode["chapters"]]
        lines.append("")
    if episode.get("links"):
        lines += [f"## {t['links']}", ""]
        lines += [f"- [{link['title']}]({link['url']})" for link in episode["links"]]
        lines.append("")
    lines += [
        f"## {t['cta_title']}", "", t["cta"], "",
        f"- [{t['cta_button']}]({try_url})",
        f"- [{t['template']}]({template_url})",
        "",
    ]
    if episode.get("transcript"):
        lines += [f"[{t['transcript']}]({site_url(cfg, 'podcast/transcripts/' + episode['transcript'])})", ""]
    return "\n".join(lines)


def show_notes_html(cfg: dict, episode: dict) -> str:
    """The same notes as HTML, for the feed and the page."""
    t = TEXT[episode["lang"]]
    e = html.escape
    try_url, template_url = cta_links(cfg, episode["lang"])
    parts = [f"<p>{e(episode.get('summary', '').strip())}</p>"]
    if episode.get("ai_voice"):
        parts.append(f"<p><em>{e(t['ai_voice'])}</em></p>")
    if episode.get("chapters"):
        items = "".join(f"<li>{e(c['time'])} — {e(c['title'])}</li>" for c in episode["chapters"])
        parts.append(f"<p><strong>{e(t['chapters'])}</strong></p><ul>{items}</ul>")
    if episode.get("links"):
        items = "".join(f'<li><a href="{e(link["url"])}">{e(link["title"])}</a></li>' for link in episode["links"])
        parts.append(f"<p><strong>{e(t['links'])}</strong></p><ul>{items}</ul>")
    parts.append(
        f"<p><strong>{e(t['cta_title'])}</strong> — {e(t['cta'])} "
        f'<a href="{e(try_url)}">{e(t["cta_button"])}</a> · <a href="{e(template_url)}">{e(t["template"])}</a></p>'
    )
    return "".join(parts)


def sub(parent: ET.Element, tag: str, text: str | None = None, attrs: dict | None = None, **more) -> ET.Element:
    if ":" in tag:
        prefix, name = tag.split(":", 1)
        tag = f"{{{NS[prefix]}}}{name}"
    el = ET.SubElement(parent, tag, {**(attrs or {}), **more})
    if text is not None:
        el.text = text
    return el


def feed_path(lang: str) -> str:
    return "podcast/rss.xml" if lang == "en" else f"podcast/{lang}/rss.xml"


def build_feed(cfg: dict, lang: str, episodes: list[dict], now: dt.datetime) -> bytes:
    show = cfg["shows"][lang]
    rss = ET.Element("rss", {"version": "2.0"})
    channel = sub(rss, "channel")
    sub(channel, "title", show["title"])
    sub(channel, "link", site_url(cfg, f"?lang={lang}"))
    sub(channel, "language", lang)
    sub(channel, "description", show["description"])
    sub(channel, "copyright", f"© {now.year} {cfg['author']}")
    sub(channel, "lastBuildDate", format_datetime(now))
    sub(channel, "generator", "CRM Scoring podcast_pipeline")
    sub(channel, "atom:link", href=site_url(cfg, feed_path(lang)), rel="self", type="application/rss+xml")
    sub(channel, "itunes:author", cfg["author"])
    sub(channel, "itunes:summary", show["description"])
    owner = sub(channel, "itunes:owner")
    sub(owner, "itunes:name", cfg["author"])
    sub(owner, "itunes:email", cfg["email"])
    sub(channel, "itunes:image", href=site_url(cfg, "podcast/cover.png"))
    image = sub(channel, "image")
    sub(image, "url", site_url(cfg, "podcast/cover.png"))
    sub(image, "title", show["title"])
    sub(image, "link", site_url(cfg, f"?lang={lang}"))
    category = sub(channel, "itunes:category", attrs={"text": cfg["category"]})
    sub(category, "itunes:category", attrs={"text": cfg["subcategory"]})
    sub(channel, "itunes:explicit", "true" if cfg.get("explicit") else "false")
    sub(channel, "itunes:type", "episodic")
    sub(channel, "podcast:locked", "no", owner=cfg["email"])

    for episode in episodes:
        item = sub(channel, "item")
        sub(item, "title", episode["title"])
        notes = show_notes_html(cfg, episode)
        sub(item, "description", notes)
        sub(item, "content:encoded", notes)
        sub(item, "link", site_url(cfg, f"?lang={episode['lang']}"))
        sub(item, "guid", site_url(cfg, f"podcast/audio/{episode['audio']}"), isPermaLink="false")
        published = dt.datetime.combine(dt.date.fromisoformat(episode["date"]), dt.time(9, 0), YEREVAN)
        sub(item, "pubDate", format_datetime(published))
        sub(item, "enclosure", url=site_url(cfg, f"podcast/audio/{episode['audio']}"),
            length=str(episode["bytes"]), type="audio/mpeg")
        sub(item, "itunes:duration", str(int(round(episode["duration"]))))
        sub(item, "itunes:summary", episode.get("summary", ""))
        sub(item, "itunes:explicit", "true" if cfg.get("explicit") else "false")
        sub(item, "itunes:episodeType", "full")
        if episode.get("srt"):
            sub(item, "podcast:transcript", url=site_url(cfg, f"podcast/transcripts/{episode['srt']}"),
                type="application/x-subrip", language=episode["lang"])
    ET.indent(rss, space="  ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="utf-8")


def make_cover(path: Path) -> None:
    """A plain 3000x3000 cover in the site's colours (Apple wants 1400-3000 px, square)."""
    from PIL import Image, ImageDraw, ImageFont

    size = 3000
    img = Image.new("RGB", (size, size), (246, 241, 230))
    draw = ImageDraw.Draw(img)
    for i, colour in enumerate([(197, 58, 44), (168, 113, 15), (91, 100, 114)]):
        x = 900 + i * 460
        draw.ellipse([x, 760, x + 300, 1060], fill=colour)
    font_path = next(
        (p for p in ["/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
                     "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"] if Path(p).exists()),
        None,
    )
    big = ImageFont.truetype(font_path, 330) if font_path else ImageFont.load_default()
    small = ImageFont.truetype(font_path, 230) if font_path else ImageFont.load_default()
    for text, font, y, colour in [
        ("CRM Scoring", big, 1350, (33, 27, 18)),
        ("Podcast", small, 1800, (179, 64, 31)),
        ("Hot · Warm · Cold", small, 2250, (107, 97, 82)),
    ]:
        w = draw.textlength(text, font=font)
        draw.text(((size - w) / 2, y), text, font=font, fill=colour)
    img.save(path, optimize=True)


def publish(today: dt.date | None = None, out: Path = SITE_PODCAST) -> dict[str, list[dict]]:
    cfg = settings()
    today = today or dt.datetime.now(YEREVAN).date()
    now = dt.datetime.now(YEREVAN).replace(microsecond=0)
    episodes = load_episodes(today)
    if not episodes:
        return {}
    out.mkdir(parents=True, exist_ok=True)
    for folder in ("audio", "transcripts", "notes"):
        (out / folder).mkdir(exist_ok=True)

    cover = ROOT / "cover.png"
    if not cover.exists():
        make_cover(cover)
    shutil.copyfile(cover, out / "cover.png")

    by_lang: dict[str, list[dict]] = {}
    for ep in episodes:
        if ep["lang"] not in LANGUAGES:
            raise SystemExit(f"{ep['slug']}: language must be one of {', '.join(LANGUAGES)}")
        by_lang.setdefault(ep["lang"], []).append(ep)
        src = ep["_dir"]
        # The MP3 isn't kept in git next to episode.json (it's already in
        # docs/podcast/audio once published), so either place will do.
        if (src / ep["audio"]).exists():
            shutil.copyfile(src / ep["audio"], out / "audio" / ep["audio"])
        elif not (out / "audio" / ep["audio"]).exists():
            raise SystemExit(f"{ep['slug']}: audio file {ep['audio']} is missing")
        for name in (ep.get("srt"), ep.get("transcript")):
            if name and (src / name).exists():
                shutil.copyfile(src / name, out / "transcripts" / name)
        notes = show_notes_md(cfg, ep)
        (src / "show-notes.md").write_text(notes, encoding="utf-8")
        (out / "notes" / f"{ep['slug']}.md").write_text(notes, encoding="utf-8")

    for lang, eps in by_lang.items():
        target = out.parent / feed_path(lang)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(build_feed(cfg, lang, eps, now))
    return by_lang


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--today", help="pretend it's this date (YYYY-MM-DD), to preview scheduled episodes")
    args = parser.parse_args(argv)
    by_lang = publish(dt.date.fromisoformat(args.today) if args.today else None)
    for lang in LANGUAGES:
        print(f"{lang}: {len(by_lang.get(lang, []))} episode(s)")
    print("Wrote the feeds to docs/podcast/. Commit and push to publish them.")


if __name__ == "__main__":
    main()
