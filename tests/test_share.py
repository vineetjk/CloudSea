from __future__ import annotations

import io
from datetime import date

from PIL import Image

from cloudsea import share


def test_cards_have_the_right_size_and_stay_small(sample_call):
    for verdict, p in (("SKIP", 0.08), ("MAYBE", 0.41), ("GO", 0.93)):
        call = {**sample_call, "verdict": verdict, "probability": p}
        for render, size in ((share.render_og, (1200, 630)), (share.render_story, (1080, 1920))):
            png = render(call)
            im = Image.open(io.BytesIO(png))
            assert im.format == "PNG" and im.size == size
            assert len(png) < 300 * 1024


def test_cards_are_cached_per_issue(sample_call):
    a = share.card_png("og", sample_call)
    assert share.card_png("og", sample_call) is a
    later = {**sample_call, "issued_at": sample_call["issued_at"].replace(minute=45), "verdict": "GO"}
    assert share.card_png("og", later) is not a


def test_titles_and_dates(sample_call):
    assert share.og_title(sample_call) == "SKIP · 8% cloud sea · Sun 11 Oct"
    assert share.day_long(date(2026, 10, 11)) == "Sunday 11 Oct"
    assert share.og_description(sample_call) == "SKIP for Sunday."
    assert share.og_description(None) == share.DEFAULT_DESCRIPTION
    assert share.og_description({"text": ""}) == share.DEFAULT_DESCRIPTION


def test_share_page_has_open_graph_tags_and_sends_people_on(sample_call):
    page = share.share_html(sample_call, date(2026, 10, 11), base_url="https://api.example.org/",
                            web_base_url="https://cloudsea.example.org")
    assert '<meta property="og:title" content="SKIP · 8% cloud sea · Sun 11 Oct">' in page
    assert 'content="https://api.example.org/og/2026-10-11.png?v=' in page
    assert '<meta name="twitter:card" content="summary_large_image">' in page
    assert 'http-equiv="refresh" content="0; url=https://cloudsea.example.org/#/?d=2026-10-11"' in page


def test_share_page_escapes_call_text(sample_call):
    call = {**sample_call, "text": 'Skip "this" <script>alert(1)</script>. More.'}
    page = share.share_html(call, date(2026, 10, 11), base_url="http://x/", web_base_url="http://y")
    assert "<script>alert" not in page and "&lt;script&gt;" in page


def test_share_page_without_a_call_has_no_image():
    page = share.share_html(None, date(2026, 10, 11), base_url="http://x/", web_base_url="http://y")
    assert "og:image" not in page and "Tomorrow&#x27;s sunrise call for Nandi Hills" in page
