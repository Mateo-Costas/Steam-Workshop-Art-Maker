"""processing.shrink - GIF size-cap optimisation (gifski binary search + FFmpeg ladder)."""
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple, Callable

from PIL import Image, ImageSequence

from processing.common import _NO_WINDOW_FLAGS, logger


class ShrinkMixin:
    def shrink_to_size_cap(self, gif_path: Path,
                           max_mb: float = 5.0,
                           min_mb: float = 4.7,
                           progress_cb: Optional[Callable[[str], None]] = None) -> Optional[Path]:
        """Reducir un GIF por debajo de max_mb manteniendo máxima calidad.

        Busca el resultado con mayor tamaño que quepa en [min_mb, max_mb].
        Si no logra bajar de max_mb, devuelve el mejor candidato por debajo
        y loguea advertencia. No modifica el archivo original; escribe
        <stem>_opt.gif al lado.
        """
        def log(msg: str):
            logger.info(msg)
            if progress_cb:
                try:
                    progress_cb(msg)
                except Exception:
                    pass

        if not self.ffmpeg_path:
            log("FFmpeg no disponible")
            return None
        if not gif_path.exists():
            log(f"No existe: {gif_path}")
            return None

        original_mb = gif_path.stat().st_size / (1024 * 1024)
        log(f"Tamaño original: {original_mb:.2f} MB (objetivo ≤ {max_mb:.2f} MB)")

        if original_mb <= max_mb and original_mb >= min_mb:
            log("Ya cumple el rango, no hay que tocarlo")
            return gif_path

        # Quality ladder: (fps, max_colors, scale_factor), ordered highest→lowest quality.
        # scale is always 1.0 — resizing individual fragments would desync the long-artwork
        # layout on the Steam profile. Only fps and palette depth are reduced.
        strategies: List[Tuple[str, int, float]] = [
            # Phase 1: palette reduction only, original fps (maximum visual quality)
            ("keep", 256, 1.0),
            ("keep", 224, 1.0),
            ("keep", 192, 1.0),
            ("keep", 160, 1.0),
            ("keep", 128, 1.0),
            ("keep", 96,  1.0),
            # Phase 2: 30 fps
            ("30",   256, 1.0),
            ("30",   224, 1.0),
            ("30",   192, 1.0),
            ("30",   160, 1.0),
            ("30",   128, 1.0),
            ("30",   96,  1.0),
            # Phase 3: 25 fps
            ("25",   224, 1.0),
            ("25",   192, 1.0),
            ("25",   160, 1.0),
            ("25",   128, 1.0),
            ("25",   96,  1.0),
            # Phase 4: 22 fps
            ("22",   192, 1.0),
            ("22",   160, 1.0),
            ("22",   128, 1.0),
            ("22",   96,  1.0),
            # Phase 5: 20 fps
            ("20",   192, 1.0),
            ("20",   160, 1.0),
            ("20",   128, 1.0),
            ("20",   96,  1.0),
            ("20",   80,  1.0),
            # Phase 6: 18 fps
            ("18",   160, 1.0),
            ("18",   128, 1.0),
            ("18",   96,  1.0),
            ("18",   80,  1.0),
            # Phase 7: 15 fps
            ("15",   128, 1.0),
            ("15",   96,  1.0),
            ("15",   80,  1.0),
            ("15",   64,  1.0),
            # Phase 8: 12 fps
            ("12",   96,  1.0),
            ("12",   80,  1.0),
            ("12",   64,  1.0),
            ("12",   48,  1.0),
            # Phase 9: 10 fps
            ("10",   80,  1.0),
            ("10",   64,  1.0),
            ("10",   48,  1.0),
            ("10",   32,  1.0),
            # Phase 10: last resort (8-6 fps)
            ("8",    48,  1.0),
            ("8",    32,  1.0),
            ("6",    32,  1.0),
            ("6",    16,  1.0),
        ]

        out_dir = self._workspace_dir(gif_path, "optimizado")
        self._archive_before_overwrite(out_dir, keep_names=[f"{gif_path.stem}_opt.gif"])
        out_path = out_dir / f"{gif_path.stem}_opt.gif"
        best_path: Optional[Path] = None
        best_mb: float = 0.0
        winning_strategy: Optional[Tuple[str, int, float]] = None

        import tempfile
        tmp_dir = Path(tempfile.mkdtemp(prefix="wkart_opt_"))

        def _run_candidate(fps: str, colors: int, scale: float,
                           label_idx: str) -> Tuple[Optional[Path], float]:
            """Run FFmpeg with given fps/colors/scale parameters. Returns (path, size_mb) or (None, 0.0)."""
            filters = []
            if fps != "keep":
                filters.append(f"fps={fps}")
            if scale < 1.0:
                filters.append(f"scale=iw*{scale}:ih*{scale}:flags=lanczos")
            filters.append(
                # stats_mode=diff builds palette from changed pixels only (better for animations)
                f"split[s0][s1];[s0]palettegen=max_colors={colors}:stats_mode=diff[p];"
                f"[s1][p]paletteuse=dither=sierra2_4a"
            )
            vf = ",".join(filters)
            cand = tmp_dir / f"cand_{label_idx}.gif"
            cmd = [str(self.ffmpeg_path), "-y", "-i", str(gif_path),
                   "-vf", vf, "-loop", "0", str(cand)]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=180, **_NO_WINDOW_FLAGS)
            except Exception as e:
                log(f"  Candidato {label_idx} error: {e}")
                return None, 0.0
            if r.returncode != 0 or not cand.exists():
                log(f"  Candidato {label_idx} falló (rc={r.returncode})")
                return None, 0.0
            return cand, cand.stat().st_size / (1024 * 1024)

        try:
            # ── gifski primary path ────────────────────────────────────────────
            if self.gifski_path and self.gifski_path.exists():
                _orig_fps = 25
                try:
                    with Image.open(gif_path) as _img:
                        _dur = _img.info.get('duration', 40) or 40
                        _orig_fps = max(1, int(round(1000.0 / _dur)))
                except Exception:
                    pass

                gifski_fps_tiers = [None, 24, 20, 15, 12, 10, 8, 6, 4, 3]
                max_bytes = int(max_mb * 1024 * 1024)
                gsk_frames = tmp_dir / "_gsk_frames"

                for fps_cap in gifski_fps_tiers:
                    shutil.rmtree(gsk_frames, ignore_errors=True)
                    gsk_frames.mkdir()
                    cmd_ex = [str(self.ffmpeg_path), "-y", "-i", str(gif_path)]
                    if fps_cap:
                        cmd_ex += ["-vf", f"fps={fps_cap}"]
                    cmd_ex.append(str(gsk_frames / "frame%06d.png"))
                    r_ex = subprocess.run(cmd_ex, capture_output=True,
                                          encoding='utf-8', errors='replace',
                                          timeout=180, **_NO_WINDOW_FLAGS)
                    if r_ex.returncode != 0 or not any(gsk_frames.glob("frame*.png")):
                        log(f"  gifski fps={fps_cap or 'orig'}: extracción falló")
                        continue

                    fps_arg = str(fps_cap) if fps_cap else str(_orig_fps)
                    gsk_out = tmp_dir / "_gsk_out.gif"
                    result = self._gifski_optimal(
                        str(gsk_frames / "frame*.png"), gsk_out, fps_arg, max_bytes
                    )
                    if result is not None:
                        q, size = result
                        size_mb = size / (1024 * 1024)
                        log(f"✅ gifski fps={fps_cap or 'orig'} q={q} → {size_mb:.2f} MB")
                        shutil.copy(gsk_out, out_path)
                        self._write_manifest(out_dir, "optimizar_tamano",
                            {"max_mb": max_mb, "min_mb": min_mb,
                             "engine": "gifski", "fps": fps_cap or "orig", "quality": q,
                             "resultado_mb": round(size_mb, 3),
                             "original_mb": round(original_mb, 3)},
                            archivos=[out_path], fuente=gif_path)
                        self._patch_gif_trailer(out_path)
                        return out_path
                    log(f"  gifski fps={fps_cap or 'orig'}: no cupo bajo {max_mb:.2f} MB")

                log(f"gifski no consiguió bajar de {max_mb:.2f} MB — usando ffmpeg...")

            # ── ffmpeg ladder ──────────────────────────────────────────────────
            hit_range = False
            for idx, (fps, colors, scale) in enumerate(strategies, 1):
                candidate, size_mb = _run_candidate(fps, colors, scale, f"{idx:02d}")
                if candidate is None:
                    continue

                label = f"fps={fps}, colors={colors}, scale={scale}"
                log(f"  [{idx}/{len(strategies)}] {label} → {size_mb:.2f} MB")

                # Dentro del rango óptimo → perfecto, parar aquí
                if min_mb <= size_mb <= max_mb:
                    best_path = candidate
                    best_mb = size_mb
                    winning_strategy = (fps, colors, scale)
                    log(f"✅ Dentro del rango [{min_mb:.1f}, {max_mb:.1f}] MB en intento {idx}")
                    hit_range = True
                    break

                # Por debajo del máximo: candidato válido, guardar el mayor
                if size_mb <= max_mb and size_mb > best_mb:
                    best_mb = size_mb
                    best_path = candidate
                    winning_strategy = (fps, colors, scale)
                    # Primera vez que cabe bajo el cap → salimos a refinar.
                    # Las siguientes estrategias son de MENOR calidad, no tiene
                    # sentido seguirlas si ya cabe.
                    break

                # Por encima todavía: sigue bajando calidad
                # (no hacemos nada, el loop continúa)

            # Refinamiento: si cabe pero está por debajo de min_mb, búsqueda
            # binaria de paleta hacia arriba para acercarnos al cap sin pasarnos.
            if (not hit_range and best_path is not None and winning_strategy is not None
                    and best_mb < min_mb):
                w_fps, w_colors, w_scale = winning_strategy
                log(f"🔧 Margen libre ({best_mb:.2f} MB < {min_mb:.1f}) — "
                    f"refinando paleta hacia arriba para maximizar calidad...")
                lo, hi = w_colors, 256
                for probe in range(6):
                    if hi - lo <= 4:
                        break
                    mid = (lo + hi) // 2
                    cand, size_mb = _run_candidate(w_fps, mid, w_scale, f"ref{probe+1}")
                    if cand is None:
                        break
                    log(f"  refinado paleta={mid} → {size_mb:.2f} MB")
                    if size_mb <= max_mb:
                        if size_mb > best_mb:
                            best_mb = size_mb
                            best_path = cand
                            winning_strategy = (w_fps, mid, w_scale)
                        lo = mid
                        if min_mb <= size_mb <= max_mb:
                            log(f"✅ Refinado en rango [{min_mb:.1f}, {max_mb:.1f}] "
                                f"con paleta={mid}")
                            break
                    else:
                        hi = mid

            if hit_range or best_path is not None:
                # Salida con el mejor candidato encontrado
                shutil.copy(best_path, out_path)
                fps_w, colors_w, scale_w = winning_strategy or ("?", 0, 0.0)
                self._write_manifest(out_dir, "optimizar_tamano",
                    {"max_mb": max_mb, "min_mb": min_mb,
                     "fps": fps_w, "colors": colors_w, "scale": scale_w,
                     "resultado_mb": round(best_mb, 3),
                     "original_mb": round(original_mb, 3)},
                    archivos=[out_path], fuente=gif_path)
                self._patch_gif_trailer(out_path)
                return out_path

            log(f"❌ No se consiguió bajar de {max_mb:.2f} MB con ninguna "
                f"de las {len(strategies)} estrategias probadas.")
            log(f"   Tamaño original: {original_mb:.2f} MB — el GIF es "
                f"demasiado largo. Recorta la duración de entrada.")
            return None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def shrink_batch_to_size_cap(self, gif_paths: List[Path],
                                 max_mb: float = 5.0,
                                 min_mb: float = 4.7,
                                 progress_cb: Optional[Callable[[str], None]] = None
                                 ) -> List[Optional[Path]]:
        """Optimiza varios fragmentos compartiendo UNA misma estrategia.

        Esto evita desincronización visual cuando los fragmentos se muestran
        como long-artwork lado a lado (si cada uno tuviera distinto fps,
        se verían fuera de sincronía). Busca la estrategia de mayor calidad
        en la que TODOS los fragmentos quepan bajo `max_mb`, y la aplica a
        todos. Luego refina paleta hacia arriba si el mayor queda por
        debajo de `min_mb`.

        Devuelve lista de rutas de salida (una por input), con None donde
        no se haya podido optimizar.
        """
        def log(msg: str):
            logger.info(msg)
            if progress_cb:
                try:
                    progress_cb(msg)
                except Exception:
                    pass

        if not self.ffmpeg_path:
            log("FFmpeg no disponible")
            return [None] * len(gif_paths)

        paths = [Path(p) for p in gif_paths if p and Path(p).exists()]
        if not paths:
            return []

        # Mismas fases que shrink_to_size_cap (ordenadas de mayor a menor calidad)
        strategies: List[Tuple[str, int, float]] = [
            ("keep", 256, 1.0), ("keep", 224, 1.0), ("keep", 192, 1.0),
            ("keep", 160, 1.0), ("keep", 128, 1.0), ("keep", 96, 1.0),
            ("30", 256, 1.0), ("30", 224, 1.0), ("30", 192, 1.0),
            ("30", 160, 1.0), ("30", 128, 1.0), ("30", 96, 1.0),
            ("25", 224, 1.0), ("25", 192, 1.0), ("25", 160, 1.0),
            ("25", 128, 1.0), ("25", 96, 1.0),
            ("22", 192, 1.0), ("22", 160, 1.0), ("22", 128, 1.0), ("22", 96, 1.0),
            ("20", 192, 1.0), ("20", 160, 1.0), ("20", 128, 1.0),
            ("20", 96, 1.0), ("20", 80, 1.0),
            ("18", 160, 1.0), ("18", 128, 1.0), ("18", 96, 1.0), ("18", 80, 1.0),
            ("15", 128, 1.0), ("15", 96, 1.0), ("15", 80, 1.0), ("15", 64, 1.0),
            ("12", 96, 1.0), ("12", 80, 1.0), ("12", 64, 1.0), ("12", 48, 1.0),
            ("10", 80, 1.0), ("10", 64, 1.0), ("10", 48, 1.0), ("10", 32, 1.0),
            ("8", 48, 1.0), ("8", 32, 1.0), ("6", 32, 1.0), ("6", 16, 1.0),
        ]

        import tempfile
        tmp_dir = Path(tempfile.mkdtemp(prefix="wkart_batch_opt_"))

        def _run_all(fps: str, colors: int, scale: float,
                     label: str) -> Optional[List[Tuple[Path, float]]]:
            """Apply one strategy to all input fragments. Returns list of (candidate_path, size_mb)
            if every fragment succeeded, or None if any fragment failed."""
            filters = []
            if fps != "keep":
                filters.append(f"fps={fps}")
            if scale < 1.0:
                filters.append(f"scale=iw*{scale}:ih*{scale}:flags=lanczos")
            filters.append(
                # stats_mode=diff: palette optimised for motion rather than the full colour space
                f"split[s0][s1];[s0]palettegen=max_colors={colors}:stats_mode=diff[p];"
                f"[s1][p]paletteuse=dither=sierra2_4a"
            )
            vf = ",".join(filters)
            out: List[Tuple[Path, float]] = []
            for i, src in enumerate(paths):
                cand = tmp_dir / f"{label}_{i:02d}.gif"
                cmd = [str(self.ffmpeg_path), "-y", "-i", str(src),
                       "-vf", vf, "-loop", "0", str(cand)]
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True,
                                       timeout=180, **_NO_WINDOW_FLAGS)
                except Exception as e:
                    log(f"  {label} frag {i+1} error: {e}")
                    return None
                if r.returncode != 0 or not cand.exists():
                    return None
                out.append((cand, cand.stat().st_size / (1024 * 1024)))
            return out

        log(f"=== Optimización batch de {len(paths)} fragmentos a ≤{max_mb:.2f} MB (estrategia compartida) ===")

        winning_strategy: Optional[Tuple[str, int, float]] = None
        winning_results: Optional[List[Tuple[Path, float]]] = None

        try:
            # ── gifski primary path (shared quality across all fragments) ──────
            if self.gifski_path and self.gifski_path.exists():
                _orig_fps = 25
                try:
                    with Image.open(paths[0]) as _img:
                        _dur = _img.info.get('duration', 40) or 40
                        _orig_fps = max(1, int(round(1000.0 / _dur)))
                except Exception:
                    pass

                gifski_fps_tiers = [None, 24, 20, 15, 12, 10, 8, 6, 4, 3]
                max_bytes = int(max_mb * 1024 * 1024)
                gsk_tmp = tmp_dir / "_gsk"
                gsk_tmp.mkdir()

                for fps_cap in gifski_fps_tiers:
                    fps_arg = str(fps_cap) if fps_cap else str(_orig_fps)

                    frame_dirs: List[Path] = []
                    extract_ok = True
                    for i, src in enumerate(paths):
                        fd = gsk_tmp / f"fd_{fps_cap or 0}_{i}"
                        shutil.rmtree(fd, ignore_errors=True)
                        fd.mkdir()
                        cmd_ex = [str(self.ffmpeg_path), "-y", "-i", str(src)]
                        if fps_cap:
                            cmd_ex += ["-vf", f"fps={fps_cap}"]
                        cmd_ex.append(str(fd / "frame%06d.png"))
                        r_ex = subprocess.run(cmd_ex, capture_output=True,
                                              encoding='utf-8', errors='replace',
                                              timeout=180, **_NO_WINDOW_FLAGS)
                        if r_ex.returncode != 0 or not any(fd.glob("frame*.png")):
                            log(f"  gifski batch fps={fps_arg}: extracción falló para {src.name}")
                            extract_ok = False
                            break
                        frame_dirs.append(fd)

                    if not extract_ok:
                        continue

                    # Binary-search shared quality where ALL fragments fit
                    q_lo, q_hi = 10, 95
                    best_q: Optional[int] = None
                    best_gsk_results: Optional[List[Tuple[Path, float]]] = None

                    while q_lo <= q_hi:
                        q = (q_lo + q_hi) // 2
                        frag_results: List[Tuple[Path, float]] = []
                        all_fit = True
                        for i, fd in enumerate(frame_dirs):
                            gsk_out = gsk_tmp / f"q{q}_{i}.gif"
                            r = subprocess.run(
                                [str(self.gifski_path), "--fps", fps_arg,
                                 "--quality", str(q), "--repeat", "0",
                                 "-o", str(gsk_out), str(fd / "frame*.png")],
                                capture_output=True, encoding='utf-8',
                                errors='replace', timeout=180, **_NO_WINDOW_FLAGS,
                            )
                            if r.returncode != 0 or not gsk_out.exists():
                                log(f"   gifski batch q={q} frag {i}: rc={r.returncode}")
                                all_fit = False
                                break
                            size = gsk_out.stat().st_size
                            frag_results.append((gsk_out, size / (1024 * 1024)))
                            if size > max_bytes:
                                all_fit = False
                                break

                        if all_fit and len(frag_results) == len(frame_dirs):
                            best_q = q
                            best_gsk_results = list(frag_results)
                            q_lo = q + 1
                            log(f"   gifski batch fps={fps_arg} q={q} → OK "
                                f"(max={max(r[1] for r in frag_results):.2f} MB)")
                        else:
                            q_hi = q - 1

                    if best_q is not None and best_gsk_results is not None:
                        log(f"✅ gifski batch fps={fps_arg} q={best_q}")
                        all_out_names = [f"{src.stem}_opt.gif" for src in paths]
                        dirs_cleaned_gsk: set = set()
                        _gsk_out_paths: List[Optional[Path]] = []
                        for src in paths:
                            od = self._workspace_dir(src, "optimizado")
                            if od not in dirs_cleaned_gsk:
                                self._archive_before_overwrite(od, keep_names=all_out_names)
                                dirs_cleaned_gsk.add(od)
                        for src, (cand, size_mb) in zip(paths, best_gsk_results):
                            od = self._workspace_dir(src, "optimizado")
                            dst = od / f"{src.stem}_opt.gif"
                            shutil.copy(cand, dst)
                            self._write_manifest(od, "optimizar_tamano_batch",
                                {"max_mb": max_mb, "min_mb": min_mb,
                                 "engine": "gifski", "fps": fps_cap or "orig",
                                 "quality": best_q,
                                 "resultado_mb": round(size_mb, 3),
                                 "estrategia_compartida": True,
                                 "total_fragmentos": len(paths)},
                                archivos=[dst], fuente=src)
                            self._patch_gif_trailer(dst)
                            _gsk_out_paths.append(dst)
                            log(f"✅ {src.name} → {dst.name} ({size_mb:.2f} MB)")
                        return _gsk_out_paths

                    log(f"  gifski batch fps={fps_arg}: ninguna calidad cupo en todos")

                log(f"gifski batch: ningún tier funcionó, usando ffmpeg fallback...")

            # ── ffmpeg ladder ──────────────────────────────────────────────────
            # 1) Primer fit: estrategia de mayor calidad donde TODOS quepan
            for idx, (fps, colors, scale) in enumerate(strategies, 1):
                results = _run_all(fps, colors, scale, f"s{idx:02d}")
                if results is None:
                    log(f"  [{idx}/{len(strategies)}] fps={fps}, colors={colors} — falló algún fragmento")
                    continue
                max_mb_seen = max(r[1] for r in results)
                log(f"  [{idx}/{len(strategies)}] fps={fps}, colors={colors} → max fragmento: {max_mb_seen:.2f} MB")
                if max_mb_seen <= max_mb:
                    winning_strategy = (fps, colors, scale)
                    winning_results = results
                    log(f"✅ Todos los fragmentos caben bajo {max_mb:.2f} MB en intento {idx}")
                    break

            # 2) Refinamiento de paleta si hay margen
            if winning_strategy is not None and winning_results is not None:
                w_fps, w_colors, w_scale = winning_strategy
                cur_max = max(r[1] for r in winning_results)
                if cur_max < min_mb and w_colors < 256:
                    log(f"🔧 Margen libre (max={cur_max:.2f} MB < {min_mb:.1f}) — "
                        f"refinando paleta hacia arriba...")
                    lo, hi = w_colors, 256
                    for probe in range(6):
                        if hi - lo <= 4:
                            break
                        mid = (lo + hi) // 2
                        res = _run_all(w_fps, mid, w_scale, f"ref{probe+1}")
                        if res is None:
                            hi = mid
                            continue
                        mx = max(r[1] for r in res)
                        log(f"  refinado paleta={mid} → max fragmento: {mx:.2f} MB")
                        if mx <= max_mb:
                            if mx > cur_max:
                                cur_max = mx
                                winning_strategy = (w_fps, mid, w_scale)
                                winning_results = res
                            lo = mid
                            if mx >= min_mb:
                                log(f"✅ Refinado en rango [{min_mb:.1f}, {max_mb:.1f}] con paleta={mid}")
                                break
                        else:
                            hi = mid

            if winning_results is None or winning_strategy is None:
                log(f"❌ No se encontró estrategia común bajo {max_mb:.2f} MB para todos los fragmentos.")
                return [None] * len(paths)

            # 3) Copiar candidatos a carpeta "optimizado" de cada fragmento
            out_paths: List[Optional[Path]] = []
            fps_w, colors_w, scale_w = winning_strategy

            # Limpia UNA sola vez preservando TODOS los nombres de salida.
            # (Hacerlo dentro del loop borraba los fragmentos ya escritos.)
            all_out_names = [f"{src.stem}_opt.gif" for src in paths]
            dirs_cleaned: set = set()
            for src in paths:
                out_dir = self._workspace_dir(src, "optimizado")
                if out_dir in dirs_cleaned:
                    continue
                self._archive_before_overwrite(out_dir, keep_names=all_out_names)
                dirs_cleaned.add(out_dir)

            for src, (cand, size_mb) in zip(paths, winning_results):
                try:
                    out_dir = self._workspace_dir(src, "optimizado")
                    dst = out_dir / f"{src.stem}_opt.gif"
                    shutil.copy(cand, dst)
                    self._write_manifest(out_dir, "optimizar_tamano_batch",
                        {"max_mb": max_mb, "min_mb": min_mb,
                         "fps": fps_w, "colors": colors_w, "scale": scale_w,
                         "resultado_mb": round(size_mb, 3),
                         "estrategia_compartida": True,
                         "total_fragmentos": len(paths)},
                        archivos=[dst], fuente=src)
                    self._patch_gif_trailer(dst)
                    out_paths.append(dst)
                    log(f"✅ {src.name} → {dst.name} ({size_mb:.2f} MB)")
                except Exception as e:
                    log(f"❌ Error copiando {src.name}: {e}")
                    out_paths.append(None)
            return out_paths
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def optimize_gif_playback(self, gif_path: Path) -> Optional[Path]:
        """Normalize all GIF frame durations to a single average value (50–200 ms range).
        Eliminates jitter caused by inconsistent per-frame delays."""
        output_path = self._workspace_dir(gif_path, "optimizado") / f"{gif_path.stem}_optimized.gif"

        try:
            with Image.open(gif_path) as img:
                frames = []
                durations = []
                for frame in ImageSequence.Iterator(img):
                    frames.append(frame.copy())
                    durations.append(img.info.get('duration', 100))

            if not durations:
                return gif_path

            avg_duration = max(50, min(200, int(sum(durations) / len(durations))))  # clamp to 50–200 ms

            frames[0].save(
                output_path,
                save_all=True,
                append_images=frames[1:],
                duration=avg_duration,
                loop=0,
                optimize=False,
            )
            # Paso intermedio: no parchear trailer.
            return output_path
        except Exception as e:
            logger.error(f"Error optimizing playback: {e}")

