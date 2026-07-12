"""
analyzers.py - Computer-vision content analyzer for automatic AI model selection.

Inspects a GIF, image, or video and classifies it as one of:
  anime/vintage, anime/modern, gaming/mixed, realistic/photo, or mixed.

The classification drives which upscaling model is recommended (see ModelManager).
Uses OpenCV for edge detection, contour analysis, and color-space transforms,
and PIL/NumPy for frame sampling and score aggregation.

Detection pipeline (per frame):
  1. Anime character detection  — skin tones, unnatural hair colors, large circles (eyes)
  2. Anime color style           — uniform color blocks, limited palette, saturation range
  3. Anime line art              — Canny edge density, closed-contour ratio, line consistency
  4. Vintage vs modern quality   — resolution, JPEG blocking artifacts, saturation level
  5. Gaming UI detection         — rectangular contour count
  6. Realistic content           — natural noise levels, organic texture variance

Scores from 1–5 are weighted and combined into a final anime_score. If
anime_score > 0.3 the content is classified as anime; otherwise gaming or
realistic classifiers take over.
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple
import numpy as np
import cv2
from PIL import Image, ImageSequence

logger = logging.getLogger("WorkshopArtPRO.analyzers")


class ContentAnalyzer:
    """Static-method-only analyzer. No instance state; all methods are @staticmethod."""

    @staticmethod
    def analyze_content(file_path: Path) -> Dict[str, Any]:
        """Analyze a file and return a classification dict.

        For GIFs and videos, samples up to 5 frames and averages scores.
        Always appends 'aspect_ratio' and 'upload_suggestion' (Steam format hint).
        """
        results = {
            "type": "unknown",
            "characteristics": [],
            "recommended_model": "realesrgan-x4plus",
            "confidence": 0.0,
            "details": {},
            "anime_score": 0.0,
            "vintage_anime_score": 0.0,
            "modern_anime_score": 0.0,
            "gaming_score": 0.0,
            "realistic_score": 0.0,
            "aspect_ratio": None,
            "upload_suggestion": None,
        }

        _aw = _ah = 0
        try:
            logger.debug(f"Analizando: {file_path.name}")
            
            if file_path.suffix.lower() == '.gif':
                with Image.open(file_path) as img:
                    _aw, _ah = img.size
                    # Analizar múltiples frames
                    frames_to_analyze = min(5, getattr(img, 'n_frames', 1))
                    all_scores = []
                    
                    for i in range(frames_to_analyze):
                        try:
                            img.seek(i)
                            frame = img.convert('RGB')
                            frame_scores = ContentAnalyzer._analyze_image_adjusted(frame)
                            all_scores.append(frame_scores)
                        except Exception as e:
                            logger.debug(f"Frame {i} no analizable: {e}")
                            break
                    
                    if all_scores:
                        results = ContentAnalyzer._merge_frame_results_adjusted(all_scores)
                    else:
                        results.update(ContentAnalyzer._analyze_image_adjusted(img.convert('RGB')))
            
            elif file_path.suffix.lower() in ('.jpg', '.jpeg', '.png', '.bmp', '.webp'):
                with Image.open(file_path) as img:
                    _aw, _ah = img.size
                    frame = img.convert('RGB')
                    results = ContentAnalyzer._analyze_image_adjusted(frame)

            elif file_path.suffix.lower() in ('.mp4', '.avi', '.mov'):
                # Analizar video
                cap = cv2.VideoCapture(str(file_path))
                _aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                _ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                frames_analyzed = 0
                all_scores = []
                
                frame_interval = 30
                frame_count = 0
                
                while frames_analyzed < 3:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    if frame_count % frame_interval == 0:
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        pil_image = Image.fromarray(frame_rgb)
                        frame_scores = ContentAnalyzer._analyze_image_adjusted(pil_image)
                        all_scores.append(frame_scores)
                        frames_analyzed += 1
                    
                    frame_count += 1
                
                cap.release()
                
                if all_scores:
                    results = ContentAnalyzer._merge_frame_results_adjusted(all_scores)
                
        except Exception as e:
            logger.warning(f"Error analizando contenido: {e}")

        results.setdefault('aspect_ratio', None)
        results.setdefault('upload_suggestion', None)
        if _aw > 0 and _ah > 0:
            results['aspect_ratio'] = round(_aw / _ah, 3)
            results['upload_suggestion'] = ContentAnalyzer._get_upload_suggestion(_aw, _ah)

        logger.debug(
            "Analisis: anime=%.2f vintage=%.2f modern=%.2f gaming=%.2f realistic=%.2f "
            "tipo=%s confianza=%.0f%% modelo=%s",
            results['anime_score'], results['vintage_anime_score'],
            results['modern_anime_score'], results['gaming_score'],
            results['realistic_score'], results['type'],
            results['confidence'] * 100, results['recommended_model']
        )
        
        return results
    
    @staticmethod
    def _analyze_image_adjusted(img: Image.Image) -> Dict[str, Any]:
        """Run all CV detectors on a single PIL RGB image and combine into a score dict.

        Anime is given priority: if anime_score > 0.3 it overrides gaming/realistic
        regardless of their scores. This bias was calibrated for anime content like
        One Piece which has moderate saturation and aged compression artifacts.
        """
        results = {
            "type": "unknown",
            "characteristics": [],
            "recommended_model": "realesrgan-x4plus",
            "confidence": 0.0,
            "details": {},
            "anime_score": 0.0,
            "vintage_anime_score": 0.0,
            "modern_anime_score": 0.0,
            "gaming_score": 0.0,
            "realistic_score": 0.0
        }
        
        try:
            img_array = np.array(img)
            if img_array.ndim == 2:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_GRAY2RGB)
            elif img_array.shape[2] == 4:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)
            h, w, c = img_array.shape
            
            logger.debug("Analizando imagen: %dx%d", w, h)

            # =================================================================
            # INDICADORES DE ANIME EN GENERAL (MÁS PESO)
            # =================================================================

            general_anime_score = 0.0

            # 1. DETECCIÓN DE PERSONAJES ANIME (SÚPER IMPORTANTE)
            character_score = ContentAnalyzer._detect_anime_characters(img_array)
            general_anime_score += character_score * 0.4

            # 2. ESTILO DE COLORES ANIME (IMPORTANTE)
            anime_colors_score = ContentAnalyzer._detect_anime_color_style(img_array)
            general_anime_score += anime_colors_score * 0.3

            # 3. LÍNEAS Y CONTORNOS ANIME
            anime_lines_score = ContentAnalyzer._detect_anime_line_art(img_array)
            general_anime_score += anime_lines_score * 0.3

            logger.debug(
                "Scores: chars=%.3f colors=%.3f lines=%.3f",
                character_score, anime_colors_score, anime_lines_score
            )

            # =================================================================
            # VINTAGE VS MODERN (MENOR PESO EN LA DECISIÓN FINAL)
            # =================================================================

            # Vintage indicators (peso reducido)
            vintage_score = ContentAnalyzer._detect_vintage_quality(img_array) * 0.3

            # Modern indicators (peso reducido)
            modern_score = ContentAnalyzer._detect_modern_quality(img_array) * 0.3

            # =================================================================
            # GAMING Y REALISTIC (COMO ANTES)
            # =================================================================

            gaming_score = (
                ContentAnalyzer._detect_gaming_ui(img_array) * 0.5 +
                ContentAnalyzer._analyze_contrast_gaming(img_array) * 0.5
            )

            realistic_score = (
                ContentAnalyzer._analyze_natural_noise(img_array) * 0.5 +
                ContentAnalyzer._analyze_organic_textures(img_array) * 0.5
            )

            logger.debug("Gaming=%.3f realistic=%.3f vintage=%.3f modern=%.3f", gaming_score, realistic_score, vintage_score, modern_score)
            
            # =================================================================
            # LÓGICA DE DECISIÓN AJUSTADA
            # =================================================================
            
            # PRIORIDAD 1: ¿Es anime en general?
            is_anime = general_anime_score > 0.3  # Umbral bajo para capturar más anime
            
            # PRIORIDAD 2: Si es anime, ¿qué tipo?
            if is_anime:
                logger.debug("Anime detectado (score=%.3f)", general_anime_score)
                
                # Decidir vintage vs modern con lógica más flexible
                if vintage_score > modern_score or general_anime_score > 0.6:
                    # Si vintage gana O si es claramente anime, preferir vintage
                    content_type = "anime/vintage" 
                    model = "realesr-animevideov3-x4"  # MEJOR para anime clásico
                    characteristics = ["anime", "vintage_style", "one_piece_compatible"]
                    final_confidence = general_anime_score * 1.2  # Boost
                else:
                    content_type = "anime/modern"
                    model = "realesrgan-x4plus-anime" 
                    characteristics = ["anime", "modern_style"]
                    final_confidence = general_anime_score
                
                # Si la confianza es muy alta, forzar vintage (para One Piece)
                if general_anime_score > 0.5:
                    content_type = "anime/vintage"
                    model = "realesr-animevideov3-x4"
                    final_confidence = min(1.0, general_anime_score * 1.3)
                    logger.debug("Forzando anime/vintage por alta confianza")
            
            else:
                # No es anime claramente
                if gaming_score > 0.5:
                    content_type = "gaming/mixed"
                    model = "realesrgan-x4plus"
                    characteristics = ["gaming"]
                    final_confidence = gaming_score
                elif realistic_score > 0.5:
                    content_type = "realistic/photo"
                    model = "realesrnet-x4plus"
                    characteristics = ["realistic"]
                    final_confidence = realistic_score
                else:
                    # FALLBACK ESPECIAL: Si nada es claro pero hay indicios de anime, forzar anime/vintage
                    if general_anime_score > 0.15:  # Umbral muy bajo
                        content_type = "anime/vintage_uncertain"
                        model = "realesr-animevideov3-x4"  # Mejor apuesta para anime
                        characteristics = ["possible_anime", "vintage_fallback"]
                        final_confidence = 0.7  # Confianza moderada
                        logger.debug("Fallback a anime/vintage (score=%.3f)", general_anime_score)
                    else:
                        content_type = "mixed"
                        model = "realesrgan-x4plus"
                        characteristics = ["mixed_content"]
                        final_confidence = 0.5
            
            results.update({
                "type": content_type,
                "characteristics": characteristics,
                "recommended_model": model,
                "confidence": min(1.0, final_confidence),
                "anime_score": general_anime_score,
                "vintage_anime_score": vintage_score,
                "modern_anime_score": modern_score,
                "gaming_score": gaming_score,
                "realistic_score": realistic_score,
                "details": {
                    "general_anime_score": general_anime_score,
                    "character_score": character_score,
                    "anime_colors_score": anime_colors_score,
                    "anime_lines_score": anime_lines_score,
                    "vintage_vs_modern": f"{vintage_score:.3f} vs {modern_score:.3f}",
                    "decision_logic": "anime_first_priority",
                    "resolution": f"{w}x{h}"
                }
            })
            
        except Exception as e:
            logger.warning("Error en análisis de imagen: %s", e)
        
        return results
    
    # =================================================================
    # FUNCIONES ESPECÍFICAS AJUSTADAS
    # =================================================================
    
    @staticmethod
    def _detect_anime_characters(img_array: np.ndarray) -> float:
        """Score 0–1 based on anime character indicators: skin tones, unnatural hair colors, large eye-circles."""
        try:
            h, w = img_array.shape[:2]
            anime_character_score = 0.0
            
            # 1. COLORES DE PIEL ANIME (muy característico)
            hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)
            
            # Rangos de colores de piel típicos en anime
            skin_ranges = [
                ((0, 30, 100), (25, 180, 255)),    # Piel normal
                ((25, 20, 120), (35, 150, 255)),   # Piel más clara
                ((0, 10, 150), (15, 100, 255))     # Piel muy clara (anime)
            ]
            
            total_skin_pixels = 0
            for lower, upper in skin_ranges:
                mask = cv2.inRange(hsv, lower, upper)
                total_skin_pixels += np.sum(mask > 0)
            
            skin_ratio = total_skin_pixels / (h * w)
            anime_character_score += min(0.4, skin_ratio * 8)  # Normalizar
            
            # 2. COLORES DE CABELLO NO NATURALES (MUY típico de anime)
            unnatural_hair = 0
            
            # Azules, verdes, rosas, púrpuras
            hair_ranges = [
                ((90, 50, 50), (130, 255, 255)),   # Azul/Verde
                ((130, 50, 50), (170, 255, 255)),  # Rosa/Púrpura
                ((40, 50, 50), (80, 255, 255))     # Amarillo brillante
            ]
            
            for lower, upper in hair_ranges:
                mask = cv2.inRange(hsv, lower, upper)
                unnatural_hair += np.sum(mask > 0)
            
            hair_ratio = unnatural_hair / (h * w)
            anime_character_score += min(0.3, hair_ratio * 15)
            
            # 3. OJOS GRANDES (detectar círculos/elipses grandes)
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            
            # Detectar círculos que podrían ser ojos
            circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1, minDist=20,
                                     param1=50, param2=30, minRadius=8, maxRadius=40)
            
            if circles is not None:
                # Filtrar círculos grandes (posibles ojos anime)
                large_circles = [c for c in circles[0] if c[2] > 12]
                eye_score = min(0.3, len(large_circles) / 8)
                anime_character_score += eye_score
            
            return min(1.0, anime_character_score)
            
        except Exception as e:
            logger.debug("Error detectando personajes: %s", e)
            return 0.0
    
    @staticmethod
    def _detect_anime_color_style(img_array: np.ndarray) -> float:
        """Score 0–1 based on anime color style: flat color blocks, limited palette, moderate saturation."""
        try:
            hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)
            h, s, v = cv2.split(hsv)
            
            color_style_score = 0.0
            
            # 1. ÁREAS DE COLOR UNIFORME (anime usa bloques de color)
            # Calcular varianza en pequeñas regiones
            h_img, w_img = h.shape
            block_size = 16
            uniform_blocks = 0
            total_blocks = 0
            
            for i in range(0, h_img - block_size, block_size):
                for j in range(0, w_img - block_size, block_size):
                    block = img_array[i:i+block_size, j:j+block_size]
                    variance = np.var(block)
                    
                    if variance < 400:  # Bloque muy uniforme
                        uniform_blocks += 1
                    total_blocks += 1
            
            if total_blocks > 0:
                uniformity = uniform_blocks / total_blocks
                color_style_score += min(0.4, uniformity * 2)
            
            # 2. PALETA LIMITADA (anime usa menos colores únicos)
            # Subsample pixels before np.unique: on large frames (1080p+) the full
            # unique-count is O(n log n) over millions of rows and dominates the
            # whole analysis. The unique/total ratio is stable under subsampling.
            step = max(1, int((img_array.shape[0] * img_array.shape[1] / 65536) ** 0.5))
            data = img_array[::step, ::step].reshape((-1, 3))
            unique_colors = len(np.unique(data, axis=0))
            total_pixels = data.shape[0]
            
            color_reduction = 1.0 - (unique_colors / total_pixels)
            color_style_score += color_reduction * 0.3
            
            # 3. SATURACIÓN MODERADA-ALTA (típica del anime)
            mean_saturation = np.mean(s) / 255.0
            if 0.3 < mean_saturation < 0.8:  # Rango típico anime
                color_style_score += 0.3
            
            return min(1.0, color_style_score)
            
        except Exception as e:
            logger.debug("Error en estilo de colores: %s", e)
            return 0.0
    
    @staticmethod
    def _detect_anime_line_art(img_array: np.ndarray) -> float:
        """Score 0–1 based on Canny edge density, closed-contour ratio, and line thickness consistency."""
        try:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            
            line_art_score = 0.0
            
            # 1. CONTORNOS DEFINIDOS
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            
            # Anime tiene densidad de bordes moderada (no demasiado, no muy poco)
            if 0.05 < edge_density < 0.25:
                line_art_score += 0.4
            
            # 2. LÍNEAS CONTINUAS (contornos cerrados)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            closed_contours = 0
            significant_contours = 0
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 100:  # Solo contornos significativos
                    significant_contours += 1
                    
                    # Verificar si está "cerrado" (típico de anime)
                    perimeter = cv2.arcLength(contour, True)
                    if perimeter > 50:
                        # Calcular "solidez" del contorno
                        hull = cv2.convexHull(contour)
                        hull_area = cv2.contourArea(hull)
                        if hull_area > 0:
                            solidity = area / hull_area
                            if solidity > 0.7:  # Contorno sólido
                                closed_contours += 1
            
            if significant_contours > 0:
                closure_ratio = closed_contours / significant_contours
                line_art_score += closure_ratio * 0.4
            
            # 3. CONSISTENCIA EN GROSOR DE LÍNEAS
            # Usar transformada de distancia
            if np.sum(edges) > 0:
                dist_transform = cv2.distanceTransform(255 - edges, cv2.DIST_L2, 5)
                line_pixels = edges > 0
                
                if np.sum(line_pixels) > 100:
                    thickness_values = dist_transform[line_pixels]
                    thickness_std = np.std(thickness_values)
                    
                    # Líneas consistentes = bajo std
                    consistency = max(0, 1.0 - (thickness_std / 5))
                    line_art_score += consistency * 0.2
            
            return min(1.0, line_art_score)
            
        except Exception as e:
            logger.debug("Error en líneas anime: %s", e)
            return 0.0
    
    @staticmethod
    def _detect_vintage_quality(img_array: np.ndarray) -> float:
        """Score 0–1 for vintage indicators: low resolution, 8x8 DCT blocking artifacts, muted saturation."""
        try:
            h, w = img_array.shape[:2]
            vintage_score = 0.0
            
            # 1. Resolución relativamente baja
            total_pixels = h * w
            if total_pixels < 640 * 480:
                vintage_score += 0.5
            elif total_pixels < 1024 * 768:
                vintage_score += 0.3
            
            # 2. Compresión/artifacts
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            
            # Detectar blocking (típico de codecs viejos)
            # Dividir en bloques 8x8 y analizar uniformidad
            block_variances = []
            for i in range(0, h-8, 8):
                for j in range(0, w-8, 8):
                    block = gray[i:i+8, j:j+8]
                    block_variances.append(np.var(block))
            
            if block_variances:
                avg_variance = np.mean(block_variances)
                # Baja varianza = bloques uniformes = compresión
                if avg_variance < 50:
                    vintage_score += 0.3
            
            # 3. Colores menos saturados
            hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)
            mean_saturation = np.mean(hsv[:, :, 1]) / 255.0
            
            if mean_saturation < 0.6:  # Saturación moderada
                vintage_score += 0.2
            
            return min(1.0, vintage_score)
            
        except Exception:
            return 0.0
    
    @staticmethod
    def _detect_modern_quality(img_array: np.ndarray) -> float:
        """Score 0–1 for modern indicators: high resolution, sharp Canny edges, high saturation."""
        try:
            h, w = img_array.shape[:2]
            modern_score = 0.0
            
            # 1. Resolución alta
            total_pixels = h * w
            if total_pixels > 1920 * 1080:
                modern_score += 0.5
            elif total_pixels > 1280 * 720:
                modern_score += 0.3
            
            # 2. Bordes muy definidos (HD)
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 100, 200)
            sharp_edge_density = np.sum(edges > 0) / edges.size
            
            if sharp_edge_density > 0.15:
                modern_score += 0.3
            
            # 3. Saturación muy alta (digital)
            hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)
            high_saturation = np.sum(hsv[:, :, 1] > 200) / hsv[:, :, 1].size
            
            if high_saturation > 0.3:
                modern_score += 0.2
            
            return min(1.0, modern_score)
            
        except Exception:
            return 0.0
    
    # =================================================================
    # FUNCIONES HEREDADAS (simplificadas)
    # =================================================================
    
    @staticmethod
    def _detect_gaming_ui(img_array: np.ndarray) -> float:
        """Score 0–1 based on rectangular contour count — gaming UIs typically contain many rect elements."""
        try:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            rectangles = 0
            for contour in contours:
                if cv2.contourArea(contour) > 500:
                    perimeter = cv2.arcLength(contour, True)
                    approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
                    if len(approx) == 4:
                        rectangles += 1
            
            return min(1.0, rectangles / 20)
        except Exception:
            return 0.0
    
    @staticmethod
    def _analyze_contrast_gaming(img_array: np.ndarray) -> float:
        """Score 0–1 based on grayscale std-dev; gaming screenshots tend to have high contrast."""
        try:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            return min(1.0, np.std(gray) / 128.0 * 1.5)
        except Exception:
            return 0.0
    
    @staticmethod
    def _analyze_natural_noise(img_array: np.ndarray) -> float:
        """Score 0–1 for natural photographic noise (difference between raw and Gaussian-blurred)."""
        try:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            noise_level = np.mean(np.abs(gray.astype(float) - blurred.astype(float))) / 255.0
            
            if 0.01 < noise_level < 0.1:
                return min(1.0, noise_level * 10)
            else:
                return max(0.0, 1.0 - abs(noise_level - 0.05) * 20)
        except Exception:
            return 0.0
    
    @staticmethod
    def _analyze_organic_textures(img_array: np.ndarray) -> float:
        """Score 0–1 for organic texture variance (variance of residuals after mean filter)."""
        try:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            kernel = np.ones((3,3), np.float32) / 9
            smoothed = cv2.filter2D(gray, -1, kernel)
            texture_variance = np.var(gray - smoothed)
            return min(1.0, texture_variance / 1000.0)
        except Exception:
            return 0.0
    
    @staticmethod
    def _merge_frame_results_adjusted(all_scores: List[Dict]) -> Dict[str, Any]:
        """Average per-frame scores and apply the same anime-priority decision logic as _analyze_image_adjusted."""
        if not all_scores:
            return {}
        
        # Promediar puntuaciones
        merged = {
            "anime_score": np.mean([s.get("anime_score", 0) for s in all_scores]),
            "vintage_anime_score": np.mean([s.get("vintage_anime_score", 0) for s in all_scores]),
            "modern_anime_score": np.mean([s.get("modern_anime_score", 0) for s in all_scores]),
            "gaming_score": np.mean([s.get("gaming_score", 0) for s in all_scores]),
            "realistic_score": np.mean([s.get("realistic_score", 0) for s in all_scores])
        }
        
        logger.debug("Fusión de %d frames: anime=%.3f", len(all_scores), merged['anime_score'])

        # LÓGICA AJUSTADA: Priorizar anime por encima de todo
        if merged["anime_score"] > 0.3:  # Umbral bajo para capturar anime
            if merged["anime_score"] > 0.6:  # Alta confianza = vintage
                content_type = "anime/vintage"
                model = "realesr-animevideov3-x4"
                confidence = merged["anime_score"] * 1.2
                logger.debug("Alta confianza -> anime/vintage")
            elif merged["vintage_anime_score"] >= merged["modern_anime_score"]:
                content_type = "anime/vintage"
                model = "realesr-animevideov3-x4"
                confidence = merged["anime_score"] * 1.1
                logger.debug("Vintage gana -> anime/vintage")
            else:
                content_type = "anime/modern"
                model = "realesrgan-x4plus-anime"
                confidence = merged["anime_score"]
                logger.debug("Modern gana -> anime/modern")
        else:
            # Fallback normal
            if merged["gaming_score"] > 0.5:
                content_type = "gaming/mixed"
                model = "realesrgan-x4plus"
                confidence = merged["gaming_score"]
            elif merged["realistic_score"] > 0.5:
                content_type = "realistic/photo"
                model = "realesrnet-x4plus"
                confidence = merged["realistic_score"]
            else:
                content_type = "anime/vintage_fallback"  # ¡Fallback a anime!
                model = "realesr-animevideov3-x4"
                confidence = 0.7
                logger.debug("Fallback -> anime/vintage")
        
        merged.update({
            "type": content_type,
            "recommended_model": model,
            "confidence": min(1.0, confidence),
            "characteristics": [content_type.replace("/", "_")],
            "details": {
                "frames_analyzed": len(all_scores),
                "analysis_method": "anime_priority_adjusted"
            }
        })
        
        return merged
    
    @staticmethod
    def _get_upload_suggestion(w: int, h: int) -> str:
        """Map image dimensions to the recommended Steam Workshop display format.

        Thresholds are based on Steam's actual aspect-ratio ranges:
        >= 3.5  → Workshop Showcase (5-part banner 638x354)
        >= 1.5  → Screenshot Showcase
        >= 0.8  → Artwork Showcase (main 506px + side 100px)
        < 0.8   → Artwork Showcase or Profile Background
        """
        if h <= 0:
            return "Artwork Showcase"
        ratio = w / h
        if ratio >= 3.5:
            return "Workshop Showcase (5 partes 638x354)"
        elif ratio >= 1.5:
            return "Screenshot Showcase (638x354)"
        elif ratio >= 0.8:
            return "Artwork Showcase (main 506px + side 100px)"
        else:
            return "Artwork Showcase o Perfil Background"

    @staticmethod
    def get_content_description(content_type: str) -> str:
        """Descripciones ajustadas"""
        descriptions = {
            "anime/vintage": "Anime Vintage — One Piece, Dragon Ball (mejor: realesr-animevideov3-x4)",
            "anime/modern": "Anime Moderno — HD con colores digitales vibrantes",
            "anime/vintage_uncertain": "Posible Anime Vintage — amplía análisis para confirmar",
            "anime/vintage_fallback": "Anime Vintage (fallback) — mejor apuesta para anime incierto",
            "gaming/mixed": "Gaming — capturas de videojuegos, UI/HUD visible",
            "realistic/photo": "Realista/Foto — fotografía o render 3D fotorrealista",
            "mixed": "Mixto — contenido variado sin tipo dominante",
        }
        return descriptions.get(content_type, "Tipo desconocido")