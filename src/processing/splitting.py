"""processing.splitting - Steam showcase fragmentation (5-part, artwork, presets)."""
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from PIL import Image, ImageSequence

from processing.common import _NO_WINDOW_FLAGS, logger


class SplitMixin:
    def split_gif_for_steam(self, gif_path: Path) -> bool:
        """Split a GIF into 5 equal-width parts for Steam Workshop profile uploads.
        Uses gifski binary-search quality as primary encoder, FFmpeg as fallback.
        Each part must be ≤ 5 MiB to comply with Steam's per-file size limit."""
        if not self.check_ffmpeg():
            logger.error("❌ FFmpeg no disponible - necesario para fragmentación")
            return False
        output_dir = self._workspace_dir(gif_path, "fragmentos")
        self._archive_before_overwrite(output_dir)
        output_prefix = output_dir / gif_path.stem
        _source_for_manifest = gif_path
        logger.info(f"✂️ Fragmentando: {gif_path}")
        logger.info(f"📁 Salida en: {output_dir}")

        original_gif_path = gif_path
        try:
            logger.info(f"✂️ Fragmentando GIF: {gif_path}")

            # Verificar y ajustar dimensiones primero
            with Image.open(gif_path) as img:
                expected_width = self.config.get('steam_profile.width')
                expected_height = self.config.get('steam_profile.height')
                
                logger.info(f"📐 Dimensiones actuales: {img.size}, esperadas: {expected_width}x{expected_height}")
                
                if img.size != (expected_width, expected_height):
                    logger.info(f"🔧 Redimensionando de {img.size} a {expected_width}x{expected_height}")
                    
                    # Crear GIF redimensionado
                    frames = []
                    durations = []
                    
                    for frame in ImageSequence.Iterator(img):
                        # Convert P-mode frames before resizing: LANCZOS over raw
                        # palette indices corrupts colors.
                        rgb = frame.convert('RGB') if frame.mode != 'RGB' else frame
                        resized = rgb.resize((expected_width, expected_height), Image.Resampling.LANCZOS)
                        frames.append(resized)
                        durations.append(img.info.get('duration', 100))
                    
                    # Guardar GIF temporal redimensionado
                    temp_resized = gif_path.with_stem(f"{gif_path.stem}_resized_temp")
                    frames[0].save(
                        temp_resized,
                        save_all=True,
                        append_images=frames[1:],
                        duration=durations[0] if durations else 100,
                        loop=0,
                        optimize=False
                    )
                    gif_path = temp_resized
                    logger.info(f"✅ GIF redimensionado guardado: {gif_path}")
            
            output_prefix = gif_path.with_suffix('')
            section_width = expected_width // 5
            height = expected_height
            
            logger.info(f"📊 Fragmentando en secciones de {section_width}x{height} px")
            
            # Fragmentar: gifski primary (binary-search quality), ffmpeg fallback
            success = True
            created_parts = []
            MAX_BYTES = 5 * 1024 * 1024 - 16 * 1024  # 16 KiB headroom below Steam's hard 5 MiB limit
            _use_gifski = self.check_gifski()

            _orig_fps = 25
            try:
                with Image.open(gif_path) as _fps_img:
                    _dur = _fps_img.info.get('duration', 40) or 40
                    _orig_fps = max(1, int(round(1000.0 / _dur)))
            except Exception:
                pass

            import tempfile
            _tmp = Path(tempfile.mkdtemp(prefix="wkart_steam_"))
            _gifski_done = False
            try:
                # ── gifski: shared fps+quality for ALL 5 parts ───────────────
                if _use_gifski:
                    # Outer loop: descend fps tiers until ALL 5 parts fit under MAX_BYTES
                    for fps_cap in [None, 24, 20, 15, 12, 10, 8, 6, 4, 3]:
                        _fps_a = str(fps_cap) if fps_cap else str(_orig_fps)

                        # Extract PNG frames for all 5 parts at this fps tier
                        _fds: dict = {}
                        _ex_ok = True
                        for i in range(5):
                            left = i * section_width
                            _vf = f"crop={section_width}:{height}:{left}:0"
                            if fps_cap:
                                _vf = f"fps={fps_cap}," + _vf
                            fd = _tmp / f"fd_{fps_cap or 0}_p{i+1}"
                            shutil.rmtree(fd, ignore_errors=True)
                            fd.mkdir()
                            r_ex = subprocess.run(
                                [str(self.ffmpeg_path), "-y", "-i", str(gif_path),
                                 "-vf", _vf, str(fd / "frame%06d.png")],
                                capture_output=True, encoding='utf-8',
                                errors='replace', timeout=120, **_NO_WINDOW_FLAGS)
                            if r_ex.returncode != 0 or not any(fd.glob("frame*.png")):
                                logger.warning(f"   gifski/extract parte {i+1} fps={_fps_a}: rc={r_ex.returncode}")
                                _ex_ok = False
                                break
                            _fds[i] = fd

                        if not _ex_ok:
                            for fd in _fds.values():
                                shutil.rmtree(fd, ignore_errors=True)
                            continue

                        # Binary-search highest gifski quality where ALL 5 parts fit ≤ MAX_BYTES.
                        # Converges in ≤ ceil(log2(85)) ≈ 7 iterations.
                        q_lo, q_hi = 10, 95
                        _best_q = None
                        _best_baks: dict = {}
                        _best_sizes: dict = {}

                        while q_lo <= q_hi:
                            q = (q_lo + q_hi) // 2
                            _res: dict = {}
                            _all_fit = True
                            for i in range(5):
                                out_path = output_dir / f"{gif_path.stem}_part_{i+1}.gif"
                                fd = _fds[i]
                                r = subprocess.run(
                                    [str(self.gifski_path), "--fps", _fps_a,
                                     "--quality", str(q),  # 1-100; higher = better visual quality but larger file
                                     "--repeat", "0",       # 0 = loop forever
                                     "-o", str(out_path), str(fd / "frame*.png")],
                                    capture_output=True, encoding='utf-8',
                                    errors='replace', timeout=180, **_NO_WINDOW_FLAGS)
                                if r.returncode != 0 or not out_path.exists():
                                    logger.warning(f"   gifski parte {i+1} q={q} rc={r.returncode}")
                                    _all_fit = False
                                    break
                                sz = out_path.stat().st_size
                                logger.info(f"   gifski parte {i+1} q={q} fps={_fps_a} → {sz/1024/1024:.2f} MB")
                                _res[i] = (out_path, sz)
                                if sz > MAX_BYTES:
                                    _all_fit = False
                                    break

                            if _all_fit and len(_res) == 5:
                                _best_q = q
                                for i, (path, sz) in _res.items():
                                    bak = path.with_suffix("._gbest")
                                    shutil.copy(path, bak)
                                    _best_baks[i] = bak
                                    _best_sizes[i] = sz
                                q_lo = q + 1
                            else:
                                q_hi = q - 1

                        for fd in _fds.values():
                            shutil.rmtree(fd, ignore_errors=True)

                        if _best_q is not None:
                            for i in range(5):
                                out_path = output_dir / f"{gif_path.stem}_part_{i+1}.gif"
                                bak = _best_baks.get(i)
                                if bak and bak.exists():
                                    shutil.copy(bak, out_path)
                                    try: bak.unlink()
                                    except OSError: pass
                                self._patch_gif_trailer(out_path)
                                size_mb = _best_sizes[i] / (1024 * 1024)
                                created_parts.append({"part": i+1, "path": out_path, "size": size_mb})
                                logger.info(f"✅ Parte {i+1}: {size_mb:.2f} MB [gifski fps={_fps_a} q={_best_q}]")
                            _gifski_done = True
                            break

                        for bak in _best_baks.values():
                            try: bak.unlink()
                            except OSError: pass

                # ── ffmpeg fallback ───────────────────────────────────────────
                if not _gifski_done:
                    for i in range(5):
                        left = i * section_width
                        output_path = output_dir / f"{gif_path.stem}_part_{i+1}.gif"
                        logger.info(f"✂️ Creando parte {i+1}/5: {output_path.name}")
                        cmd = [
                            str(self.ffmpeg_path), "-i", str(gif_path),
                            "-vf", (
                                f"crop={section_width}:{height}:{left}:0,"   # crop to this panel's column
                                f"split[s0][s1];"                              # fork stream for 2-pass palette
                                f"[s0]palettegen=max_colors=256"
                                f":reserve_transparent=1"                      # keep 1 palette slot for transparency
                                f":stats_mode=full[p];"                        # analyse all frames for optimal palette
                                f"[s1][p]paletteuse=dither=sierra2_4a"        # sierra2_4a: best dither for animation
                                f":diff_mode=rectangle"                        # only dither changed rectangular regions
                            ),
                            "-y", str(output_path)
                        ]
                        try:
                            result = subprocess.run(
                                cmd, capture_output=True, encoding='utf-8',
                                errors='replace', timeout=60, **_NO_WINDOW_FLAGS)
                            if result.returncode != 0:
                                logger.error(f"❌ Error en parte {i+1}: {result.stderr[-200:]}")
                                success = False
                                break
                        except Exception as e:
                            logger.error(f"❌ Excepción en parte {i+1}: {e}")
                            success = False
                            break

                        if not output_path.exists():
                            logger.error(f"❌ Parte {i+1}: no se creó el archivo")
                            success = False
                            break
                        self._patch_gif_trailer(output_path)
                        size_mb = output_path.stat().st_size / (1024 * 1024)
                        created_parts.append({"part": i+1, "path": output_path, "size": size_mb})
                        logger.info(f"✅ Parte {i+1}: {size_mb:.2f} MB [ffmpeg]")
            finally:
                shutil.rmtree(_tmp, ignore_errors=True)
            
            # Limpiar archivo temporal si se creó
            if gif_path != original_gif_path and gif_path.exists():
                gif_path.unlink()
                logger.info("🧹 Archivo temporal eliminado")
            
            if success and len(created_parts) == 5:
                self._write_manifest(output_dir, "fragmentar_steam",
                    {"partes": 5, "section_width": section_width, "height": height},
                    archivos=[p['path'] for p in created_parts],
                    fuente=_source_for_manifest)
                logger.info(f"\n✅ Fragmentación completada exitosamente!")
                logger.info("📊 Resumen de partes creadas:")
                
                total_size = 0
                min_size = self.config.get('steam_profile.min_size_mb', 4.4)
                max_size = self.config.get('steam_profile.max_size_mb', 4.8)
                
                for part in created_parts:
                    size = part['size']
                    total_size += size
                    status = "✅" if min_size <= size <= max_size else "⚠️"
                    logger.info(f"  {status} {part['path'].name}: {size:.2f} MB")
                
                logger.info(f"📊 Tamaño total: {total_size:.2f} MB")
                
                # Verificar advertencias
                warnings = []
                for part in created_parts:
                    if part['size'] < min_size:
                        warnings.append(f"Parte {part['part']} muy pequeña ({part['size']:.2f} MB)")
                    elif part['size'] > max_size:
                        warnings.append(f"Parte {part['part']} muy grande ({part['size']:.2f} MB)")
                
                if warnings:
                    logger.warning("\n⚠️ Advertencias:")
                    for warning in warnings:
                        logger.warning(f"  • {warning}")
                    logger.info("Steam Workshop puede tener problemas con estos archivos.")
                
                return True
            else:
                logger.error(f"❌ Fragmentación falló: solo {len(created_parts)}/5 partes creadas")
                return False
            
        except Exception as e:
            logger.error(f"❌ Error en fragmentación: {e}")
            return False

    def _gifski_optimal(self, frame_glob: str, out_path: Path,
                        fps_arg: str, max_bytes: int,
                        q_lo: int = 10, q_hi: int = 95) -> Optional[tuple]:
        """Binary-search the highest gifski quality that produces a file ≤ max_bytes.

        Returns (quality, file_size_bytes) or None if even q_lo is too large.
        Converges in ≤ ceil(log2(q_hi - q_lo + 1)) ≈ 7 iterations.
        """
        # The binary search may overwrite out_path with a "too large" result after
        # finding a good one.  Save a copy each time we beat the budget so we can
        # restore the real best file at the end.
        best = None
        _bak = out_path.with_suffix("._gbest")
        try:
            while q_lo <= q_hi:
                q = (q_lo + q_hi) // 2
                r = subprocess.run(
                    [str(self.gifski_path),
                     "--fps", fps_arg,
                     "--quality", str(q),
                     "--repeat", "0",
                     "-o", str(out_path),
                     frame_glob],
                    capture_output=True, encoding='utf-8', errors='replace',
                    timeout=180, **_NO_WINDOW_FLAGS,
                )
                if r.returncode != 0 or not out_path.exists():
                    logger.warning(f"   gifski q={q} rc={r.returncode}")
                    q_hi = q - 1
                    continue
                size = out_path.stat().st_size
                logger.info(f"   gifski q={q} fps={fps_arg} → {size / 1024 / 1024:.2f} MiB")
                if size <= max_bytes:
                    best = (q, size)
                    shutil.copy(out_path, _bak)  # preserve this good result
                    q_lo = q + 1
                else:
                    q_hi = q - 1
        finally:
            if best is not None and _bak.exists():
                shutil.copy(_bak, out_path)  # restore actual best file
            try:
                _bak.unlink()
            except OSError:
                pass
        return best

    def split_gif_for_artwork_showcase(self, gif_path: Path, output_dir=None) -> bool:
        """Fragmentar GIF en 2 partes (main 506 + side 100) para Steam Artwork Showcase.

        Specs (Steam 2026): formatos aceptados jpg/gif/png, max 5 MiB por pieza.
        Regular showcase = main 506px ancho + side 100px ancho (alto LIBRE, cualquier valor).
        Featured showcase = 630px ancho único.

        Calidad — pipeline optimizado:
          - Sin pre-resize con PIL (evita doble cuantización).
          - Un solo ffmpeg por parte con scale lanczos + 2-pass palette en filter_complex.
          - palettegen stats_mode=full (palette óptima sobre TODO el clip).
          - paletteuse dither=sierra2_4a (mejor dither para gradientes/animación).
          - Reintento adaptativo: si > 4.9 MiB, baja max_colors (256→192→128→96) y
            luego fps si hace falta. Mantiene calidad máxima dentro del límite.
          - Altura preservada: si el fuente no es 606 ancho, reescala por lanczos
            manteniendo aspecto (no fuerza 506 alto — showcase acepta cualquier alto).
        """
        if not self.check_ffmpeg():
            logger.error("❌ FFmpeg no disponible - necesario para fragmentación")
            return False

        if output_dir is None:
            output_dir = self._workspace_dir(gif_path, "fragmentos")
        output_dir = Path(output_dir)
        self._archive_before_overwrite(output_dir)
        _artwork_src = gif_path

        main_width = self.config.get('artwork_showcase.main_width', 506)
        side_width = self.config.get('artwork_showcase.side_width', 100)
        total_width = main_width + side_width  # 606
        forced_height = self.config.get('artwork_showcase.height', 0)
        MAX_BYTES = 5 * 1024 * 1024 - 16 * 1024  # 16 KiB safety margin below Steam's 5 MiB limit
        STEAM_HARD_MAX = 5 * 1024 * 1024

        logger.info(f"🎨 Fragmentando para Artwork Showcase: {gif_path}")

        try:
            with Image.open(gif_path) as img:
                orig_w, orig_h = img.size
                orig_duration = img.info.get('duration', 100) or 100
            orig_fps = 1000.0 / max(1, orig_duration)
            logger.info(f"📐 Origen: {orig_w}x{orig_h} @ ~{orig_fps:.2f}fps")

            if forced_height and forced_height > 0:
                target_height = int(forced_height)
            else:
                # Preserve aspect ratio, scaling to the combined target width
                target_height = max(1, round(orig_h * total_width / max(1, orig_w)))
            if target_height % 2 == 1:
                target_height += 1  # keep even height; some codecs require it
            logger.info(f"📐 Target: {main_width}+{side_width}={total_width} × {target_height}")

            parts_config = [
                {"name": "artwork_main", "width": main_width, "left": 0},
                {"name": "artwork_side", "width": side_width, "left": main_width},
            ]

            _use_gifski = self.check_gifski()
            logger.info(f"🎞️  Encoder: {'gifski + binary-search quality' if _use_gifski else 'ffmpeg'}")

            # gifski: iterate fps tiers, binary-search quality at each tier to
            # find the HIGHEST quality that still fits under MAX_BYTES.
            # This maximises visual quality instead of the linear ladder which
            # often overshoots and wastes available budget.
            gifski_fps_tiers = [None, 24, 20, 15, 12, 10, 8, 6, 4, 3] if _use_gifski else []

            # FFmpeg fallback: try (colors, fps_cap) pairs from highest to lowest quality
            # until both parts fit under MAX_BYTES.
            ffmpeg_ladder = [
                (256, None),
                (256, 24),
                (192, 24),
                (160, 20),
                (128, 20),
                ( 96, 15),
                ( 64, 12),
                ( 64,  8),
                ( 48,  8),
                ( 32,  6),
                ( 24,  5),
                ( 16,  4),
                ( 16,  3),
            ]

            created_parts = []
            success = True
            self._last_split_error = ""

            # ── gifski: shared fps+quality for ALL parts ─────────────────────
            # Both parts are tested at each candidate fps+quality so they always
            # share the same fps — otherwise the two panels desync during playback.
            _gifski_done = False
            if _use_gifski:
                for fps_cap in gifski_fps_tiers:
                    _fps_arg = str(int(fps_cap)) if fps_cap else str(max(1, int(orig_fps)))
                    fps_filter = f"fps={fps_cap}," if fps_cap else ""

                    # Extract frames for every part at this fps tier
                    _fds = {}
                    _ex_ok = True
                    for part in parts_config:
                        _tmp = "_ga" if part["left"] == 0 else "_gb"
                        fd = output_dir / _tmp
                        shutil.rmtree(fd, ignore_errors=True)
                        fd.mkdir(parents=True, exist_ok=True)
                        vf = (f"{fps_filter}"
                              f"scale={total_width}:{target_height}:flags=lanczos,"
                              f"crop={part['width']}:{target_height}:{part['left']}:0")
                        r = subprocess.run(
                            [str(self.ffmpeg_path), "-i", str(gif_path),
                             "-vf", vf, "-y", str(fd / "frame%06d.png")],
                            capture_output=True, encoding='utf-8', errors='replace',
                            timeout=120, **_NO_WINDOW_FLAGS)
                        if r.returncode != 0 or not any(fd.glob("frame*.png")):
                            logger.warning(f"   gifski/extract {part['name']} fps={_fps_arg}: rc={r.returncode}")
                            _ex_ok = False
                            break
                        _fds[part["name"]] = fd

                    if not _ex_ok:
                        for fd in _fds.values():
                            shutil.rmtree(fd, ignore_errors=True)
                        continue

                    # Binary-search shared quality where ALL parts fit under MAX_BYTES
                    q_lo, q_hi = 10, 95
                    _best_q = None
                    _best_baks: dict = {}
                    _best_sizes: dict = {}

                    while q_lo <= q_hi:
                        q = (q_lo + q_hi) // 2
                        _res = {}
                        _all_fit = True
                        for part in parts_config:
                            out_path = output_dir / f"{gif_path.stem}_{part['name']}.gif"
                            fd = _fds[part["name"]]
                            r = subprocess.run(
                                [str(self.gifski_path), "--fps", _fps_arg,
                                 "--quality", str(q), "--repeat", "0",
                                 "-o", str(out_path), str(fd / "frame*.png")],
                                capture_output=True, encoding='utf-8', errors='replace',
                                timeout=180, **_NO_WINDOW_FLAGS)
                            if r.returncode != 0 or not out_path.exists():
                                logger.warning(f"   gifski {part['name']} q={q} rc={r.returncode}")
                                _all_fit = False
                                break
                            sz = out_path.stat().st_size
                            logger.info(f"   gifski {part['name']} q={q} fps={_fps_arg} → {sz/1024/1024:.2f} MiB")
                            _res[part["name"]] = (out_path, sz)
                            if sz > MAX_BYTES:
                                _all_fit = False
                                break

                        if _all_fit and len(_res) == len(parts_config):
                            _best_q = q
                            for name, (path, sz) in _res.items():
                                bak = path.with_suffix("._gbest")
                                shutil.copy(path, bak)
                                _best_baks[name] = bak
                                _best_sizes[name] = sz
                            q_lo = q + 1
                        else:
                            q_hi = q - 1

                    # Cleanup frame dirs
                    for fd in _fds.values():
                        shutil.rmtree(fd, ignore_errors=True)

                    if _best_q is not None:
                        for part in parts_config:
                            name = part["name"]
                            out_path = output_dir / f"{gif_path.stem}_{name}.gif"
                            bak = _best_baks.get(name)
                            if bak and bak.exists():
                                shutil.copy(bak, out_path)
                                try: bak.unlink()
                                except OSError: pass
                            self._patch_gif_trailer(out_path)
                            size_mb = _best_sizes[name] / (1024 * 1024)
                            created_parts.append({"name": name, "path": out_path,
                                                  "size": size_mb, "engine": "gifski"})
                            logger.info(f"✅ {name}: {size_mb:.2f} MiB [gifski fps={_fps_arg} q={_best_q}]")
                        _gifski_done = True
                        break

                    for bak in _best_baks.values():
                        try: bak.unlink()
                        except OSError: pass

            # ── ffmpeg fallback: per-part (only if gifski didn't cover all) ──
            if not _gifski_done:
                for part in parts_config:
                    out_path = output_dir / f"{gif_path.stem}_{part['name']}.gif"
                    chosen = None
                    last_err = ""
                    for colors, fps_cap in ffmpeg_ladder:
                        fps_part = f"fps={fps_cap}," if fps_cap else ""
                        vf = (
                            f"{fps_part}"
                            f"scale={total_width}:{target_height}:flags=lanczos,"  # resize full canvas before crop
                            f"crop={part['width']}:{target_height}:{part['left']}:0,"  # extract this panel
                            f"split[s0][s1];"                                           # 2-pass palette
                            f"[s0]palettegen=max_colors={colors}:stats_mode=full:reserve_transparent=1[p];"
                            f"[s1][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle"
                        )
                        cmd = [str(self.ffmpeg_path), "-i", str(gif_path),
                               "-vf", vf, "-loop", "0", "-y", str(out_path)]
                        logger.info(f"✂️ {part['name']}: colors={colors} fps={fps_cap or 'orig'}")
                        try:
                            result = subprocess.run(cmd, capture_output=True,
                                                    encoding='utf-8', errors='replace',
                                                    timeout=180, **_NO_WINDOW_FLAGS)
                            if result.returncode != 0:
                                last_err = (result.stderr or "")[-400:]
                                logger.warning(f"   ffmpeg rc={result.returncode}: {last_err[-150:]}")
                                continue
                            if not out_path.exists():
                                last_err = "ffmpeg no creó el archivo"
                                continue
                            size = out_path.stat().st_size
                            logger.info(f"   → {size/1024/1024:.2f} MiB")
                            if size <= MAX_BYTES:
                                chosen = {"engine": "ffmpeg", "colors": colors,
                                          "fps": fps_cap, "size": size}
                                break
                        except subprocess.TimeoutExpired:
                            last_err = "timeout"
                            continue
                        except Exception as e:
                            last_err = str(e)
                            continue

                    if chosen is None:
                        logger.error(f"❌ {part['name']}: no se pudo generar. último error: {last_err}")
                        self._last_split_error = f"{part['name']}: {last_err}"
                        success = False
                        break

                    self._patch_gif_trailer(out_path)
                    size_mb = chosen["size"] / (1024 * 1024)
                    created_parts.append({"name": part['name'], "path": out_path,
                                          "size": size_mb, "engine": chosen["engine"]})
                    logger.info(f"✅ {part['name']}: {size_mb:.2f} MiB [ffmpeg]")

            if success and len(created_parts) == 2:
                self._write_manifest(output_dir, "fragmentar_artwork_showcase",
                    {"main_width": main_width, "side_width": side_width, "height": target_height,
                     "partes": [{"name": p['name'], "engine": p['engine']} for p in created_parts]},
                    archivos=[p['path'] for p in created_parts],
                    fuente=_artwork_src)
                total_size = sum(p['size'] for p in created_parts)
                logger.info(f"✅ Fragmentación Artwork Showcase completada! Total: {total_size:.2f} MiB")
                return True
            else:
                logger.error(f"❌ Fragmentación falló: {len(created_parts)}/2 partes creadas")
                return False

        except Exception as e:
            logger.error(f"❌ Error en fragmentación Artwork Showcase: {e}")
            return False

    def _split_image_into_jpeg_parts(self, image_path: Path,
                                      parts: list, total_w: int, fixed_h,
                                      output_dir: Path,
                                      manifest_op: str, manifest_params: dict) -> bool:
        """Crop a static image into JPEG panels using ffmpeg. Internal helper."""
        try:
            created = []
            for (name, w, left) in parts:
                out_path = output_dir / f"{image_path.stem}_{name}.jpg"
                if fixed_h:
                    vf = (
                        f"scale={total_w}:{fixed_h}"
                        f":force_original_aspect_ratio=increase"   # scale up so neither dimension is smaller than target
                        f":flags=lanczos+accurate_rnd+full_chroma_int,"  # high-quality resize flags
                        f"crop={total_w}:{fixed_h},"               # trim overflow from force_original_aspect_ratio
                        f"crop={w}:{fixed_h}:{left}:0"             # extract this panel
                    )
                else:
                    vf = (
                        f"scale={total_w}:-2"                       # -2 = preserve aspect ratio, even height
                        f":flags=lanczos+accurate_rnd+full_chroma_int,"
                        f"crop={w}:ih:{left}:0"                     # ih = input height (unchanged)
                    )
                cmd = [str(self.ffmpeg_path), "-i", str(image_path),
                       "-vf", vf, "-q:v", "2",  # JPEG quality scale 2 ≈ ~95% quality
                       "-y", str(out_path)]
                logger.info(f"✂️ {name}: {out_path.name}")
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=60, **_NO_WINDOW_FLAGS)
                if r.returncode != 0 or not out_path.exists():
                    logger.error(f"❌ {name}: {(r.stderr or '')[-200:]}")
                    return False
                size_mb = out_path.stat().st_size / (1024 * 1024)
                logger.info(f"✅ {name}: {size_mb:.2f} MiB")
                created.append(out_path)
            self._write_manifest(output_dir, manifest_op, manifest_params,
                                 archivos=created, fuente=image_path)
            return True
        except Exception as e:
            logger.error(f"❌ _split_image_into_jpeg_parts: {e}")
            return False

    def split_image_for_artwork_showcase(self, image_path: Path, output_dir=None) -> bool:
        """Split static image (JPG/PNG) into JPEG panels (main 506px + side 100px)."""
        if not self.check_ffmpeg():
            logger.error("❌ FFmpeg no disponible")
            return False
        image_path = Path(image_path)
        if output_dir is None:
            output_dir = self._workspace_dir(image_path, "fragmentos")
        output_dir = Path(output_dir)
        self._archive_before_overwrite(output_dir)
        main_width = self.config.get('artwork_showcase.main_width', 506)
        side_width = self.config.get('artwork_showcase.side_width', 100)
        total_width = main_width + side_width
        forced_height = self.config.get('artwork_showcase.height', 0)
        fixed_h = int(forced_height) if forced_height and int(forced_height) > 0 else None

        parts = [("artwork_main", main_width, 0), ("artwork_side", side_width, main_width)]
        logger.info(f"🎨 Fragmentando imagen para Artwork Showcase: {image_path}")
        return self._split_image_into_jpeg_parts(
            image_path, parts, total_width, fixed_h, output_dir,
            "fragmentar_artwork_showcase_image",
            {"main_width": main_width, "side_width": side_width, "format": "jpeg"},
        )

    def split_image_for_showcase(self, image_path: Path, preset: str, output_dir=None) -> bool:
        """Split static image (JPG/PNG) into JPEG panels per showcase preset."""
        if preset not in self.SHOWCASE_PRESETS:
            logger.error(f"❌ Preset desconocido: {preset}")
            return False
        if not self.check_ffmpeg():
            logger.error("❌ FFmpeg no disponible")
            return False
        image_path = Path(image_path)
        cfg = self.SHOWCASE_PRESETS[preset]
        if output_dir is None:
            output_dir = self._workspace_dir(image_path, "fragmentos")
        output_dir = Path(output_dir)
        self._archive_before_overwrite(output_dir)
        logger.info(f"🎨 Preset '{preset}' (imagen) → {cfg['desc']}")
        return self._split_image_into_jpeg_parts(
            image_path, cfg["parts"], cfg["total_w"], cfg["fixed_h"], output_dir,
            f"fragmentar_showcase_image_{preset}",
            {"preset": preset, "format": "jpeg"},
        )

    # ---- Showcase preset registry (layouts verified on Steam forums 2025) ----
    # Each preset defines:
    #   parts: list of (name, width_px, left_offset_px) crop segments from the scaled source
    #   total_w: width to scale the source to before cropping
    #   fixed_h: forced height in pixels (None = preserve source aspect ratio)
    #   upload_hint: recommended upload mode ("artwork" / "screenshot" / "workshop")
    SHOWCASE_PRESETS = {
        # 1 slot — sin fragmentar
        "featured_630": {
            "parts": [("featured", 630, 0)], "total_w": 630, "fixed_h": None,
            "upload_hint": "artwork",
            "desc": "Featured Artwork 630×H (1 slot grande)",
        },
        "artwork_single_630": {
            "parts": [("single", 630, 0)], "total_w": 630, "fixed_h": 354,
            "upload_hint": "artwork",
            "desc": "Artwork single 630×354 (sin side image, 16:9)",
        },
        "screenshot_638": {
            "parts": [("screenshot", 638, 0)], "total_w": 638, "fixed_h": 354,
            "upload_hint": "screenshot",
            "desc": "Screenshot Showcase 638×354 (1 slot, file_type=5)",
        },
        # 2 slots — layout artwork normal
        "artwork_2part": {
            "parts": [("artwork_main", 506, 0), ("artwork_side", 100, 506)],
            "total_w": 606, "fixed_h": None,
            "upload_hint": "artwork",
            "desc": "Artwork 506+100 (main+side, alto libre)",
        },
        # 4 slots — grid artwork
        "artwork_4grid": {
            "parts": [(f"artwork_g{i+1}", 245, 245*i) for i in range(4)],
            "total_w": 980, "fixed_h": 245,
            "upload_hint": "artwork",
            "desc": "Artwork 4-grid 4×245 cuadrados",
        },
        # 4 slots — screenshot 4-grid
        "screenshot_4grid": {
            "parts": [(f"ss_g{i+1}", 638, 638*i) for i in range(4)],
            "total_w": 2552, "fixed_h": 354,
            "upload_hint": "screenshot",
            "desc": "Screenshot 4-grid 4×638×354 (file_type=5)",
        },
        # 5 slots workshop 150×150 (sin bordes)
        "workshop_5slot_150": {
            "parts": [(f"ws_s{i+1}", 150, 150*i) for i in range(5)],
            "total_w": 750, "fixed_h": 150,
            "upload_hint": "workshop",
            "desc": "Workshop Showcase 5×150×150",
        },
        # 5 slots workshop 119×119 (tamaño real del grid)
        "workshop_5slot_119": {
            "parts": [(f"ws_s{i+1}", 119, 119*i) for i in range(5)],
            "total_w": 595, "fixed_h": 119,
            "upload_hint": "workshop",
            "desc": "Workshop Showcase 5×119×119 (tamaño nativo)",
        },
        # 5 slots panorama artwork — banner horizontal 3150×360
        "panorama_5_630": {
            "parts": [(f"pano_{i+1}", 630, 630*i) for i in range(5)],
            "total_w": 3150, "fixed_h": 360,
            "upload_hint": "artwork",
            "desc": "Panorama artwork 5×630×360 (banner horizontal)",
        },
    }

    def split_gif_for_showcase(self, gif_path: Path, preset: str,
                               output_dir: Optional[Path] = None) -> bool:
        """Fragmenta un GIF según preset de showcase.

        Pipeline idéntico a split_gif_for_artwork_showcase (2-pass palette + ladder
        de calidad), pero parametrizado por preset. Garantiza trailer-patch y
        tamaño ≤ 5 MiB por parte.
        """
        if preset not in self.SHOWCASE_PRESETS:
            logger.error(f"❌ Preset desconocido: {preset}")
            return False
        if not self.check_ffmpeg():
            logger.error("❌ FFmpeg no disponible")
            return False

        cfg = self.SHOWCASE_PRESETS[preset]
        parts_cfg = cfg["parts"]
        total_w = cfg["total_w"]
        fixed_h = cfg["fixed_h"]

        if output_dir is None:
            output_dir = self._workspace_dir(gif_path, "fragmentos")
        output_dir = Path(output_dir)
        self._archive_before_overwrite(output_dir)

        MAX_BYTES = 5 * 1024 * 1024 - 16 * 1024
        STEAM_HARD_MAX = 5 * 1024 * 1024

        logger.info(f"🎨 Preset '{preset}' → {cfg['desc']}")
        try:
            with Image.open(gif_path) as img:
                orig_w, orig_h = img.size

            if fixed_h:
                target_h = int(fixed_h)
            else:
                target_h = max(1, round(orig_h * total_w / max(1, orig_w)))
            if target_h % 2 == 1:
                target_h += 1
            logger.info(f"📐 Target: {total_w}×{target_h}, {len(parts_cfg)} parte(s)")

            ffmpeg_ladder = [
                (256, None), (256, 24), (192, 24), (160, 20),
                (128, 20), (96, 15), (64, 12),
            ]

            _use_gifski = self.check_gifski()
            _orig_fps = 25
            try:
                with Image.open(gif_path) as _fps_img:
                    _dur = _fps_img.info.get('duration', 40) or 40
                    _orig_fps = max(1, int(round(1000.0 / _dur)))
            except Exception:
                pass

            import tempfile
            _tmp = Path(tempfile.mkdtemp(prefix="wkart_showcase_"))
            created = []
            _gifski_done = False
            try:
                # ── gifski: shared fps+quality for ALL parts ─────────────────
                if _use_gifski:
                    for fps_cap in [None, 24, 20, 15, 12, 10, 8, 6, 4, 3]:
                        _fps_a = str(fps_cap) if fps_cap else str(_orig_fps)

                        # Extract frames for every part at this fps tier
                        _fds: dict = {}
                        _ex_ok = True
                        for (name, w, left) in parts_cfg:
                            if fixed_h:
                                _sc = (f"scale={total_w}:{target_h}"
                                       f":force_original_aspect_ratio=increase:flags=lanczos,"
                                       f"crop={total_w}:{target_h}")
                                _cr = f"crop={w}:{target_h}:{left}:0"
                            else:
                                _sc = f"scale={total_w}:-2:flags=lanczos"
                                _cr = f"crop={w}:ih:{left}:0"
                            _vf = (f"fps={fps_cap}," if fps_cap else "") + f"{_sc},{_cr}"
                            fd = _tmp / f"fd_{fps_cap or 0}_{name}"
                            shutil.rmtree(fd, ignore_errors=True)
                            fd.mkdir()
                            r_ex = subprocess.run(
                                [str(self.ffmpeg_path), "-y", "-i", str(gif_path),
                                 "-vf", _vf, str(fd / "frame%06d.png")],
                                capture_output=True, encoding='utf-8',
                                errors='replace', timeout=180, **_NO_WINDOW_FLAGS)
                            if r_ex.returncode != 0 or not any(fd.glob("frame*.png")):
                                logger.warning(f"   gifski/extract {name} fps={_fps_a}: rc={r_ex.returncode}")
                                _ex_ok = False
                                break
                            _fds[name] = fd

                        if not _ex_ok:
                            for fd in _fds.values():
                                shutil.rmtree(fd, ignore_errors=True)
                            continue

                        # Binary-search shared quality where ALL parts fit
                        q_lo, q_hi = 10, 95
                        _best_q = None
                        _best_baks: dict = {}
                        _best_sizes: dict = {}

                        while q_lo <= q_hi:
                            q = (q_lo + q_hi) // 2
                            _res: dict = {}
                            _all_fit = True
                            for (name, w, left) in parts_cfg:
                                out_path = output_dir / f"{gif_path.stem}_{name}.gif"
                                fd = _fds[name]
                                r = subprocess.run(
                                    [str(self.gifski_path), "--fps", _fps_a,
                                     "--quality", str(q), "--repeat", "0",
                                     "-o", str(out_path), str(fd / "frame*.png")],
                                    capture_output=True, encoding='utf-8',
                                    errors='replace', timeout=180, **_NO_WINDOW_FLAGS)
                                if r.returncode != 0 or not out_path.exists():
                                    logger.warning(f"   gifski {name} q={q} rc={r.returncode}")
                                    _all_fit = False
                                    break
                                sz = out_path.stat().st_size
                                logger.info(f"   gifski {name} q={q} fps={_fps_a} → {sz/1024/1024:.2f} MiB")
                                _res[name] = (out_path, sz)
                                if sz > MAX_BYTES:
                                    _all_fit = False
                                    break

                            if _all_fit and len(_res) == len(parts_cfg):
                                _best_q = q
                                for name, (path, sz) in _res.items():
                                    bak = path.with_suffix("._gbest")
                                    shutil.copy(path, bak)
                                    _best_baks[name] = bak
                                    _best_sizes[name] = sz
                                q_lo = q + 1
                            else:
                                q_hi = q - 1

                        for fd in _fds.values():
                            shutil.rmtree(fd, ignore_errors=True)

                        if _best_q is not None:
                            for (name, w, left) in parts_cfg:
                                out_path = output_dir / f"{gif_path.stem}_{name}.gif"
                                bak = _best_baks.get(name)
                                if bak and bak.exists():
                                    shutil.copy(bak, out_path)
                                    try: bak.unlink()
                                    except OSError: pass
                                self._patch_gif_trailer(out_path)
                                sz = _best_sizes[name]
                                created.append({"name": name, "path": out_path,
                                                "size": sz/1024/1024,
                                                "colors": _best_q, "fps_cap": fps_cap})
                                logger.info(f"✅ {name}: {sz/1024/1024:.2f} MiB "
                                            f"[gifski fps={_fps_a} q={_best_q}]")
                            _gifski_done = True
                            break

                        for bak in _best_baks.values():
                            try: bak.unlink()
                            except OSError: pass

                # ── ffmpeg fallback: per-part ─────────────────────────────────
                if not _gifski_done:
                    for (name, w, left) in parts_cfg:
                        out_path = output_dir / f"{gif_path.stem}_{name}.gif"
                        chosen = None
                        last_err = ""
                        for colors, fps_cap in ffmpeg_ladder:
                            fps_part = f"fps={fps_cap}," if fps_cap else ""
                            if fixed_h:
                                scale = (f"scale={total_w}:{target_h}"
                                         f":force_original_aspect_ratio=increase"
                                         f":flags=lanczos+accurate_rnd+full_chroma_int,"
                                         f"crop={total_w}:{target_h}")
                                crop = f"crop={w}:{target_h}:{left}:0"
                            else:
                                scale = (f"scale={total_w}:-2"
                                         f":flags=lanczos+accurate_rnd+full_chroma_int")
                                crop = f"crop={w}:ih:{left}:0"
                            filter_complex = (
                                f"[0:v]{fps_part}{scale},{crop},split[a][b];"
                                f"[a]palettegen=max_colors={colors}:stats_mode=full"
                                f":reserve_transparent=1[p];"
                                f"[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle"
                            )
                            cmd = [str(self.ffmpeg_path), "-i", str(gif_path),
                                   "-filter_complex", filter_complex, "-loop", "0",
                                   "-y", str(out_path)]
                            try:
                                r = subprocess.run(cmd, capture_output=True,
                                                   encoding='utf-8', errors='replace',
                                                   timeout=180, **_NO_WINDOW_FLAGS)
                                if r.returncode != 0:
                                    last_err = (r.stderr or "")[-200:]
                                    continue
                                if not out_path.exists():
                                    last_err = "ffmpeg no creó el archivo"
                                    continue
                                sz = out_path.stat().st_size
                                if sz <= MAX_BYTES:
                                    chosen = (colors, fps_cap, sz)
                                    break
                            except subprocess.TimeoutExpired:
                                last_err = "timeout"
                                continue
                            except Exception as e:
                                last_err = str(e)
                                continue

                        if chosen is None:
                            logger.error(
                                f"❌ {name}: no generado ≤ {STEAM_HARD_MAX/1024/1024:.1f} MiB. {last_err}")
                            return False
                        self._patch_gif_trailer(out_path)
                        info, fc, sz = chosen
                        created.append({"name": name, "path": out_path,
                                        "size": sz/1024/1024, "colors": info, "fps_cap": fc})
                        logger.info(f"✅ {name}: {sz/1024/1024:.2f} MiB [ffmpeg fps={fc or 'orig'}]")
            finally:
                shutil.rmtree(_tmp, ignore_errors=True)

            self._write_manifest(output_dir, f"showcase_{preset}",
                {"preset": preset, "total_w": total_w, "height": target_h,
                 "parts": [{"n": p["name"], "colors": p["colors"], "fps": p["fps_cap"]}
                           for p in created]},
                archivos=[p["path"] for p in created], fuente=gif_path)
            logger.info(f"✅ Preset '{preset}' completado: {len(created)} parte(s)")
            return True
        except Exception as e:
            logger.error(f"❌ Error preset '{preset}': {e}")
            return False


