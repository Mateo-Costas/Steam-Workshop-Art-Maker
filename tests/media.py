"""Small generated test media shared by the pytest suite and ui_check.py."""
import subprocess
from pathlib import Path
from typing import Dict

from PIL import Image, ImageDraw


def make_media(folder: Path, ffmpeg: Path) -> Dict[str, Path]:
    """Create the test files in ``folder`` with ``ffmpeg``; returns name -> path."""
    folder.mkdir(parents=True, exist_ok=True)

    def run(*args):
        subprocess.run([str(ffmpeg), "-v", "error", "-y", *map(str, args)], check=True)

    palette = "split[a][b];[a]palettegen[p];[b][p]paletteuse"
    files = {
        "gif25": folder / "wide_25fps.gif",
        "gif30": folder / "big_30fps.gif",
        "square": folder / "square_10fps.gif",
        "vertical": folder / "vertical_30fps.mp4",
        "wide_video": folder / "wide_24fps.mp4",
        "image": folder / "static.png",
        "accents": folder / "canción_ñ.gif",
        "variable": folder / "variable_delay.gif",
    }
    run("-f", "lavfi", "-t", "2", "-i", "testsrc2=size=320x180:rate=25", "-vf", palette, files["gif25"])
    run("-f", "lavfi", "-t", "2", "-i", "testsrc2=size=960x540:rate=30", "-vf", palette, files["gif30"])
    run("-f", "lavfi", "-t", "2", "-i", "mandelbrot=size=200x200:rate=10", "-vf", palette, files["square"])
    run("-f", "lavfi", "-t", "2", "-i", "testsrc2=size=360x640:rate=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", files["vertical"])
    run("-f", "lavfi", "-t", "3", "-i", "testsrc2=size=640x360:rate=24",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", files["wide_video"])
    run("-f", "lavfi", "-i", "testsrc2=size=1200x800", "-frames:v", "1", files["image"])
    files["accents"].write_bytes(files["gif25"].read_bytes())

    frames = []
    for i in range(12):
        frame = Image.new("RGB", (240, 135), (20 * i, 60, 200 - 15 * i))
        ImageDraw.Draw(frame).rectangle([i * 18, 50, i * 18 + 20, 85], fill=(255, 255, 0))
        frames.append(frame)
    frames[0].save(files["variable"], save_all=True, append_images=frames[1:], loop=0,
                   duration=[40, 40, 40, 120, 40, 40, 200, 40, 40, 40, 80, 40])
    return files
