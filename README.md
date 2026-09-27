# WorkshopArt

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![AI](https://img.shields.io/badge/AI-Real--ESRGAN%20%7C%20Real--CUGAN%20%7C%20RIFE-orange)
![Version](https://img.shields.io/badge/Version-2.1-blue)
![Lang](https://img.shields.io/badge/Lang-ES%20%7C%20EN%20%7C%20PT--BR-green)

**Animated GIF artwork for every Steam profile showcase.**

Turn videos, GIFs and images into upload-ready pieces for the Artwork, Screenshot and Workshop showcases: every piece stays under Steam's 5 MB limit, all the pieces of a layout play in sync, and the trailer-byte patch is applied so Steam shows them at full size.

[⬇ Download the .exe (Itch.io)](https://mxteoo7.itch.io/workshopart-pro) · [Releases](../../releases) · [⭐ Patreon](https://www.patreon.com/mxteoo7) · [Report a bug](../../issues/new)

</div>

---

The full app is free for personal use. The source is public so you can read and verify it, but it is **not** open source: see [LICENSE](LICENSE).

---

## What's new in v2.1

A quality release: no new features, everything that was there now works as intended.

- **Correct playback speed**: GIFs above 20 fps (and RIFE results) no longer play slowed down, and variable frame delays are preserved.
- **No distortion**: videos and GIFs that are not 16:9 are cropped to the showcase instead of stretched.
- **Pieces always in sync**: every preset encodes all its pieces with one shared frame rate and quality, including the FFmpeg fallback and the ≤ 5 MB optimizer (which used to wreck the timing).
- **AI fixes**: the 2x/3x models no longer produce scrambled images, the right model is used when `realesrgan-ncnn-py` is installed, and Real-CUGAN is downloaded and detected correctly.
- **RIFE works** again ("Smooth animation" always failed on Windows).
- **Step 4** copies the console snippet that matches your format (artwork, screenshot, workshop or panorama), and the Upload Tool opens with the right preset.
- **Safer files**: converting a video never overwrites a GIF of the same name next to it.
- **First launch**: gifski downloads again (new release format), a failed AI-model download no longer stops the app from opening, and the startup screen stays responsive.
- **GPU detection** works on current Windows 11 (no `wmic`) and shows the real VRAM of cards above 4 GB.
- **Drag & drop** no longer closes the app, and works with accented or Japanese file names.
- Fully translated interface (ES/EN/PT), stacked layout for narrow windows, and Python 3.13/3.14 support.

---

## Features

- **10 showcase presets** covering every profile layout (table below), with a live preview of the cut before fragmenting.
- **AI upscaling** with Real-ESRGAN and Real-CUGAN (GPU via Vulkan, CPU fallback). Tell the app whether your content is anime and it picks the best model.
- **Frame interpolation** with RIFE (2x or 4x frames) for smoother animations.
- **Color adjustments**: contrast, saturation, vibrance, sharpness and temperature, with an animated live preview.
- **Video → GIF** with trim, frame rate and size options.
- **1-click pipeline**: AI + colors + fragmentation in one go.
- **≤ 5 MB optimizer** for GIFs you already have, keeping a set of pieces in sync.
- **Steam tools**: console snippet per format, automatic Upload Tool, profile check (public, level 10+) and ZIP export with instructions.
- **Interface in Spanish, English and Portuguese**, adjustable text size, drag & drop, keyboard shortcuts.
- **Zero setup**: FFmpeg, gifski, gifsicle, the AI models and RIFE are downloaded on first launch.

---

## Showcase presets

| Preset | Pieces | Size of each piece | Upload as |
|---|---|---|---|
| Workshop Showcase · 5 parts | 5 | 127 × 354 (one 638 × 354 image cut into columns) | Workshop |
| Artwork · main + side | 2 | 506 and 100 px wide, any height | Artwork |
| Featured Artwork | 1 | 630 px wide, any height | Artwork |
| Single artwork 16:9 | 1 | 630 × 354 | Artwork |
| Artwork 4-grid | 4 | 245 × 245 | Artwork |
| Panorama | 5 | 630 × 360 | Artwork (size trick) |
| Screenshot · 1 slot | 1 | 638 × 354 | Screenshot |
| Screenshot · 4 pieces | 4 | 638 × 354 | Screenshot |
| Workshop · 5 squares | 5 | 150 × 150 | Workshop |
| Workshop · 5 squares (native) | 5 | 119 × 119 | Workshop |

The source is scaled to fill the layout and center-cropped (never stretched). Presets with "any height" keep the source aspect ratio. Animated pieces are encoded with gifski (best quality that fits) or FFmpeg as a fallback; still images become JPEG pieces.

---

## Requirements

| | |
|---|---|
| **OS** | Windows 10 / 11 (64-bit) |
| **Python** | 3.10 or newer (only to run from source) |
| **GPU** | Any Vulkan-capable GPU recommended for the AI (NVIDIA, AMD, Intel Arc). CPU works, slower. |
| **Disk** | About 1 GB for the tools and models downloaded on first launch |
| **Internet** | Needed on first launch for those downloads |

---

## Run from source

```bash
git clone https://github.com/Mateo-Costas/Steam-Workshop-Art-Maker.git
cd Steam-Workshop-Art-Maker
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

On first launch the app downloads FFmpeg, gifski, gifsicle, Real-ESRGAN, Real-CUGAN and RIFE into `SteamWorkshopAppData/` next to `main.py`. Optional extras:

```bash
pip install playwright browser_cookie3   # automatic upload with the Upload Tool
pip install realesrgan-ncnn-py           # slightly faster Real-ESRGAN
```

---

## How to use

1. **File**: drop a video, GIF or image on the window (or `Ctrl+O`) and say whether it is anime.
2. **Process** (optional): AI upscaling, color adjustments, video → GIF or RIFE smoothing.
3. **Fragment**: pick the showcase preset, check the preview and click *Fragment*. Pieces are saved in `<name>_workshop/fragmentos/` next to your file.
4. **Upload**: use the Upload Tool, or upload manually as below.

Shortcuts: `Ctrl+O` open file · `Ctrl+1…4` go to a step · `F1` help.

---

## Uploading to Steam manually

1. Open `https://steamcommunity.com/sharedfiles/edititem/767/3/`.
2. Open the browser console (**F12 → Console**), paste the snippet for your format (step 4's *Copy JS* button copies the right one) and press Enter.
3. Upload the file, give it a title, tick the agreement box and save. Repeat for every piece.
4. Edit your profile and place each piece in its showcase slot. Showcases need a level 10+ account.

**Workshop**
```javascript
$J('[name=consumer_app_id]').val(480);
$J('[name=file_type]').val(0);
$J('[name=visibility]').val(0);
```

**Artwork**
```javascript
$J('[name=consumer_app_id]').val(767);
$J('[name=file_type]').val(3);
$J('[name=visibility]').val(0);
```

**Screenshot**
```javascript
$J('[name=consumer_app_id]').val(767);
$J('[name=file_type]').val(5);
$J('[name=visibility]').val(0);
```

**Panorama** (artwork with faked dimensions so Steam accepts the wide banner)
```javascript
$J('#image_width').val(1000).attr('id', '');
$J('#image_height').val(1).attr('id', '');
$J('[name=consumer_app_id]').val(767);
$J('[name=file_type]').val(3);
$J('[name=visibility]').val(0);
```

The **Upload Tool** does all of this automatically with your Steam session in Firefox (read through `browser_cookie3`; current Chrome and Edge encrypt their cookies so other programs cannot read them) or a `steam_cookies.json` file next to the app. Close Firefox before uploading, and never share that file: it contains your Steam session.

---

## GIF requirements on Steam

| Property | Value |
|---|---|
| Max size | **5 MiB (5,242,880 bytes)** per file; WorkshopArt keeps 16 KiB of margin |
| Last byte | `0x21` instead of the `0x3B` trailer, so Steam shows the GIF at full size (applied automatically) |
| Loop | Infinite |
| Sync | All pieces of a layout share frame rate and duration |

---

## AI models

Downloaded automatically (also from *Download models* in step 2):

| Model | Scale | Best for |
|---|---|---|
| `realesr-animevideov3-x2 / x3 / x4` | 2x / 3x / 4x | Anime and games (fast) |
| `realesrgan-x4plus-anime` | 4x | Anime illustrations |
| `realesrgan-x4plus` | 4x | General content |
| Real-CUGAN SE (2x, 3x, 4x) | 2x–4x | Anime, with optional denoise |

Other Real-ESRGAN `.bin`/`.param` pairs copied into `SteamWorkshopAppData/models/` appear in the list too.

---

## Project structure

```
Steam-Workshop-Art-Maker/
├── main.py                 # entry point: first-run downloads + main window (--upload-tool)
├── upload_tool.py          # Upload Tool window
├── WorkshopArt.spec        # PyInstaller build
├── requirements.txt        # requirements-dev.txt adds pytest, pyflakes, PyInstaller
├── tests/                  # engine tests (pytest)
└── src/
    ├── app_paths.py        # app folders, version, tool lookup
    ├── config.py           # config.json
    ├── i18n.py             # ES / EN / PT texts
    ├── gif_utils.py        # GIF timing and reading Steam-patched files
    ├── video_utils.py      # video probing and thumbnails (OpenCV)
    ├── downloads.py        # download helper
    ├── models.py           # AI model registry and downloads
    ├── processing/         # engine: fragmentation, encoding, AI, colors, size optimizer
    ├── ui/                 # main window, the four steps, widgets, theme
    │   └── logic/          # actions behind the buttons, by domain
    ├── fragment_preview.py # preview of the cut
    ├── quality_report.py   # before/after report after AI processing
    └── steam_uploader.py   # automatic upload (Playwright)
```

---

## Tests and building the .exe

```bash
pip install -r requirements-dev.txt playwright browser_cookie3
pytest tests                      # engine tests (needs the FFmpeg the app downloads)
pyinstaller WorkshopArt.spec      # -> dist/WorkshopArt.exe
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Windows SmartScreen blocks the .exe | *More info → Run anyway*. The exe is not code-signed; the full source is here to verify it. |
| First launch takes a while | The tools and models are being downloaded; progress is shown on the startup screen. |
| GPU not detected | Update the graphics drivers (Vulkan support is required). |
| The AI fails on the GPU | Turn off *Use GPU* in step 2 and try again. |
| A preset does not fit in 5 MB | Trim the clip; long or very detailed animations cannot fit. |
| Steam rejects the upload | Paste the console snippet before saving and check the file is under 5 MB. |
| Anything else | Details in `SteamWorkshopAppData/logs/runtime.log`. |

---

## Credits

- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) by Xintao Wang et al.
- [Real-CUGAN](https://github.com/bilibili/ailab/tree/main/Real-CUGAN) by Bilibili, [ncnn port](https://github.com/nihui/realcugan-ncnn-vulkan) by nihui
- [RIFE ncnn Vulkan](https://github.com/nihui/rife-ncnn-vulkan) by nihui
- [gifski](https://github.com/ImageOptim/gifski) by Kornel Lesiński
- [gifsicle](https://github.com/kohler/gifsicle) by Eddie Kohler
- [FFmpeg](https://ffmpeg.org/), [OpenCV](https://opencv.org/), [Pillow](https://python-pillow.org/)
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) by Tom Schimansky

---

## License

Proprietary software, free for personal, non-commercial use. Redistribution, modification and commercial use are not permitted without written permission from the author. See [LICENSE](LICENSE).
