"""Step 3: show notes, RSS feeds and the crmscoring.com/podcast/ page.

    python podcast_pipeline/publish_feed.py

Reads every podcast_pipeline/episodes/*/episode.json and writes into docs/
(the website, published by GitHub Pages):

    docs/podcast/index.html            the /podcast page: every episode with a player,
                                       show notes and a way into lead scoring
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
from common import EPISODES, LANGUAGES, ROOT, SITE, SITE_PODCAST, clock, settings  # noqa: E402

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
    },
    "ru": {
        "chapters": "В выпуске", "links": "Упоминается", "transcript": "Расшифровка",
        "cta_title": "Оцените свои лиды",
        "cta": "CRM Scoring делит лиды на горячие, тёплые и холодные и объясняет почему. Загрузите выгрузку из CRM и получите результат за минуту — начать можно бесплатно.",
        "cta_button": "Попробовать бесплатно", "template": "Шаблон скоринга лидов",
        "listen": "Слушать", "subscribe": "Подписаться (RSS)", "soon": "Первый выпуск скоро.",
        "heading": "Подкаст", "tab": "Русский",
    },
    "hy": {
        "chapters": "Այս թողարկումում", "links": "Հիշատակված", "transcript": "Տեքստը",
        "cta_title": "Գնահատեք ձեր լիդերը",
        "cta": "CRM Scoring-ը լիդերը բաժանում է թեժ, տաք և սառը և բացատրում՝ ինչու։ Վերբեռնեք CRM-ի արտահանումը և արդյունքը կունենաք մեկ րոպեում՝ սկսելն անվճար է։",
        "cta_button": "Փորձել անվճար", "template": "Լիդերի գնահատման ձևանմուշ",
        "listen": "Լսել", "subscribe": "Բաժանորդագրվել (RSS)", "soon": "Առաջին թողարկումը շուտով։",
        "heading": "Փոդքասթ", "tab": "Հայերեն",
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
    sub(channel, "link", site_url(cfg, f"podcast/#{lang}"))
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
    sub(image, "link", site_url(cfg, f"podcast/#{lang}"))
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
        sub(item, "link", site_url(cfg, f"podcast/#{episode['slug']}"))
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


PAGE_STYLE = """
  :root { --bg:#f6f1e6; --bg-alt:#fffcf5; --text-h:#211b12; --text:#6b6152; --text-muted:#8a7e6d; --border:#e6dbc3; --accent:#b3401f; --hot:#c53a2c; --warm:#a8710f; --cold:#5b6472; }
  @media (prefers-color-scheme: dark) { :root { --bg:#18130c; --bg-alt:#211a11; --text-h:#f4ead9; --text:#b6a993; --text-muted:#8d8069; --border:#382d1e; --accent:#e37a4c; --hot:#ea6a53; --warm:#dba43b; --cold:#8b93a3; } }
  * { box-sizing: border-box; }
  body { margin:0; font-family:"IBM Plex Sans", system-ui, sans-serif; background:var(--bg); color:var(--text); line-height:1.65; }
  h1, h2, h3 { font-family:"Fraunces", ui-serif, Georgia, serif; color:var(--text-h); line-height:1.25; }
  h1 { font-size:2rem; margin:8px 0 6px; } h2 { font-size:1.35rem; margin:40px 0 12px; } h3 { font-size:1.15rem; margin:0 0 4px; }
  a { color:var(--accent); }
  .wrap { max-width:760px; margin:0 auto; padding:0 24px; }
  header.nav { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:20px 0; flex-wrap:wrap; }
  .logo { display:flex; align-items:center; gap:8px; text-decoration:none; }
  .logo-dots { display:flex; gap:3px; } .logo-dots span { width:7px; height:7px; border-radius:999px; display:block; }
  .logo-dots span:nth-child(1){background:var(--hot)} .logo-dots span:nth-child(2){background:var(--warm)} .logo-dots span:nth-child(3){background:var(--cold)}
  .logo-word { font-family:"Fraunces", ui-serif, Georgia, serif; font-weight:600; font-size:1.15rem; color:var(--text-h); }
  .logo-word em { font-style:normal; color:var(--accent); }
  .langs a { margin-left:12px; color:var(--text-muted); font-size:0.9rem; }
  .intro { display:flex; gap:20px; align-items:center; margin:8px 0 8px; }
  .intro img { width:120px; height:120px; border-radius:14px; flex-shrink:0; }
  .episode { background:var(--bg-alt); border:1px solid var(--border); border-radius:12px; padding:20px; margin:16px 0; }
  .episode .meta { font-size:0.85rem; color:var(--text-muted); margin:0 0 10px; }
  .episode audio { width:100%; margin:6px 0 10px; }
  .episode ul { padding-left:20px; }
  .feed { font-size:0.9rem; }
  .cta-box { border:1px solid var(--accent); border-radius:12px; padding:18px 20px; margin:28px 0; }
  .cta { display:inline-block; background:var(--accent); color:#fff; padding:10px 20px; border-radius:8px; text-decoration:none; font-weight:600; margin:6px 12px 0 0; }
  footer { border-top:1px solid var(--border); padding:24px 0 40px; font-size:0.9rem; color:var(--text-muted); }
"""


def build_page(cfg: dict, by_lang: dict[str, list[dict]]) -> str:
    e = html.escape
    sections = []
    for lang in LANGUAGES:
        t = TEXT[lang]
        show = cfg["shows"][lang]
        try_url, template_url = cta_links(cfg, lang)
        episodes = by_lang.get(lang, [])
        cards = []
        for ep in episodes:
            day = dt.date.fromisoformat(ep["date"]).isoformat()
            transcript = (
                f' · <a href="transcripts/{e(ep["transcript"])}">{e(t["transcript"])}</a>' if ep.get("transcript") else ""
            )
            cards.append(
                f'<article class="episode" id="{e(ep["slug"])}">'
                f"<h3>{e(ep['title'])}</h3>"
                f'<p class="meta">{day} · {clock(ep["duration"])}{transcript}</p>'
                f'<audio controls preload="none" src="audio/{e(ep["audio"])}"></audio>'
                f"{show_notes_html(cfg, ep)}</article>"
            )
        feed = (
            f'<p class="feed"><a href="{e(site_url(cfg, feed_path(lang)))}">{e(t["subscribe"])}</a></p>' if episodes else ""
        )
        sections.append(
            f'<section id="{lang}" lang="{lang}"><h2>{e(show["title"])}</h2>'
            f"<p>{e(show['description'])}</p>{feed}"
            + ("".join(cards) or f"<p><em>{e(t['soon'])}</em></p>")
            + f'<div class="cta-box"><h3>{e(t["cta_title"])}</h3><p>{e(t["cta"])}</p>'
            f'<a class="cta" href="{e(try_url)}">{e(t["cta_button"])}</a>'
            f'<a href="{e(template_url)}">{e(t["template"])}</a></div></section>'
        )
    langs = " ".join(f'<a href="#{lang}">{e(TEXT[lang]["tab"])}</a>' for lang in LANGUAGES)
    feeds = "".join(
        f'<link rel="alternate" type="application/rss+xml" title="{e(cfg["shows"][lang]["title"])}" '
        f'href="{e(site_url(cfg, feed_path(lang)))}" />'
        for lang in LANGUAGES if by_lang.get(lang)
    )
    title = cfg["shows"]["en"]["title"]
    description = cfg["shows"]["en"]["description"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{e(title)} — CRM Scoring</title>
<meta name="description" content="{e(description)}" />
<link rel="canonical" href="{e(site_url(cfg, 'podcast/'))}" />
<meta property="og:type" content="website" />
<meta property="og:site_name" content="CRM Scoring" />
<meta property="og:url" content="{e(site_url(cfg, 'podcast/'))}" />
<meta property="og:title" content="{e(title)}" />
<meta property="og:description" content="{e(description)}" />
<meta property="og:image" content="{e(site_url(cfg, 'podcast/cover.png'))}" />
{feeds}
<link rel="icon" href="../assets/app-icon.png" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet" />
<style>{PAGE_STYLE}</style>
</head>
<body>
<div class="wrap">
  <header class="nav">
    <a class="logo" href="../"><span class="logo-dots"><span></span><span></span><span></span></span><span class="logo-word">CRM <em>Scoring</em></span></a>
    <nav class="langs">{langs}</nav>
  </header>
  <main>
    <div class="intro">
      <img src="cover.png" alt="" width="120" height="120" />
      <div><h1>{e(title)}</h1><p>{e(description)}</p></div>
    </div>
    {"".join(sections)}
  </main>
  <footer>&copy; {dt.date.today().year} CRM Scoring · <a href="mailto:{e(cfg['email'])}">{e(cfg['email'])}</a> · <a href="../terms.html">Terms</a> · <a href="../privacy.html">Privacy</a></footer>
</div>
</body>
</html>
"""


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


def add_to_sitemap(cfg: dict) -> None:
    sitemap = SITE / "sitemap.xml"
    if not sitemap.exists():
        return
    text = sitemap.read_text(encoding="utf-8")
    loc = site_url(cfg, "podcast/")
    if loc not in text:
        text = text.replace("</urlset>", f"  <url><loc>{loc}</loc></url>\n</urlset>")
        sitemap.write_text(text, encoding="utf-8")


def publish(today: dt.date | None = None, out: Path = SITE_PODCAST) -> dict[str, list[dict]]:
    cfg = settings()
    today = today or dt.datetime.now(YEREVAN).date()
    now = dt.datetime.now(YEREVAN).replace(microsecond=0)
    episodes = load_episodes(today)
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
    (out / "index.html").write_text(build_page(cfg, by_lang), encoding="utf-8")
    if out == SITE_PODCAST:
        add_to_sitemap(cfg)
    return by_lang


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--today", help="pretend it's this date (YYYY-MM-DD), to preview scheduled episodes")
    args = parser.parse_args(argv)
    by_lang = publish(dt.date.fromisoformat(args.today) if args.today else None)
    for lang in LANGUAGES:
        print(f"{lang}: {len(by_lang.get(lang, []))} episode(s)")
    print("Wrote docs/podcast/. Commit and push to put it on crmscoring.com/podcast/")


if __name__ == "__main__":
    main()
