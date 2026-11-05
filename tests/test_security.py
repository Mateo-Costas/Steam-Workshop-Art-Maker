"""Tests of the security hardening: verified downloads, archive names, profile
URLs, cookie domains and untrusted media.

    pytest tests/test_security.py
"""
import hashlib
import io
import sys
import time
import zipfile

import pytest
from PIL import Image


# ---------------------------------------------------------------------------
# Verified downloads
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, payload: bytes, headers=None):
        self.payload = payload
        self.headers = {"content-length": str(len(payload)), **(headers or {})}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        for start in range(0, len(self.payload), chunk_size):
            yield self.payload[start:start + chunk_size]


@pytest.fixture
def serve(monkeypatch):
    """serve(payload, headers) makes downloads.requests.get answer with ``payload``."""
    import downloads

    def install(payload: bytes, headers=None):
        monkeypatch.setattr(downloads.requests, "get",
                            lambda *_a, **_kw: _FakeResponse(payload, headers))
    return install


def test_download_accepts_the_expected_sha256(tmp_path, serve):
    from downloads import download_file
    payload = b"tool" * 100_000
    serve(payload)
    dest = download_file("https://example.invalid/tool.zip", tmp_path / "tool.zip", "tool",
                         sha256="SHA256:" + hashlib.sha256(payload).hexdigest().upper())
    assert dest.read_bytes() == payload
    assert not (tmp_path / "tool.zip.part").exists()


def test_download_rejects_a_tampered_file(tmp_path, serve):
    from downloads import IntegrityError, download_file
    serve(b"malicious payload")
    with pytest.raises(IntegrityError):
        download_file("https://example.invalid/tool.zip", tmp_path / "tool.zip", "tool",
                      sha256=hashlib.sha256(b"the real tool").hexdigest())
    assert not list(tmp_path.iterdir()), "nothing may be left behind"


def test_download_rejects_a_truncated_file(tmp_path, serve):
    from downloads import IntegrityError, download_file
    serve(b"half", headers={"content-length": "8"})
    with pytest.raises(IntegrityError):
        download_file("https://example.invalid/tool.zip", tmp_path / "tool.zip", "tool")
    assert not list(tmp_path.iterdir())


def test_download_can_be_cancelled(tmp_path, serve):
    from downloads import download_file
    serve(b"x" * 1_000_000)
    with pytest.raises(InterruptedError):
        download_file("https://example.invalid/big.zip", tmp_path / "big.zip", "big",
                      should_cancel=lambda: True)
    assert not list(tmp_path.iterdir())


def test_sha256_lists_are_parsed_like_sha256sum():
    from downloads import parse_sha256_list
    digest = "a" * 64
    text = (f"{'b' * 64}  ffmpeg-master-latest-win64-gpl-shared.zip\n"
            f"{digest} *ffmpeg-master-latest-win64-gpl.zip\n")
    assert parse_sha256_list(text, "ffmpeg-master-latest-win64-gpl.zip") == digest
    assert parse_sha256_list(text, "missing.zip") is None
    assert parse_sha256_list("nothex  file.zip", "file.zip") is None


def test_pinned_downloads_carry_a_sha256():
    import models
    import tools
    from processing import gif_encode
    for value in (models.ESRGAN_SHA256, models.CUGAN_SHA256, tools.RIFE_SHA256,
                  tools.GIFSKI_FALLBACK_SHA256, *(h for _u, h in gif_encode._GIFSICLE_DOWNLOADS)):
        assert len(value) == 64 and int(value, 16) >= 0
    assert all(url.startswith("https://") for url in
               (models.ESRGAN_URL, models.CUGAN_URL, tools.RIFE_URL, tools.FFMPEG_URL,
                tools.FFMPEG_SUMS_URL, tools.GIFSKI_FALLBACK_URL))


# ---------------------------------------------------------------------------
# Archive members
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("member, expected", [
    ("pkg/realcugan-ncnn-vulkan.exe", "realcugan-ncnn-vulkan.exe"),
    ("pkg\\models-se\\up2x-no-denoise.bin", "up2x-no-denoise.bin"),
    ("../../evil.exe", "evil.exe"),            # folders are dropped...
    ("pkg/..", None),                          # ...and dot names refused
    ("C:evil.exe", None),                      # drive-relative path
    ("pkg/ffmpeg.exe:stream", None),           # NTFS alternate data stream
    ("pkg/", None),
    ("pkg/.hidden.dll", None),
])
def test_archive_member_names(member, expected):
    from tools import safe_member_name
    assert safe_member_name(member) == expected


def test_rife_extracts_only_the_models_the_app_uses(tmp_path, monkeypatch):
    import tools
    archive = tmp_path / "rife.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for member in ("pkg/rife-ncnn-vulkan.exe", "pkg/vcomp140.dll", "pkg/vcomp140d.dll",
                       "pkg/input0.png", "pkg/README.md",
                       "pkg/rife-v4.6/flownet.bin", "pkg/rife-v4.6/flownet.param",
                       "pkg/rife-anime/flownet.bin", "pkg/rife-UHD/flownet.bin",
                       "pkg/../rife-v4/flownet.bin"):
            zf.writestr(member, b"0")
    data, rife = tmp_path / "data", tmp_path / "data" / "rife"
    monkeypatch.setattr(tools, "DATA_DIR", data)
    monkeypatch.setattr(tools, "RIFE_DIR", rife)
    monkeypatch.setattr(tools, "download_file", lambda *_a, **_kw: archive)
    tools.install_rife(tmp_path, lambda *_a: None)
    assert sorted(p.name for p in data.iterdir()) == ["rife", "rife-ncnn-vulkan.exe", "vcomp140.dll"]
    assert sorted(p.name for p in rife.iterdir()) == ["rife-v4", "rife-v4.6"]
    assert sorted(p.name for p in (rife / "rife-v4.6").iterdir()) == ["flownet.bin", "flownet.param"]


# ---------------------------------------------------------------------------
# Steam profile URLs and cookies
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw, expected", [
    ("gabelogannewell", "https://steamcommunity.com/id/gabelogannewell"),
    ("76561197960287930", "https://steamcommunity.com/profiles/76561197960287930"),
    ("https://steamcommunity.com/id/gabe/", "https://steamcommunity.com/id/gabe"),
    ("steamcommunity.com/profiles/76561197960287930/?xml=1",
     "https://steamcommunity.com/profiles/76561197960287930"),
    ("http://www.steamcommunity.com/id/gabe", "https://steamcommunity.com/id/gabe"),
])
def test_profile_urls_are_normalised(raw, expected):
    from steam_profile import profile_url
    assert profile_url(raw) == expected


@pytest.mark.parametrize("raw", [
    "https://evil.example/id/gabe", "https://steamcommunity.com.evil.example/id/gabe",
    "file:///C:/Windows/win.ini", "https://steamcommunity.com/market/", "", "name with spaces",
    "https://steamcommunity.com/id/../../login", "javascript:alert(1)",
])
def test_profile_urls_outside_steam_are_refused(raw):
    from steam_profile import profile_url
    with pytest.raises(ValueError):
        profile_url(raw)


def test_avatars_only_come_from_steam_https():
    from steam_profile import _is_avatar_url
    assert _is_avatar_url("https://avatars.steamstatic.com/abc_full.jpg")
    assert _is_avatar_url("https://avatars.fastly.steamstatic.com/abc_full.jpg")
    assert not _is_avatar_url("http://avatars.steamstatic.com/abc_full.jpg")
    assert not _is_avatar_url("https://avatars.steamstatic.com.evil.example/a.jpg")
    assert not _is_avatar_url("https://evil.example/steamstatic.com.jpg")


def test_only_real_steam_cookies_are_used():
    import requests
    import steam_uploader
    for domain in (".steamcommunity.com", "steamcommunity.com", "store.steampowered.com"):
        assert steam_uploader._is_steam_domain(domain), domain
    for domain in ("steamgifts.com", ".steamdb.info", "steamcommunity.com.evil.example",
                   "notsteamcommunity.com", ""):
        assert not steam_uploader._is_steam_domain(domain), domain
    jar = requests.cookies.RequestsCookieJar()
    jar.set("steamLoginSecure", "secret", domain=".steamcommunity.com", path="/")
    jar.set("session", "other-site", domain=".steamgifts.com", path="/")
    sent = steam_uploader._pw_cookies_from_jar(jar)
    assert [c["domain"] for c in sent] == [".steamcommunity.com"]


# ---------------------------------------------------------------------------
# Untrusted media
# ---------------------------------------------------------------------------
def test_truncated_gifs_do_not_crash_the_parser(tmp_path, media):
    from gif_utils import playback_fps, read_timing
    data = media["gif25"].read_bytes()
    full = read_timing(media["gif25"]).frames
    for cut in (14, 40, 400, len(data) // 3, len(data) - 5):
        broken = tmp_path / f"cut_{cut}.gif"
        broken.write_bytes(data[:cut])
        timing = read_timing(broken)  # never IndexError / struct.error
        assert 0 <= timing.frames <= full
        assert playback_fps(broken) > 0
    (tmp_path / "tiny.gif").write_bytes(b"GIF89a\x01")
    with pytest.raises(ValueError):
        read_timing(tmp_path / "tiny.gif")


def test_disguised_image_formats_are_refused(tmp_path):
    from gif_utils import open_image
    disguised = tmp_path / "art.png"
    Image.new("RGB", (8, 8), "red").save(disguised, format="TIFF")  # TIFF named .png
    with pytest.raises(OSError):
        open_image(disguised)
    real = tmp_path / "real.png"
    Image.new("RGB", (8, 8), "red").save(real)
    with open_image(real) as image:
        assert image.size == (8, 8)
    webp = tmp_path / "art.webp"
    Image.new("RGB", (8, 8), "blue").save(webp)
    with open_image(webp) as image:
        assert image.format == "WEBP"


def test_avatar_decoding_is_limited_to_web_formats():
    from steam_profile import _AVATAR_FORMATS
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buffer, format="TIFF")
    with pytest.raises(OSError):
        Image.open(io.BytesIO(buffer.getvalue()), formats=_AVATAR_FORMATS)


# ---------------------------------------------------------------------------
# External tools
# ---------------------------------------------------------------------------
def test_cancel_stops_a_running_tool_at_once():
    from processing.common import run_tool
    started = time.monotonic()
    with pytest.raises(InterruptedError):
        run_tool([sys.executable, "-c", "import time; time.sleep(30)"], timeout=60,
                 should_cancel=lambda: time.monotonic() - started > 0.5)
    assert time.monotonic() - started < 5


def test_tools_run_with_closed_stdin_and_timeouts():
    from processing.common import run_tool
    result = run_tool([sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"],
                      timeout=30)
    assert result.returncode == 0 and result.stdout.strip() == "''"
    slow = run_tool([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)
    assert slow.returncode == -1 and "timeout" in slow.stderr
    missing = run_tool(["definitely-not-a-real-tool-xyz"], timeout=5)
    assert missing.returncode == -1
