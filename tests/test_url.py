import pytest

from app.utils.url import hash_link, normalize_url


def test_removes_utm_and_click_tracking_params():
    url = "https://example.com/a?utm_source=x&fbclid=1&gclid=2&mc_cid=3&mc_eid=4"
    assert normalize_url(url) == "https://example.com/a"


def test_keeps_other_params_in_order():
    url = "https://example.com/a?id=5&utm_source=x&ref=home"
    assert normalize_url(url) == "https://example.com/a?id=5&ref=home"


def test_removes_fragment():
    assert normalize_url("https://example.com/a#section") == "https://example.com/a"


def test_bare_domain_gets_trailing_slash():
    assert normalize_url("https://example.com") == "https://example.com/"


def test_host_is_lowercased():
    assert normalize_url("https://Example.COM/Path") == "https://example.com/Path"


@pytest.mark.parametrize(
    "bad_url",
    ["ftp://example.com/file", "javascript:alert(1)", "not a url"],
)
def test_rejects_non_http_schemes(bad_url):
    with pytest.raises(ValueError):
        normalize_url(bad_url)


def test_rejects_missing_host():
    with pytest.raises(ValueError):
        normalize_url("http:///path")


def test_hash_is_64_char_hex():
    digest = hash_link("https://example.com/")
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_hash_is_deterministic_and_unique():
    assert hash_link("https://a.com/") == hash_link("https://a.com/")
    assert hash_link("https://a.com/") != hash_link("https://b.com/")


def test_tracking_variants_share_one_hash():
    clean = normalize_url("https://example.com/story")
    tracked = normalize_url("https://example.com/story?utm_source=newsletter#top")
    assert hash_link(clean) == hash_link(tracked)