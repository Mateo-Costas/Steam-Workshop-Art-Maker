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
