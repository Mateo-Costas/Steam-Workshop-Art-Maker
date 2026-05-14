# WorkshopArt PRO

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![AI](https://img.shields.io/badge/AI-Real--ESRGAN%20%7C%20Real--CUGAN-orange)
![Version](https://img.shields.io/badge/Version-3.0-blue)
![Lang](https://img.shields.io/badge/Lang-ES%20%7C%20EN%20%7C%20PT--BR-green)

**Create stunning animated GIF artwork for every Steam profile showcase format.**

Transform videos and GIFs into upload-ready fragments for any Steam showcase — Artwork, Screenshot, Workshop, Panorama — using AI upscaling (Real-ESRGAN / Real-CUGAN).

[⬇ Download compiled .exe (Itch.io)](https://mxteoo7.itch.io/workshopart-pro) · [⭐ Support on Patreon](https://www.patreon.com/mxteoo7) · [Quick Start](#run-from-source) · [Report a Bug](../../issues/new)

</div>

---

## Free vs PRO

This repository contains the **free, open-source version** of WorkshopArt PRO.

| Feature | Free (this repo) | PRO (Itch.io / Patreon) |
|---|---|---|
| All 9 showcase presets | ✅ | ✅ |
| MP4-to-GIF conversion | ✅ | ✅ |
| gifski encoder | ✅ | ✅ |
| Color enhancement | ✅ | ✅ |
| **gifsicle post-optimization** (auto-download) | ✅ | ✅ |
| **3-language UI** (ES / EN / PT-BR) | ✅ | ✅ |
| **VRAM display** in GPU info | ✅ | ✅ |
| **SSIM quality metric** in quality report | ✅ | ✅ |
| Zero-config auto-download of tools | ✅ | ✅ |
| **AI upscaling (Real-ESRGAN / Real-CUGAN)** | ❌ | ✅ |
| **Animation enhancement (RIFE)** | ❌ | ✅ |
| **GIF fragment preview** | ❌ | ✅ |
| **Faster upscaling via Python bindings** | ❌ | ✅ |
| **Automatic Steam upload (Upload Tool)** | ❌ | ✅ |
| **Compiled .exe — no Python needed** | ❌ | ✅ |

The free version covers the full conversion and fragmentation pipeline including GIF post-optimization via gifsicle (10–25% smaller output), 3-language UI, and SSIM quality metrics. AI upscaling, RIFE animation enhancement, fragment preview, Python bindings for faster batch processing, and automated upload are PRO-only.

**Get the PRO .exe:**
- [mxteoo7.itch.io/workshopart-pro](https://mxteoo7.itch.io/workshopart-pro) — one-time purchase
- [patreon.com/mxteoo7](https://www.patreon.com/mxteoo7) — supporter tier

---

## Features

- **9 Showcase Presets** — Covers every Steam profile showcase layout (see table below)
- **AI Upscaling (2x / 3x / 4x)** — Real-ESRGAN and Real-CUGAN via ncnn Vulkan (PRO)
- **Smart Content Detection** — Automatically picks the best AI model for anime, gaming, or photo content
- **Color Enhancement** — Contrast and saturation sliders with real-time preview
- **MP4-to-GIF Conversion** — Convert any video to GIF with configurable FPS
- **gifsicle Post-Optimization** — Automatic LZW recompression after export; typically 10–25% smaller GIFs with zero quality loss. Binary is auto-downloaded on first use.
- **VRAM Display** — GPU detection shows exact VRAM (e.g. "NVIDIA RTX 3060 (12 GB VRAM)") via GPUtil (NVIDIA) or wmic (AMD)
- **SSIM Quality Metric** — Structural similarity score added to the quality report after processing
- **3-Language UI** — Switch between Español, English, and Português (BR) from the interface
- **Animation Enhancement (PRO)** — Boost frame rate and fluidity using RIFE interpolation
- **GIF Preview with Drag & Drop** — Drop files directly onto the window for instant preview
- **GPU Acceleration** — Vulkan-based processing (~10x faster than CPU)
- **Dark Theme UI** — Modern GitHub-dark interface built with CustomTkinter
- **Zero-Config Setup** — FFmpeg, gifski, gifsicle, RIFE, and AI models download automatically on first launch
- **GIF Trailer Patch** — Applies the required `0x3B → 0x21` byte fix to all output fragments

---

## Showcase Presets

| Preset | Dimensions | Parts | Showcase Type |
|--------|-----------|-------|---------------|
| Featured Artwork 630×H | 630 px wide, free height | 1 | Artwork Showcase (featured) |
| Artwork single 630×354 | 630 × 354 px | 1 | Artwork Showcase (1-slot 16:9) |
| Artwork 506+100 (main+side) | 506 px + 100 px, free height | 2 | Artwork Showcase (2-slot) |
| Artwork 4-grid 4×245 | 245 × 245 px each | 4 | Artwork Showcase (4-grid) |
| Panorama 5×630×360 | 630 × 360 px each | 5 | Artwork Showcase (wide/panorama) |
| Screenshot 638×354 | 638 × 354 px | 1 | Screenshot Showcase (1-slot) |
| Screenshot 4-grid | 638 × 354 px each | 4 | Screenshot Showcase (4-grid) |
| Workshop 5×150×150 | 150 × 150 px each | 5 | Workshop Showcase (5-slot) |
| Workshop 5×119×119 | 119 × 119 px each | 5 | Workshop Showcase (native size) |

All presets apply cover+crop (no distortion), 2-pass GIF palette optimization, gifsicle post-optimization, and enforce the 5 MB per-file Steam limit.

---

## Requirements

| Requirement | Details |
|---|---|
| **Python** | 3.10 or newer |
| **OS** | Windows 10 / 11 (64-bit) |
| **RAM** | 4 GB minimum, 8 GB recommended |
| **Disk** | ~2 GB free (models + temp files) |
| **GPU** | Any Vulkan-capable GPU recommended (AMD RX, NVIDIA GTX/RTX). CPU fallback available. |
| **Internet** | Required once for initial tool and model download |

### Python dependencies

```bash
pip install -r requirements.txt
```

Key packages: `pillow`, `moviepy`, `opencv-python`, `numpy`, `customtkinter`, `gputil`, `pygifsicle`, `tqdm`.

> **PRO only:** `pip install -r requirements.txt -r requirements-pro.txt` adds `realesrgan-ncnn-py`, `rife-ncnn-py`, and `playwright`.

---

## Run from Source

```bash
# 1. Clone the repository
git clone https://github.com/Mateo-Costas/Steam-Workshop-Art-Maker.git
cd Steam-Workshop-Art-Maker

# 2. (Optional) Create a virtual environment
python -m venv venv
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch
python src/main.py
```

On first launch the app downloads automatically:

- **FFmpeg** portable binary (~120 MB)
- **gifski** encoder
- **gifsicle** LZW optimizer (~1 MB)

All tools are placed inside a `SteamWorkshopAppData/` folder next to the script.

> **Real-ESRGAN / Real-CUGAN / RIFE** models and binaries are PRO-only and are not downloaded by the free version.

---

## Usage

### Quick Workflow

1. **Open a file** — Drag and drop an MP4, AVI, MOV, MKV, WEBM, or GIF onto the window, or click *Abrir archivo*.
2. **Configure** — Adjust contrast / saturation. Enable *Auto-detectar modelo* to let the analyzer choose the best AI model for you (PRO).
3. **Process** — Click *Solo colores* for contrast/saturation enhancement (free), or use *Procesar con IA* for AI upscaling (PRO).
4. **Fragment for showcase** — Select a showcase preset and click *Fragmentar Showcase*. The app splits the result into upload-ready parts and applies gifsicle optimization automatically.
5. **Upload to Steam** — Follow the guide below for your showcase type (manual), or use the PRO Upload Tool.

### Button Reference

| Button | Description |
|---|---|
| **Abrir archivo** | Load a video or GIF |
| **Procesar con IA** | AI upscale + color enhancement (PRO) |
| **Solo colores** | Apply contrast / saturation without AI |
| **MP4 a GIF** | Convert video to GIF |
| **Mejorar animacion** | Improve frame rate and fluidity with RIFE AI (PRO) |
| **Fragmentar Showcase** | Split GIF into parts using the selected preset |
| **Descargar modelos IA** | Manually trigger model download (PRO) |

---

## Uploading to Steam (Manual)

### Step 1 — Open the Upload Page

Go to: `https://steamcommunity.com/sharedfiles/edititem/767/3/`

Upload your GIF file, then open the browser developer console (**F12 → Console**) and run the appropriate snippet for your showcase type **before clicking Save**.

---

### Workshop Showcase (5-slot)

```javascript
$J('[name=consumer_app_id]').val(480);
$J('[name=file_type]').val(0);
$J('[name=visibility]').val(0);
```

Repeat for each of the 5 parts.

---

### Artwork Showcase (Featured / Single / 2-part / 4-grid)

```javascript
$J('[name=consumer_app_id]').val(767);
$J('[name=file_type]').val(3);
$J('[name=visibility]').val(0);
```

---

### Screenshot Showcase

```javascript
$J('[name=consumer_app_id]').val(767);
$J('[name=file_type]').val(5);
$J('[name=visibility]').val(0);
```

---

### Panorama (full-width image)

```javascript
$J('#image_width').val(1000).attr('id', '');
$J('#image_height').val(1).attr('id', '');
$J('[name=consumer_app_id]').val(767);
$J('[name=file_type]').val(3);
$J('[name=visibility]').val(0);
```

---

### Step 2 — Check the agreement box and click Save

Repeat for each fragment. After all parts are uploaded, edit your Steam profile and configure the relevant showcase to display them.

> **Want one-click upload?** The PRO version handles authentication and submission automatically. [Get it on Itch.io](https://mxteoo7.itch.io/workshopart-pro) or [Patreon](https://www.patreon.com/mxteoo7).

---

## GIF Technical Requirements (Steam)

| Property | Requirement |
|---|---|
| Format | GIF89a |
| Max file size | **5 MB per file** |
| Last byte | Must be `0x21` — the app applies this automatically |
| Loop | Netscape loop block present (infinite loop) |

---

## Supported AI Models (PRO)

### Real-ESRGAN

| Model | Scale | Best For |
|---|---|---|
| `realesr-animevideov3-x2` | 2x | Anime / Gaming (fast) |
| `realesr-animevideov3-x3` | 3x | Anime / Gaming (balanced) |
| `realesr-animevideov3-x4` | 4x | Anime / Gaming (high quality) |
| `realesrgan-x4plus-anime` | 4x | Anime illustrations |
| `realesrgan-x4plus` | 4x | General purpose |
| `realesrnet-x4plus` | 4x | Realistic photos |

### Real-CUGAN

| Model | Scale | Best For |
|---|---|---|
| `cugan-se-2x-no-denoise` | 2x | Clean anime sources |
| `cugan-se-2x-denoise3` | 2x | Noisy / old anime |
| `cugan-se-3x-no-denoise` | 3x | Anime (high quality) |
| `cugan-pro-2x-denoise3` | 2x | Premium anime + denoise |

---

## Project Structure

```
Steam-Workshop-Art-Maker/
├── src/
│   ├── main.py               # Entry point (run with: python src/main.py)
│   ├── gui.py                # Main GUI layout (CustomTkinter)
│   ├── gui_methods.py        # GUI logic and processing callbacks
│   ├── processor.py          # Core processing engine + showcase presets
│   ├── quality_report.py     # Quality analysis, SSIM metrics, improvement report
│   ├── models.py             # AI model management and auto-download
│   ├── analyzers.py          # Content analysis (anime / gaming / photo)
│   ├── config.py             # Configuration management
│   ├── theme_PRO.py          # Color palette and font constants
│   └── i18n.py               # Internationalization (ES / EN / PT-BR)
├── main.py                   # PyInstaller entry point (PRO exe build)
├── WorkshopArt_PRO_v1.0.spec # PyInstaller build spec
├── requirements.txt          # Free version dependencies
├── requirements-pro.txt      # Extra dependencies for PRO build
└── README.md
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| **Windows SmartScreen blocks the .exe** | Click **"More info" → "Run anyway"**. The warning appears because the exe has no code-signing certificate. The app is open-source; you can verify the source code in this repo. |
| GPU not detected | Update AMD / NVIDIA drivers; ensure Vulkan is supported |
| VRAM shows 0 or wrong value | On AMD, Windows wmic has a 4 GB overflow bug for GPUs >4 GB. Processing still works correctly; only the display is affected. |
| Processing is slow | Enable the GPU toggle in the right panel |
| Model download fails | Delete the `SteamWorkshopAppData/models/` folder and restart |
| Output file too large | Use a shorter clip or lower FPS; gifsicle optimization is applied automatically |
| gifsicle download fails | Delete `SteamWorkshopAppData/gifsicle.exe` and restart; the app will retry the download |
| Fragmentation fails | Check that FFmpeg downloaded correctly; check `SteamWorkshopAppData/logs/` |
| Steam rejects upload | Ensure the GIF is under 5 MB and run the console snippet before clicking Save |
| **First launch hangs / does nothing** | The app is downloading tools (FFmpeg, gifski, gifsicle) in the background. Check the log panel — progress is shown there. Do not close the app. |

---

## Credits

- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) by Xintao Wang et al.
- [Real-CUGAN](https://github.com/bilibili/ailab/tree/main/Real-CUGAN) by Bilibili
- [RIFE](https://github.com/nihui/rife-ncnn-vulkan) by nihui
- [gifski](https://github.com/ImageOptim/gifski) by Kornel Lesiński
- [gifsicle](https://github.com/kohler/gifsicle) by Eddie Kohler
- [ncnn](https://github.com/Tencent/ncnn) by Tencent
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) by Tom Schimansky
- [GPUtil](https://github.com/anderskm/gputil) by Anders Krogh Mortensen
- [FFmpeg](https://ffmpeg.org/)
- [MoviePy](https://zulko.github.io/moviepy/)

---

## License

This project is proprietary software. Personal, non-commercial use only. Redistribution, modification, and commercial use are not permitted without explicit written permission from the author.
