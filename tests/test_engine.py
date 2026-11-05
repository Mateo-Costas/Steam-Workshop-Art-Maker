"""Tests of the processing engine: timing, geometry, Steam limits and sync.

    pip install pytest
    pytest tests
"""
import pytest

from gif_utils import open_gif, playback_fps, read_timing
from processing.common import FRAGMENT_MAX_BYTES


def assert_fragment_set(processor, source, preset):
    """Every piece fits Steam, is patched, readable, sized per preset and in sync."""
    cfg = processor.preset_config(preset)
    fragments = processor.list_fragments(source)
    assert len(fragments) == len(cfg["parts"])
    durations = []
    for (_name, width, _left), fragment in zip(cfg["parts"], fragments):
        assert fragment.stat().st_size <= FRAGMENT_MAX_BYTES
        if fragment.suffix != ".gif":
            continue
        timing = read_timing(fragment)
        assert timing.width == width
        if cfg["fixed_h"]:
            assert timing.height == cfg["fixed_h"]
        assert fragment.read_bytes()[-1] == 0x21, "falta el parche de Steam"
        with open_gif(fragment) as image:  # still readable despite the patch
            assert image.size == (timing.width, timing.height)
        durations.append(timing.duration_ms)
    if durations:
        assert max(durations) - min(durations) <= 40, f"piezas desincronizadas: {durations}"
    assert processor.read_fragments_manifest(source)["parametros"]["preset"] == preset
    return fragments, durations


# ---------------------------------------------------------------------------
# gif_utils
# ---------------------------------------------------------------------------
def test_playback_fps(media):
    assert playback_fps(media["gif25"]) == pytest.approx(25, abs=0.6)
    assert playback_fps(media["gif30"]) == pytest.approx(30, abs=0.6)
    assert playback_fps(media["square"]) == pytest.approx(10, abs=0.6)
    assert playback_fps(media["variable"]) == pytest.approx(25, abs=0.6)


def test_patched_gif_is_readable(tmp_path, media):
    patched = tmp_path / "patched.gif"
    patched.write_bytes(media["gif25"].read_bytes()[:-1] + b"\x21")
    assert read_timing(patched).frames == read_timing(media["gif25"]).frames
    with open_gif(patched) as image:
        assert image.n_frames == 50


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------
def test_video_to_gif_keeps_aspect_ratio(processor, work):
    video = work("vertical")
    result = read_timing(processor.convert_video_to_gif(video, video.with_suffix(".gif"), 24))
    assert (result.width, result.height) == (360, 640)  # narrower than 638: not upscaled
    assert result.duration_ms == pytest.approx(2000, abs=60)


def test_video_to_gif_cover_and_trim(processor, work):
    video = work("vertical")
    out = processor.convert_video_to_gif(video, video.with_suffix(".gif"), 24,
                                         start_s=0.5, end_s=1.5, size=(638, 354))
    result = read_timing(out)
    assert (result.width, result.height) == (638, 354)
    assert result.duration_ms == pytest.approx(1000, abs=60)


def test_color_enhancement_keeps_every_delay(processor, work):
    source = work("variable")
    result = processor.enhance_colors(source, 1.2, 1.1, vibrance=0.3, sharpness=0.2, temperature=0.2)
    assert result != source
    assert read_timing(result).delays == read_timing(source).delays


def test_assembly_accepts_any_frame_names_and_caps_at_50_fps(processor, work, tmp_path):
    frames, fps = processor.extract_gif_frames(work("gif25"), tmp_path / "frames")
    assert len(frames) == 50 and fps == pytest.approx(25)
    renamed = tmp_path / "rife"
    renamed.mkdir()
    for index, frame in enumerate(frames, 1):  # rife-ncnn-vulkan naming
        (renamed / f"frame{index:08d}.png").write_bytes(frame.read_bytes())
    names = sorted(renamed.glob("*.png"))
    normal = tmp_path / "normal.gif"
    assert processor.create_optimized_gif(names, normal, 25)
    assert read_timing(normal).duration_ms == pytest.approx(2000, abs=40)
    fast = tmp_path / "fast.gif"
    assert processor.create_optimized_gif(names, fast, 100)  # 100 fps -> 50 fps, same speed
    timing = read_timing(fast)
    assert min(timing.delays) >= 20
    assert timing.duration_ms == pytest.approx(500, abs=40)


# ---------------------------------------------------------------------------
# Fragmentation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("preset", ["workshop_5part", "artwork_2part", "featured_630",
                                    "artwork_4grid", "panorama_5_630", "workshop_5slot_119"])
def test_presets(processor, work, preset):
    source = work("gif30")
    assert processor.fragment_media(source, preset), processor._last_split_error
    _fragments, durations = assert_fragment_set(processor, source, preset)
    assert durations[0] == pytest.approx(read_timing(source).duration_ms, abs=90)


def test_ffmpeg_fallback_stays_in_sync(processor, work):
    processor.gifski_path = None
    source = work("gif30")
    assert processor.fragment_media(source, "screenshot_4grid"), processor._last_split_error
    assert_fragment_set(processor, source, "screenshot_4grid")


def test_video_is_fragmented_directly(processor, work):
    video = work("vertical")
    assert processor.fragment_media(video, "workshop_5part"), processor._last_split_error
    fragments, _ = assert_fragment_set(processor, video, "workshop_5part")
    assert not video.with_suffix(".gif").exists(), "no debe crear GIFs junto al video"
    assert all("_resized_temp" not in f.name for f in fragments)


def test_names_with_accents(processor, work):
    source = work("accents")
    assert processor.fragment_media(source, "artwork_2part"), processor._last_split_error
    assert_fragment_set(processor, source, "artwork_2part")


def test_still_image_becomes_jpeg_pieces(processor, work):
    image = work("image")
    assert processor.fragment_media(image, "panorama_5_630")
    fragments = processor.list_fragments(image)
    assert [f.suffix for f in fragments] == [".jpg"] * 5


def test_source_inside_output_folder_is_kept(processor, work):
    source = work("square")
    assert processor.fragment_media(source, "screenshot_638")
    inside = processor.get_fragments_dir(source) / "copy.gif"
    inside.write_bytes(source.read_bytes())
    assert processor.fragment_media(inside, "screenshot_638")
    assert inside.exists()


def test_size_optimizer_keeps_sync_and_speed(processor, work):
    source = work("gif30")
    assert processor.fragment_media(source, "screenshot_4grid")
    pieces = processor.list_fragments(source)
    outputs = processor.shrink_batch_to_size_cap(pieces, max_mb=0.2)
    assert all(outputs)
    durations = [read_timing(o).duration_ms for o in outputs]
    assert all(o.stat().st_size <= 0.2 * 1048576 for o in outputs)
    assert max(durations) - min(durations) <= 40
    assert durations[0] == pytest.approx(read_timing(pieces[0]).duration_ms, abs=80)


# ---------------------------------------------------------------------------
# Shared encoder: searches, single decode and gifski (simulated)
# ---------------------------------------------------------------------------
def _run_search(table, max_bytes=100):
    """_shared_search over synthetic jobs: table[job][candidate] = output size.

    Returns (best, candidate each job's "file" holds at the end, encode calls).
    """
    from processing.splitting import _shared_search
    files, copies, calls = {}, {}, []

    def encode(job, candidate):
        calls.append((job, candidate))
        files[job] = candidate
        return table[job][candidate]

    def keep(job):
        copies[job] = files[job]

    def restore(job):
        files[job] = copies[job]

    order = sorted(range(len(table)), key=lambda j: -table[j][0])  # heaviest first
    best = _shared_search(len(table[0]), order, encode, max_bytes, keep, restore)
    return best, files, calls


def test_shared_search_matches_brute_force():
    import random
    rng = random.Random(1234)
    for _case in range(400):
        jobs, count = rng.randint(1, 6), rng.choice((1, 2, 5, 13, 86))
        table = []
        for _job in range(jobs):
            size, sizes = rng.randint(50, 400), []
            for _candidate in range(count):  # sizes never grow along the candidates
                sizes.append(size)
                size = max(1, size - rng.randint(0, 12))
            table.append(sizes)
        expected = next((c for c in range(count) if all(t[c] <= 100 for t in table)), None)
        best, files, calls = _run_search(table)
        assert best == expected
        if best is not None:  # every output left at the chosen candidate
            assert all(files[job] == best for job in range(jobs))
        steps = count.bit_length() + 1  # one binary search per pilot
        assert len(calls) <= jobs + jobs * (steps + jobs), "too many encodes"


def test_shared_search_costs():
    best, _files, calls = _run_search([[90] * 86] * 5)  # everything fits at the best quality
    assert best == 0 and len(calls) == 5
    best, _files, calls = _run_search([[500] * 86] * 5)  # nothing fits: rejected at once
    assert best is None and len(calls) == 2
    # the heaviest piece decides: one encode per search step, the rest once at the end
    table = [[200 - 2 * c for c in range(86)]] + [[90 - c // 2 for c in range(86)]] * 4
    best, files, calls = _run_search(table)
    assert best == 50 and len(calls) <= 1 + 8 + 4
    assert set(files.values()) == {50}


def test_one_decode_feeds_every_piece():
    from processing.splitting import shared_graph
    graph, labels = shared_graph("25", "scale=638:354", ["crop=127:354:0:0", "crop=127:354:127:0"])
    assert graph == ("[0:v]fps=25,scale=638:354,split=2[s0][s1];"
                     "[s0]crop=127:354:0:0[o0];[s1]crop=127:354:127:0[o1]")
    assert labels == ["[o0]", "[o1]"]
    assert shared_graph("10", "", [""]) == ("[0:v]fps=10,null[o0]", ["[o0]"])


@pytest.fixture
def fake_gifski(processor, tmp_path, monkeypatch):
    """Swap gifski for an in-process stand-in whose output size grows with --quality.

    It writes a real GIF (Pillow) of the frames and pads it with comment blocks
    up to ``size_for(quality)`` bytes. Returns (calls, settings): the quality of
    every call, and a dict whose "size_for" can be replaced by the test.
    """
    import subprocess
    from pathlib import Path
    from PIL import Image
    from processing import splitting

    exe = tmp_path / "gifski-standin"
    exe.write_bytes(b"")
    processor.gifski_path = exe
    calls, settings = [], {"size_for": lambda quality: 0}
    real_run_tool = splitting.run_tool

    def run_tool(cmd, timeout, should_cancel=None):
        if str(cmd[0]) != str(exe):
            return real_run_tool(cmd, timeout, should_cancel=should_cancel)
        args = [str(a) for a in cmd[1:]]
        fps, quality = float(args[args.index("--fps") + 1]), int(args[args.index("--quality") + 1])
        output, pattern = Path(args[args.index("-o") + 1]), Path(args[-1])
        frames = [Image.open(f).convert("RGB") for f in sorted(pattern.parent.glob(pattern.name))]
        frames[0].save(output, save_all=True, append_images=frames[1:], loop=0,
                       duration=round(1000 / fps), optimize=False)
        data = output.read_bytes()
        padding, need = bytearray(), settings["size_for"](quality) - len(data)
        while need > 4:
            chunk = min(255, need - 4)
            padding += b"\x21\xfe" + bytes([chunk]) + b"#" * chunk + b"\x00"
            need -= chunk + 4
        output.write_bytes(data[:-1] + bytes(padding) + data[-1:])
        calls.append(quality)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(splitting, "run_tool", run_tool)
    return calls, settings


def test_gifski_takes_one_pass_when_the_best_quality_fits(processor, work, fake_gifski):
    calls, _settings = fake_gifski
    source = work("square")
    assert processor.fragment_media(source, "workshop_5slot_119"), processor._last_split_error
    assert calls == [95] * 5  # previously 7 rounds of a binary search
    assert processor.read_fragments_manifest(source)["parametros"]["quality"] == 95
    assert_fragment_set(processor, source, "workshop_5slot_119")


def test_gifski_keeps_the_best_quality_that_fits(processor, work, fake_gifski):
    from processing.common import FRAGMENT_MAX_BYTES
    calls, settings = fake_gifski
    settings["size_for"] = lambda quality: int(FRAGMENT_MAX_BYTES * quality / 60.5)
    source = work("square")
    assert processor.fragment_media(source, "workshop_5slot_119"), processor._last_split_error
    assert processor.read_fragments_manifest(source)["parametros"]["quality"] == 60
    fragments, _ = assert_fragment_set(processor, source, "workshop_5slot_119")
    # the files on disk are the q=60 ones, even though later tries overwrote them
    assert {f.stat().st_size for f in fragments} == {settings["size_for"](60)}
    # q95 fails on the heaviest piece, which is searched alone (q10 first), then
    # the other 4 pieces are encoded once at q60 (the old binary search: 18 runs)
    assert calls[:2] == [95, 10] and len(calls) <= 1 + 1 + 7 + 4


def test_cancelled_fragmentation_leaves_no_partial_set(processor, work, fake_gifski):
    calls, _settings = fake_gifski
    source = work("square")
    with pytest.raises(InterruptedError):
        processor.fragment_media(source, "workshop_5slot_119", should_cancel=lambda: len(calls) >= 2)
    assert processor.list_fragments(source) == []


# ---------------------------------------------------------------------------
# Color adjustments
# ---------------------------------------------------------------------------
def test_color_presets_are_valid_and_neutral_is_lossless(processor, media):
    from processing.enhance import COLOR_PRESETS, COLOR_RANGES, NEUTRAL_COLORS, clamp_colors
    for key, values in COLOR_PRESETS.items():
        assert set(values) == set(COLOR_RANGES), key
        assert clamp_colors(values) == values, f"{key} fuera de rango"
    assert clamp_colors({"contrast": 9, "saturation": "x", "vibrance": float("nan"),
                         "temperature": -4}) == {
        "contrast": 2.0, "saturation": 1.3, "vibrance": 0.0, "sharpness": 0.0, "temperature": -1.0}
    from gif_utils import open_image
    with open_image(media["image"]) as image:
        original = image.convert("RGB")
    assert processor.apply_color_adjustments(original, **NEUTRAL_COLORS).tobytes() == original.tobytes()


def test_parallel_color_enhancement_keeps_frame_order(processor, work):
    import numpy as np
    from gif_utils import open_gif
    source = work("variable")  # every frame has its own colour
    result = processor.enhance_colors(source, 1.3, 1.2)

    def means(path, adjust):
        with open_gif(path) as gif:
            out = []
            for index in range(gif.n_frames):
                gif.seek(index)
                frame = gif.convert("RGB")
                if adjust:
                    frame = processor.apply_color_adjustments(frame, 1.3, 1.2)
                out.append(np.asarray(frame, float).mean(axis=(0, 1)))
            return np.array(out)

    expected, produced = means(source, True), means(result, False)
    assert len(produced) == len(expected)
    for index, color in enumerate(produced):  # closest expected frame is its own
        assert int(np.argmin(np.abs(expected - color).sum(axis=1))) == index


# ---------------------------------------------------------------------------
# AI (skipped when Real-ESRGAN or its models are not installed)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("model", ["realesr-animevideov3-x2", "realesrgan-x4plus"])
def test_upscale_uses_the_native_scale(processor, work, tmp_path, model):
    if not processor.realesrgan_path or model not in processor.model_manager.check_available_models():
        pytest.skip("Real-ESRGAN o el modelo no están instalados")
    import numpy as np
    from PIL import Image
    frames, _ = processor.extract_gif_frames(work("gif25"), tmp_path / "in", max_width=96)
    for extra in frames[2:]:
        extra.unlink()
    upscaled = processor.upscale_frames_batch(tmp_path / "in", tmp_path / "out", model)
    assert upscaled
    scale = processor.model_manager.model_scale(model)
    with Image.open(frames[0]) as original, Image.open(upscaled[0]) as result:
        assert result.size == (original.width * scale, original.height * scale)
        back = np.asarray(result.convert("RGB").resize(original.size, Image.Resampling.BOX), float)
        mse = ((back - np.asarray(original.convert("RGB"), float)) ** 2).mean()
        assert 10 * np.log10(255 ** 2 / max(mse, 1e-9)) > 22, "salida desordenada"
