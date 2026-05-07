# WorkshopArt PRO v3.0

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![AI](https://img.shields.io/badge/AI-Real--ESRGAN%20%7C%20Real--CUGAN-orange)
![Version](https://img.shields.io/badge/Version-3.0-blue)

**Create stunning animated GIF artwork for every Steam profile showcase format.**

Transform videos and GIFs into upload-ready fragments for any Steam showcase — Artwork, Screenshot, Workshop, Panorama — using AI upscaling (Real-ESRGAN / Real-CUGAN).

[Download Release](../../releases) | [Quick Start](#installation) | [Steam Upload Guide](#uploading-to-steam) | [Report a Bug](../../issues/new)

</div>

---

---

## Features

- **9 Showcase Presets** — Covers every Steam profile showcase layout (see table below)
- **AI Upscaling (2x / 3x / 4x)** — Real-ESRGAN and Real-CUGAN via ncnn Vulkan
- **Smart Content Detection** — Automatically picks the best AI model for anime, gaming, or photo content
- **Color Enhancement** — Contrast and saturation sliders with real-time preview
- **MP4-to-GIF Conversion** — Convert any video to GIF with configurable FPS
- **Animation Enhancement** — Boost frame rate and fluidity of existing GIFs
- **GIF Preview with Drag & Drop** — Drop files directly onto the window for instant preview
- **GPU Acceleration** — Vulkan-based processing (~10x faster than CPU)
- **Dark Theme UI** — Modern GitHub-dark interface built with CustomTkinter
- **Zero-Config Setup** — FFmpeg and AI models download automatically on first launch
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

All presets apply cover+crop (no distortion), 2-pass GIF palette optimization, and enforce the 5 MB per-file Steam limit.

---

## Requirements

| Requirement | Details |
|---|---|
| **Python** | 3.10 or newer |
| **OS** | Windows 10 / 11 (64-bit) |
| **RAM** | 4 GB minimum, 8 GB recommended |
| **Disk** | ~2 GB free (models + temp files) |
| **GPU** | Any Vulkan-capable GPU recommended (AMD RX, NVIDIA GTX/RTX). CPU fallback available. |
| **Internet** | Required once for initial model download |

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/Mateo-Costas/Steam-Workshop-Art-Maker.git
cd Steam-Workshop-Art-Maker

# 2. (Optional) Create a virtual environment
python -m venv venv
venv\Scripts\activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Launch the application
python src/main.py
```

On first launch the app will automatically download:

- **FFmpeg** portable binary
- **Real-ESRGAN** ncnn Vulkan executable + model weights (~50 MB)
- **Real-CUGAN** ncnn Vulkan executable + model weights (optional, ~20 MB)

These are placed in the project root and the `models/` directory.

---

## Building a Standalone Executable

```bash
pip install pyinstaller
pyinstaller WorkshopArt_PRO_v3.0.spec
```

The output will be in `dist/WorkshopArtPRO/`. The folder is fully portable — copy it anywhere and run `WorkshopArtPRO.exe`.

---

## Usage

### Quick Workflow

1. **Open a file** — Drag and drop an MP4, AVI, MOV, MKV, WEBM, or GIF onto the window, or click *Abrir archivo*.
2. **Configure** — Pick an AI model, toggle GPU, and adjust contrast / saturation. Enable *Auto-detectar modelo* to let the analyzer choose for you.
3. **Process with AI** — Click *Procesar con IA* for full upscaling + color enhancement.
4. **Fragment for showcase** — Select a showcase preset and click *Fragmentar Showcase*. The app splits the result into upload-ready parts.
5. **Upload to Steam** — Follow the guide below for your showcase type.

### Button Reference

| Button | Description |
|---|---|
| **Abrir archivo** | Load a video or GIF |
| **Procesar con IA** | AI upscale + color enhancement |
| **Solo colores** | Apply contrast / saturation without AI |
| **MP4 a GIF** | Convert video to GIF |
| **Mejorar animacion** | Improve frame rate and fluidity |
| **Fragmentar Showcase** | Split GIF into parts using the selected preset |
| **Fragmentar Steam** | Legacy 5-part Workshop Showcase split |
| **Descargar modelos IA** | Manually trigger model download |

---

## Uploading to Steam

### Step 1 — Open the Upload Page

Go to: `https://steamcommunity.com/sharedfiles/edititem/767/3/`

Upload your GIF file. Open the browser developer console (**F12 → Console**) and run the appropriate commands for your showcase type **before clicking Save**.

---

### Workshop Showcase (5-slot)

```javascript
$J('[name=consumer_app_id]').val(480);
$J('[name=file_type]').val(0);
$J('[name=visibility]').val(0);
```

Repeat for each of the 5 parts. Then go to your Steam profile → **Workshop Showcase** → select the 5 uploaded items.

---

### Artwork Showcase (Featured / Single / 2-part / 4-grid)

```javascript
$J('[name=consumer_app_id]').val(767);
$J('[name=file_type]').val(3);
$J('[name=visibility]').val(0);
```

For the **2-part layout** (main + side): upload both files, then configure your Steam profile to show the **2-artwork layout** in the Artwork Showcase settings and assign each file to its slot.

---

### Screenshot Showcase

```javascript
$J('[name=consumer_app_id]').val(767);
$J('[name=file_type]').val(5);
$J('[name=visibility]').val(0);
```

---

### Panorama (full-width image)

Upload to the Artwork Showcase endpoint, then run:

```javascript
$J('#image_width').val(1000).attr('id', '');
$J('#image_height').val(1).attr('id', '');
$J('[name=consumer_app_id]').val(767);
$J('[name=file_type]').val(3);
$J('[name=visibility]').val(0);
```

The `1000×1` dimension spoof tells Steam to display the image at full showcase width.

---

### Step 2 — Check the agreement box and click Save

Repeat for each fragment. After all parts are uploaded, edit your Steam profile and configure the relevant showcase to display them.

---

## GIF Technical Requirements (Steam)

| Property | Requirement |
|---|---|
| Format | GIF89a |
| Max file size | **5 MB per file** (enforced since Dec 2022) |
| Last byte | Must be `0x21` (not `0x3B`) — the app applies this automatically |
| Loop | Netscape loop block present (infinite loop) |
| Color depth | Up to 256 colors per frame |

> The app automatically applies the `0x3B → 0x21` trailer byte patch to every exported fragment. Without this, Steam may reject uploads or display them incorrectly.

---

## Supported AI Models

### Real-ESRGAN

| Model | Scale | Best For | Speed |
|---|---|---|---|
| `realesr-animevideov3-x2` | 2x | Anime / Gaming (fast) | Very Fast |
| `realesr-animevideov3-x3` | 3x | Anime / Gaming (balanced) | Fast |
| `realesr-animevideov3-x4` | 4x | Anime / Gaming (high quality) | Medium |
| `realesrgan-x4plus-anime` | 4x | Anime illustrations (premium) | Slow |
| `realesrgan-x4plus` | 4x | General purpose / versatile | Medium |
| `realesrnet-x4plus` | 4x | Realistic photos | Fast |
| `realesr-general-x4v3` | 4x | Lightweight general | Very Fast |
| `realesr-general-wdn-x4v3` | 4x | General with denoising | Fast |
| `RealESRGAN_x2plus` | 2x | Quick 2x preview | Very Fast |

### Real-CUGAN (Bilibili)

| Model | Scale | Best For | Speed |
|---|---|---|---|
| `cugan-se-2x-no-denoise` | 2x | Clean anime sources | Fast |
| `cugan-se-2x-denoise3` | 2x | Noisy / old anime | Fast |
| `cugan-se-3x-no-denoise` | 3x | Anime (high quality) | Medium |
| `cugan-se-4x-no-denoise` | 4x | Anime (maximum quality) | Slow |
| `cugan-pro-2x-denoise3` | 2x | Premium anime + denoise | Medium |
| `cugan-pro-3x-no-denoise` | 3x | Premium anime | Medium |

---

## Project Structure

```
Steam-Workshop-Art-Maker/
├── src/
│   ├── main.py               # GUI entry point (run directly with Python)
│   ├── gui.py                # Main GUI layout (CustomTkinter)
│   ├── gui_methods.py        # GUI logic, processing callbacks
│   ├── processor.py          # Core processing engine + showcase presets
│   ├── fragment_preview.py   # Fragment preview dialog
│   ├── models.py             # AI model management and downloading
│   ├── analyzers.py          # Content analysis (anime / gaming / photo)
│   ├── config.py             # Configuration management
│   ├── theme_PRO.py          # Color palette and font constants
│   └── i18n.py               # Internationalization helpers
├── models/                   # AI model weights (.bin, .param) — auto-downloaded
├── temp/                     # Temporary processing files
├── logs/                     # Runtime logs
├── main.py                   # PyInstaller entry point (exe build)
├── WorkshopArt_PRO_v3.0.spec # PyInstaller build spec
├── requirements.txt          # Python dependencies
├── LICENSE                   # MIT License
└── README.md
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| GPU not detected | Update AMD / NVIDIA drivers; ensure Vulkan is supported |
| Processing is slow | Enable the GPU toggle in the right panel |
| Model download fails | Delete the `models/` folder and restart the app |
| Output file too large | Use a shorter source clip or lower FPS |
| Fragmentation fails | Make sure FFmpeg downloaded correctly; check `logs/` |
| Steam rejects upload | Check that the GIF is under 5 MB and run the console commands before clicking Save |
| Side image looks small | For 2-part artwork: configure the Artwork Showcase to the 2-column layout in Steam profile settings and assign both images to their slots |

---

## Known Limitations

- The panorama preset requires a `1000×1` dimension spoof when uploading manually — paste the panorama JS snippet in the browser console before clicking Save.
- The 2-part artwork showcase (main + side) requires manual slot assignment in Steam profile settings — Steam does not auto-layout them.
- Steam enforces a 5 MB limit per file (error messages may still say "8 MB" — they are outdated).

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Credits

- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) by Xintao Wang et al. — AI super-resolution engine
- [Real-CUGAN](https://github.com/bilibili/ailab/tree/main/Real-CUGAN) by Bilibili — Anime-specialized upscaling
- [ncnn](https://github.com/Tencent/ncnn) by Tencent — High-performance neural network inference
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) by Tom Schimansky — Modern Python GUI framework
- [FFmpeg](https://ffmpeg.org/) — Multimedia processing
- [MoviePy](https://zulko.github.io/moviepy/) — Video editing in Python
- [windnd](https://github.com/nicothin/windnd) — Windows drag-and-drop support
