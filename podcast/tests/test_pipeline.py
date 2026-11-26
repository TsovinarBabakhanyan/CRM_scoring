"""Tests for the podcast pipeline's pure parts (no ffmpeg or Whisper needed)."""

import datetime as dt
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import common  # noqa: E402
import make_reel  # noqa: E402
import process_episode  # noqa: E402
import publish_feed  # noqa: E402

ROOT_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def words(*items):
    return [{"start": s, "end": e, "word": w} for s, e, w in items]


def test_srt_time_and_cues():
    assert common.srt_time(3725.4567) == "01:02:05,457"
    srt = common.to_srt([{"start": 0, "end": 1.5, "text": " Hi "}, {"start": 1.5, "end": 3, "text": "there"}])
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,500\nHi\n")
    assert "2\n00:00:01,500 --> 00:00:03,000\nthere" in srt


def test_clock():
    assert common.clock(75) == "1:15"
    assert common.clock(3725) == "1:02:05"


def test_caption_chunks_are_short_and_relative_to_the_clip():
    ws = words((9.0, 9.5, "skip"), (10.0, 10.3, "Which"), (10.3, 10.6, "leads"), (10.6, 10.9, "to"),
               (10.9, 11.2, "call"), (11.2, 11.6, "first?"), (13.0, 13.4, "Hot"), (13.4, 13.8, "ones."))
    chunks = common.caption_chunks(ws, start=10.0, end=14.0)
    assert [c["text"] for c in chunks] == ["Which leads to call", "first?", "Hot ones."]
    assert chunks[0]["start"] == 0.0
    assert chunks[2]["start"] == pytest.approx(3.0)
    assert all(c["end"] > c["start"] for c in chunks)


def test_caption_chunks_break_on_a_pause_and_armenian_full_stop():
    ws = words((0, 0.4, "Բարև"), (0.4, 0.8, "ձեզ։"), (0.9, 1.2, "Սա"), (2.5, 2.9, "փոդքասթ"))
    assert [c["text"] for c in common.caption_chunks(ws)] == ["Բարև ձեզ։", "Սա", "փոդքասթ"]


def test_parse_time_and_crop():
    assert make_reel.parse_time("1:05") == 65
    assert make_reel.parse_time("0:01:35.5") == 95.5
    assert "crop=1080:1920" in make_reel.crop_filter(0.5)
    assert "(iw-1080)*0.0" in make_reel.crop_filter(-3)


def test_build_filter_overlays_each_caption_in_its_window():
    graph, last = make_reel.build_filter("scale", 2, [{"start": 0, "end": 1}, {"start": 1, "end": 2.5}], 1300)
    assert last == "v2"
    assert "[v0][2:v]overlay=x=0:y=1300:enable='between(t,0.000,1.000)'[v1]" in graph
    assert "[v1][3:v]" in graph


def test_first_sentences():
    long = "This is a sentence about lead scoring that goes on. " * 10
    summary = process_episode.first_sentences(long)
    assert len(summary) <= 280 and summary.endswith(".")
    assert process_episode.first_sentences("Short one") == "Short one"


def test_loudnorm_second_pass_uses_measurements():
    f = process_episode.loudnorm_filter(
        {"input_i": "-23.1", "input_tp": "-4.0", "input_lra": "6.0", "input_thresh": "-33.5", "target_offset": "0.3"}
    )
    assert f.startswith("loudnorm=I=-16.0:TP=-1.5")
    assert "measured_I=-23.1" in f and "offset=0.3" in f and "linear=true" in f


@pytest.fixture
def site(tmp_path, monkeypatch):
    episodes = tmp_path / "episodes"
    monkeypatch.setattr(publish_feed, "EPISODES", episodes)
    root = tmp_path / "pipeline"
    root.mkdir()
    (root / "cover.png").write_bytes(b"png")
    monkeypatch.setattr(publish_feed, "ROOT", root)

    def add(slug, lang, date, **extra):
        folder = episodes / slug
        folder.mkdir(parents=True)
        (folder / f"{slug}.mp3").write_bytes(b"x" * 1234)
        (folder / f"{slug}.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n", encoding="utf-8")
        episode = {"slug": slug, "title": f"Title {slug} & more", "lang": lang, "date": date,
                   "summary": "About <lead> scoring", "duration": 754.4, "bytes": 1234,
                   "audio": f"{slug}.mp3", "srt": f"{slug}.srt", "transcript": None, **extra}
        (folder / "episode.json").write_text(json.dumps(episode), encoding="utf-8")

    return tmp_path / "public", add


def test_publish_writes_valid_feeds_per_language(site):
    out, add = site
    add("ep01", "en", "2026-11-20", chapters=[{"time": "0:00", "title": "Intro"}],
        links=[{"title": "Template", "url": "https://www.crmscoring.com/en/lead-scoring-template.html"}])
    add("ep02", "hy", "2026-11-21")
    add("ep03", "en", "2026-12-24")  # scheduled: not out yet
    by_lang = publish_feed.publish(dt.date(2026, 11, 26), out)
    assert {k: [e["slug"] for e in v] for k, v in by_lang.items()} == {"en": ["ep01"], "hy": ["ep02"]}

    channel = ET.parse(out / "rss.xml").getroot().find("channel")
    assert channel.find("language").text == "en"
    assert channel.find(f"{ITUNES}category").get("text") == "Business"
    items = channel.findall("item")
    assert len(items) == 1
    item = items[0]
    assert item.find("title").text == "Title ep01 & more"
    enclosure = item.find("enclosure")
    assert enclosure.get("url") == "https://www.crmscoring.com/podcast/audio/ep01.mp3"
    assert enclosure.get("length") == "1234" and enclosure.get("type") == "audio/mpeg"
    assert item.find(f"{ITUNES}duration").text == "754"
    assert item.find("pubDate").text == "Fri, 20 Nov 2026 09:00:00 +0400"
    assert "&lt;lead&gt;" in item.find("description").text  # escaped once, as HTML text
    assert "#pricing" in item.find("description").text

    assert ET.parse(out / "hy" / "rss.xml").getroot().find("channel/language").text == "hy"
    assert not (out / "ru").exists()
    assert (out / "audio" / "ep01.mp3").stat().st_size == 1234
    notes = (out / "notes" / "ep01.md").read_text(encoding="utf-8")
    assert "- 0:00 — Intro" in notes and "[Template](" in notes and "Try it free" in notes

    assert not (out / "index.html").exists()  # no podcast page on the website


def test_publish_finds_audio_already_on_the_site(site):
    out, add = site
    add("ep01", "en", "2026-11-20")
    publish_feed.publish(dt.date(2026, 11, 26), out)
    (publish_feed.EPISODES / "ep01" / "ep01.mp3").unlink()
    publish_feed.publish(dt.date(2026, 11, 26), out)  # no error: the published copy is used
    assert (out / "audio" / "ep01.mp3").exists()


import make_voice  # noqa: E402


def test_parse_script_reads_title_slug_paragraphs_and_reel():
    text = (ROOT_SCRIPTS / "ep01-which-leads-to-call-first.ru.md").read_text(encoding="utf-8")
    script = make_voice.parse_script(text)
    assert script["title"] == "Кому звонить первым?"
    assert script["slug"] == "ep01-which-leads-to-call-first-ru"
    assert script["paragraphs"][0] == "Здравствуйте! Это подкаст CRM Scoring."
    assert not any("*" in p or "[" in p or "✂" in p for p in script["paragraphs"])
    first, last = script["reel"]
    assert script["paragraphs"][first].startswith("Вот простой способ")
    assert script["paragraphs"][last].startswith("Идеально не будет")


def test_parse_script_all_languages_drop_the_host_name():
    for lang, opening in [("en", "Hi, and welcome to the CRM Scoring podcast."),
                          ("hy", "Բարև ձեզ։ Սա CRM Scoring փոդքասթն է։")]:
        script = make_voice.parse_script(
            (ROOT_SCRIPTS / f"ep01-which-leads-to-call-first.{lang}.md").read_text(encoding="utf-8"))
        assert script["paragraphs"][0] == opening
        assert script["reel"] is not None


def test_ssml_escapes_text():
    assert "&lt;b&gt; &amp;" in make_voice.ssml("<b> &", "hy", "hy-AM-AnahitNeural", "-5%")
    assert 'xml:lang="hy-AM"' in make_voice.ssml("x", "hy", "hy-AM-AnahitNeural", "0%")


def test_ai_voice_is_disclosed_in_show_notes():
    cfg = {"site": "https://www.crmscoring.com"}
    ep = {"title": "T", "lang": "hy", "summary": "S", "ai_voice": True}
    assert "արհեստական բանականության ձայնը" in publish_feed.show_notes_md(cfg, ep)
    assert "<em>" in publish_feed.show_notes_html(cfg, ep)


def test_publish_with_no_episodes_writes_nothing(site):
    out, _add = site
    assert publish_feed.publish(dt.date(2026, 11, 26), out) == {}
    assert not out.exists()
