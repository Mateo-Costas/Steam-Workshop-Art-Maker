"""
quality_report.py - Sistema de reportes de calidad antes/después
"""

import logging
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import numpy as np
import cv2
from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
from io import BytesIO

logger = logging.getLogger("WorkshopArtPRO.quality_report")

class QualityReportSystem:
    """Sistema para generar reportes de calidad detallados"""
    
    def __init__(self, theme_colors):
        self.theme = theme_colors
        self.reports = []
        
    def create_quality_report(self, original_file: Path, processed_file: Path, 
                            processing_details: dict) -> dict:
        """Crear reporte completo de calidad"""
        
        try:
            logger.info("Generando reporte de calidad...")
            
            # Analizar archivo original
            original_metrics = self._analyze_image_quality(original_file)
            
            # Analizar archivo procesado
            processed_metrics = self._analyze_image_quality(processed_file)
            
            # Calcular mejoras
            improvements = self._calculate_improvements(original_metrics, processed_metrics)
            
            # Crear reporte
            report = {
                "timestamp": datetime.now(),
                "original_file": original_file,
                "processed_file": processed_file,
                "processing_details": processing_details,
                "original_metrics": original_metrics,
                "processed_metrics": processed_metrics,
                "improvements": improvements,
                "overall_score": self._calculate_overall_score(improvements),
                "recommendations": self._generate_recommendations(improvements)
            }
            
            self.reports.append(report)
            logger.info("Reporte de calidad generado")
            
            return report
            
        except Exception as e:
            logger.error("Error generando reporte: %s", e)
            return None
    
    def _analyze_image_quality(self, file_path: Path) -> dict:
        """Analizar métricas de calidad de una imagen"""
        try:
            metrics = {}
            
            # Información básica del archivo
            file_size = file_path.stat().st_size / (1024 * 1024)  # MB
            metrics["file_size_mb"] = file_size
            
            # Cargar imagen
            if file_path.suffix.lower() == '.gif':
                with Image.open(file_path) as img:
                    # Para GIF, analizar primer frame
                    first_frame = img.convert('RGB')
                    img_array = np.array(first_frame)
                    
                    # Información específica del GIF
                    metrics["frame_count"] = getattr(img, 'n_frames', 1)
                    metrics["duration_ms"] = img.info.get('duration', 100)
                    metrics["fps"] = 1000 / metrics["duration_ms"] if metrics["duration_ms"] > 0 else 10
            else:
                with Image.open(file_path) as img:
                    img_rgb = img.convert('RGB')
                    img_array = np.array(img_rgb)
                    metrics["frame_count"] = 1
                    metrics["fps"] = 0
            
            # Resolución
            h, w = img_array.shape[:2]
            metrics["resolution"] = (w, h)
            metrics["total_pixels"] = w * h
            
            # Análisis de calidad de imagen
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            
            # 1. Nitidez (usando varianza del Laplaciano)
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            sharpness = np.var(laplacian)
            metrics["sharpness"] = sharpness
            
            # 2. Contraste
            contrast = np.std(gray)
            metrics["contrast"] = contrast
            
            # 3. Brillo promedio
            brightness = np.mean(gray)
            metrics["brightness"] = brightness
            
            # 4. Saturación (en HSV)
            hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)
            saturation = np.mean(hsv[:, :, 1])
            metrics["saturation"] = saturation
            
            # 5. Detección de ruido
            # Aplicar filtro gaussiano y calcular diferencia
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            noise = np.mean(np.abs(gray.astype(float) - blurred.astype(float)))
            metrics["noise_level"] = noise
            
            # 6. Densidad de bordes (detalle)
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            metrics["edge_density"] = edge_density
            
            # 7. Diversidad de colores
            unique_colors = len(np.unique(img_array.reshape(-1, 3), axis=0))
            color_diversity = unique_colors / metrics["total_pixels"]
            metrics["color_diversity"] = color_diversity
            
            # 8. Histograma de distribución
            hist_r = cv2.calcHist([img_array], [0], None, [256], [0, 256])
            hist_g = cv2.calcHist([img_array], [1], None, [256], [0, 256])
            hist_b = cv2.calcHist([img_array], [2], None, [256], [0, 256])
            
            # Entropía del histograma (medida de información)
            def calculate_entropy(hist):
                hist_norm = hist.flatten() / np.sum(hist)
                hist_norm = hist_norm[hist_norm > 0]  # Evitar log(0)
                return -np.sum(hist_norm * np.log2(hist_norm))
            
            metrics["color_entropy"] = {
                "red": calculate_entropy(hist_r),
                "green": calculate_entropy(hist_g),
                "blue": calculate_entropy(hist_b)
            }
            
            # 9. Relación señal-ruido estimada
            signal_power = np.mean(gray ** 2)
            noise_power = noise ** 2
            snr = 10 * np.log10(signal_power / (noise_power + 1e-10))
            metrics["snr_db"] = snr
            
            # 10. Índice de calidad perceptual (simplificado)
            # Combinación ponderada de métricas
            quality_index = (
                (sharpness / 1000) * 0.3 +           # Nitidez normalizada
                (contrast / 128) * 0.2 +             # Contraste normalizado
                (edge_density * 10) * 0.2 +          # Detalle
                (saturation / 255) * 0.15 +          # Color
                (min(snr, 30) / 30) * 0.15           # SNR normalizado
            )
            metrics["quality_index"] = min(1.0, quality_index)
            
            return metrics
            
        except Exception as e:
            logger.warning("Error analizando calidad: %s", e)
            return {}
    
    def _calculate_improvements(self, original: dict, processed: dict) -> dict:
        """Calcular mejoras entre original y procesado"""
        improvements = {}
        
        try:
            # Mejoras en resolución
            orig_pixels = original.get("total_pixels", 1)
            proc_pixels = processed.get("total_pixels", 1)
            improvements["resolution_increase"] = proc_pixels / orig_pixels
            
            # Mejoras en nitidez
            orig_sharpness = original.get("sharpness", 0)
            proc_sharpness = processed.get("sharpness", 0)
            improvements["sharpness_improvement"] = (proc_sharpness - orig_sharpness) / (orig_sharpness + 1)
            
            # Mejoras en contraste
            orig_contrast = original.get("contrast", 1)
            proc_contrast = processed.get("contrast", 1)
            improvements["contrast_improvement"] = (proc_contrast - orig_contrast) / orig_contrast
            
            # Mejoras en saturación
            orig_saturation = original.get("saturation", 1)
            proc_saturation = processed.get("saturation", 1)
            improvements["saturation_improvement"] = (proc_saturation - orig_saturation) / orig_saturation
            
            # Reducción de ruido
            orig_noise = original.get("noise_level", 1)
            proc_noise = processed.get("noise_level", 1)
            improvements["noise_reduction"] = (orig_noise - proc_noise) / orig_noise
            
            # Mejora en detalle
            orig_edges = original.get("edge_density", 0)
            proc_edges = processed.get("edge_density", 0)
            improvements["detail_enhancement"] = (proc_edges - orig_edges) / (orig_edges + 0.01)
            
            # Mejora en calidad general
            orig_quality = original.get("quality_index", 0)
            proc_quality = processed.get("quality_index", 0)
            improvements["overall_quality_improvement"] = (proc_quality - orig_quality) / (orig_quality + 0.01)
            
            # Cambio en tamaño de archivo
            orig_size = original.get("file_size_mb", 1)
            proc_size = processed.get("file_size_mb", 1)
            improvements["file_size_change"] = (proc_size - orig_size) / orig_size
            
            return improvements
            
        except Exception as e:
            logger.warning("Error calculando mejoras: %s", e)
            return {}
    
    def _calculate_overall_score(self, improvements: dict) -> float:
        """Calcular puntuación general de mejora (0-100)"""
        try:
            # Pesos para diferentes aspectos
            weights = {
                "resolution_increase": 0.25,
                "sharpness_improvement": 0.20,
                "contrast_improvement": 0.15,
                "saturation_improvement": 0.10,
                "noise_reduction": 0.15,
                "detail_enhancement": 0.15
            }
            
            score = 0.0
            total_weight = 0.0
            
            for metric, weight in weights.items():
                if metric in improvements:
                    # Normalizar mejoras a 0-1
                    improvement = improvements[metric]
                    normalized = min(1.0, max(0.0, improvement + 0.5))  # Centrar en 0.5
                    score += normalized * weight
                    total_weight += weight
            
            if total_weight > 0:
                score = (score / total_weight) * 100
            
            return max(0, min(100, score))
            
        except Exception:
            return 50.0  # Score neutro si hay error
    
    def _generate_recommendations(self, improvements: dict) -> list:
        """Generar recomendaciones basadas en mejoras"""
        recommendations = []
        
        try:
            # Analizar cada métrica y generar recomendaciones
            if improvements.get("sharpness_improvement", 0) < 0.1:
                recommendations.append({
                    "type": "warning",
                    "title": "Nitidez limitada",
                    "message": "La nitidez podría mejorarse usando un modelo de IA más potente.",
                    "action": "Prueba con realesrgan-x4plus-anime para mayor detalle"
                })
            
            if improvements.get("contrast_improvement", 0) < 0.05:
                recommendations.append({
                    "type": "info",
                    "title": "Contraste conservativo",
                    "message": "El contraste se mantuvo similar al original.",
                    "action": "Ajusta los sliders de contraste si deseas más dramatismo"
                })
            
            if improvements.get("file_size_change", 0) > 2.0:
                recommendations.append({
                    "type": "warning",
                    "title": "Archivo muy grande",
                    "message": "El archivo creció significativamente.",
                    "action": "Considera optimizar para Steam Workshop (4.8MB máx por fragmento)"
                })
            
            if improvements.get("noise_reduction", 0) > 0.3:
                recommendations.append({
                    "type": "success",
                    "title": "Excelente reducción de ruido",
                    "message": "El procesamiento eliminó mucho ruido del original.",
                    "action": "¡Perfecto para contenido vintage como One Piece!"
                })
            
            if improvements.get("resolution_increase", 1) > 2.0:
                recommendations.append({
                    "type": "success",
                    "title": "Resolución mejorada",
                    "message": "La resolución se incrementó significativamente.",
                    "action": "Ideal para pantallas de alta resolución"
                })
            
            # Si no hay recomendaciones específicas, agregar una general
            if not recommendations:
                overall_score = self._calculate_overall_score(improvements)
                if overall_score > 70:
                    recommendations.append({
                        "type": "success",
                        "title": "Procesamiento exitoso",
                        "message": "El archivo ha sido mejorado satisfactoriamente.",
                        "action": "Listo para fragmentar y subir a Steam Workshop"
                    })
                else:
                    recommendations.append({
                        "type": "info",
                        "title": "Mejoras moderadas",
                        "message": "El procesamiento mantuvo la calidad original.",
                        "action": "Considera ajustar configuraciones para mayor mejora"
                    })
            
            return recommendations
            
        except Exception as e:
            logger.warning("Error generando recomendaciones: %s", e)
            return []
    
    def show_quality_report_window(self, report: dict, parent_window):
        """Mostrar ventana de reporte de calidad"""
        try:
            # Crear ventana del reporte
            report_window = tk.Toplevel(parent_window)
            report_window.title("📊 Reporte de Calidad - WorkshopArt PRO")
            report_window.geometry("900x700")
            report_window.configure(bg=self.theme["bg_primary"])
            
            # Hacer modal
            report_window.transient(parent_window)
            report_window.grab_set()
            
            # Frame principal con scroll
            main_frame = ttk.Frame(report_window, style="Modern.TFrame")
            main_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            # Header del reporte
            self._create_report_header(main_frame, report)
            
            # Notebook para organizar secciones
            notebook = ttk.Notebook(main_frame, style="Modern.TNotebook")
            notebook.pack(fill="both", expand=True, pady=(20, 0))
            
            # Tab 1: Comparación Visual
            visual_tab = ttk.Frame(notebook, style="Modern.TFrame")
            notebook.add(visual_tab, text="🖼️ Comparación Visual")
            self._create_visual_comparison(visual_tab, report)
            
            # Tab 2: Métricas Detalladas
            metrics_tab = ttk.Frame(notebook, style="Modern.TFrame")
            notebook.add(metrics_tab, text="📊 Métricas")
            self._create_metrics_tab(metrics_tab, report)
            
            # Tab 3: Recomendaciones
            recommendations_tab = ttk.Frame(notebook, style="Modern.TFrame")
            notebook.add(recommendations_tab, text="💡 Recomendaciones")
            self._create_recommendations_tab(recommendations_tab, report)
            
            # Botones de acción
            self._create_action_buttons(main_frame, report_window, report)
            
            # Centrar ventana
            report_window.update_idletasks()
            width = report_window.winfo_width()
            height = report_window.winfo_height()
            x = (report_window.winfo_screenwidth() // 2) - (width // 2)
            y = (report_window.winfo_screenheight() // 2) - (height // 2)
            report_window.geometry(f'{width}x{height}+{x}+{y}')
            
        except Exception as e:
            logger.error("Error mostrando reporte: %s", e)
    
    def _create_report_header(self, parent, report: dict):
        """Crear header del reporte"""
        header_frame = ttk.Frame(parent, style="Header.TFrame")
        header_frame.pack(fill="x", pady=(0, 20))
        
        # Título
        title = ttk.Label(header_frame, text="📊 Reporte de Calidad", style="Title.TLabel")
        title.pack(side="left")
        
        # Timestamp
        timestamp = report["timestamp"].strftime("%d/%m/%Y %H:%M:%S")
        time_label = ttk.Label(header_frame, text=f"Generado: {timestamp}", style="Caption.TLabel")
        time_label.pack(side="right")
        
        # Score general
        overall_score = report.get("overall_score", 50)
        score_color = "Success" if overall_score > 70 else "Warning" if overall_score > 40 else "Danger"
        
        score_frame = ttk.Frame(header_frame, style="Modern.TFrame")
        score_frame.pack(side="right", padx=(20, 0))
        
        ttk.Label(score_frame, text="Puntuación:", style="Body.TLabel").pack(side="left")
        ttk.Label(score_frame, text=f"{overall_score:.1f}/100", 
                 style=f"{score_color}.TLabel").pack(side="left", padx=(5, 0))
    
    def _create_visual_comparison(self, parent, report: dict):
        """Crear comparación visual lado a lado"""
        try:
            # Frame principal
            comparison_frame = ttk.Frame(parent, style="Modern.TFrame")
            comparison_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            # Frame para imágenes
            images_frame = ttk.Frame(comparison_frame, style="Modern.TFrame")
            images_frame.pack(fill="x", pady=(0, 20))
            
            # Cargar y mostrar imágenes
            original_path = report["original_file"]
            processed_path = report["processed_file"]
            
            # Frame original
            original_frame = ttk.LabelFrame(images_frame, text="📁 Original", 
                                          style="Modern.TLabelframe")
            original_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
            
            self._display_image_preview(original_frame, original_path, "original")
            
            # Frame procesado
            processed_frame = ttk.LabelFrame(images_frame, text="✨ Procesado", 
                                           style="Modern.TLabelframe")
            processed_frame.pack(side="right", fill="both", expand=True, padx=(10, 0))
            
            self._display_image_preview(processed_frame, processed_path, "processed")
            
            # Información de archivos
            self._create_file_info_comparison(comparison_frame, report)
            
        except Exception as e:
            logger.warning("Error en comparacion visual: %s", e)
    
    def _display_image_preview(self, parent, image_path: Path, label: str):
        """Mostrar preview de imagen"""
        try:
            # Cargar imagen
            with Image.open(image_path) as img:
                if img.format == 'GIF':
                    # Para GIF, mostrar primer frame
                    display_img = img.convert('RGB')
                else:
                    display_img = img.convert('RGB')
                
                # Redimensionar para preview
                max_size = (300, 200)
                display_img.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                # Convertir a PhotoImage
                photo = ImageTk.PhotoImage(display_img)
                
                # Mostrar en label
                img_label = ttk.Label(parent, image=photo)
                img_label.image = photo  # Mantener referencia
                img_label.pack(pady=10)
                
                # Info básica
                original_size = img.size
                file_size = image_path.stat().st_size / (1024 * 1024)
                
                info_text = f"{original_size[0]}x{original_size[1]} px\n{file_size:.2f} MB"
                
                if img.format == 'GIF':
                    frame_count = getattr(img, 'n_frames', 1)
                    duration = img.info.get('duration', 100)
                    fps = 1000 / duration if duration > 0 else 10
                    info_text += f"\n{frame_count} frames @ {fps:.1f} FPS"
                
                info_label = ttk.Label(parent, text=info_text, style="Caption.TLabel")
                info_label.pack()
                
        except Exception as e:
            error_label = ttk.Label(parent, text=f"Error cargando imagen:\n{e}", 
                                   style="Danger.TLabel")
            error_label.pack(pady=20)
    
    def _create_file_info_comparison(self, parent, report: dict):
        """Crear tabla de comparación de información de archivos"""
        info_frame = ttk.LabelFrame(parent, text="📋 Comparación Detallada", 
                                   style="Modern.TLabelframe")
        info_frame.pack(fill="x", pady=(20, 0))
        
        # Crear tabla
        columns = ("Métrica", "Original", "Procesado", "Mejora")
        tree = ttk.Treeview(info_frame, columns=columns, show="headings", height=8)
        
        # Configurar columnas
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=150, anchor="center")
        
        # Llenar datos
        original = report["original_metrics"]
        processed = report["processed_metrics"]
        improvements = report["improvements"]
        
        data_rows = [
            ("Resolución", 
             f"{original.get('resolution', (0,0))[0]}x{original.get('resolution', (0,0))[1]}", 
             f"{processed.get('resolution', (0,0))[0]}x{processed.get('resolution', (0,0))[1]}", 
             f"{improvements.get('resolution_increase', 1):.2f}x"),
            
            ("Tamaño archivo", 
             f"{original.get('file_size_mb', 0):.2f} MB", 
             f"{processed.get('file_size_mb', 0):.2f} MB", 
             f"{improvements.get('file_size_change', 0)*100:+.1f}%"),
            
            ("Nitidez", 
             f"{original.get('sharpness', 0):.0f}", 
             f"{processed.get('sharpness', 0):.0f}", 
             f"{improvements.get('sharpness_improvement', 0)*100:+.1f}%"),
            
            ("Contraste", 
             f"{original.get('contrast', 0):.1f}", 
             f"{processed.get('contrast', 0):.1f}", 
             f"{improvements.get('contrast_improvement', 0)*100:+.1f}%"),
            
            ("Saturación", 
             f"{original.get('saturation', 0):.0f}", 
             f"{processed.get('saturation', 0):.0f}", 
             f"{improvements.get('saturation_improvement', 0)*100:+.1f}%"),
            
            ("Nivel de ruido", 
             f"{original.get('noise_level', 0):.2f}", 
             f"{processed.get('noise_level', 0):.2f}", 
             f"{improvements.get('noise_reduction', 0)*100:+.1f}%"),
            
            ("Calidad general", 
             f"{original.get('quality_index', 0)*100:.1f}%", 
             f"{processed.get('quality_index', 0)*100:.1f}%", 
             f"{improvements.get('overall_quality_improvement', 0)*100:+.1f}%")
        ]
        
        for row in data_rows:
            tree.insert("", "end", values=row)
        
        tree.pack(fill="x", padx=10, pady=10)
    
    def _create_metrics_tab(self, parent, report: dict):
        """Crear tab de métricas detalladas"""
        # Crear gráficos de métricas
        self._create_metrics_charts(parent, report)
    
    def _create_metrics_charts(self, parent, report: dict):
        """Crear gráficos de métricas"""
        try:
            # Frame para gráficos
            charts_frame = ttk.Frame(parent, style="Modern.TFrame")
            charts_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            # Datos para gráficos
            original = report["original_metrics"]
            processed = report["processed_metrics"]
            
            # Gráfico de barras comparativo
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
            fig.patch.set_facecolor(self.theme["bg_primary"])
            
            # Configurar estilo oscuro
            plt.style.use('dark_background')
            
            # Gráfico 1: Métricas principales
            metrics = ['Nitidez', 'Contraste', 'Saturación', 'Detalle']
            original_values = [
                original.get('sharpness', 0) / 1000,  # Normalizar
                original.get('contrast', 0) / 128,
                original.get('saturation', 0) / 255,
                original.get('edge_density', 0) * 10
            ]
            processed_values = [
                processed.get('sharpness', 0) / 1000,
                processed.get('contrast', 0) / 128,
                processed.get('saturation', 0) / 255,
                processed.get('edge_density', 0) * 10
            ]
            
            x = np.arange(len(metrics))
            width = 0.35
            
            ax1.bar(x - width/2, original_values, width, label='Original', 
                   color=self.theme["accent_warning"], alpha=0.8)
            ax1.bar(x + width/2, processed_values, width, label='Procesado', 
                   color=self.theme["accent_success"], alpha=0.8)
            
            ax1.set_xlabel('Métricas')
            ax1.set_ylabel('Valor normalizado')
            ax1.set_title('Comparación de Calidad')
            ax1.set_xticks(x)
            ax1.set_xticklabels(metrics)
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # Gráfico 2: Mejoras porcentuales
            improvements = report["improvements"]
            improvement_metrics = ['Resolución', 'Nitidez', 'Contraste', 'Saturación', 'Detalle']
            improvement_values = [
                (improvements.get('resolution_increase', 1) - 1) * 100,
                improvements.get('sharpness_improvement', 0) * 100,
                improvements.get('contrast_improvement', 0) * 100,
                improvements.get('saturation_improvement', 0) * 100,
                improvements.get('detail_enhancement', 0) * 100
            ]
            
            colors = [self.theme["accent_success"] if v > 0 else self.theme["accent_danger"] 
                     for v in improvement_values]
            
            ax2.bar(improvement_metrics, improvement_values, color=colors, alpha=0.8)
            ax2.set_xlabel('Aspecto')
            ax2.set_ylabel('Mejora (%)')
            ax2.set_title('Mejoras Porcentuales')
            ax2.axhline(y=0, color='white', linestyle='-', alpha=0.5)
            ax2.grid(True, alpha=0.3)
            
            # Rotar labels si es necesario
            plt.setp(ax2.get_xticklabels(), rotation=45, ha='right')
            
            plt.tight_layout()
            
            # Convertir a imagen y mostrar
            buf = BytesIO()
            plt.savefig(buf, format='png', facecolor=self.theme["bg_primary"], 
                       edgecolor='none', bbox_inches='tight')
            buf.seek(0)
            
            # Cargar imagen en Tkinter
            with Image.open(buf) as pil_image:
                photo = ImageTk.PhotoImage(pil_image)
            
            chart_label = ttk.Label(charts_frame, image=photo)
            chart_label.image = photo  # Mantener referencia
            chart_label.pack()
            
            plt.close(fig)
            buf.close()
            
        except Exception as e:
            logger.warning("Error creando graficos: %s", e)
            error_label = ttk.Label(parent, text=f"Error generando gráficos: {e}", 
                                   style="Danger.TLabel")
            error_label.pack(pady=20)
    
    def _create_recommendations_tab(self, parent, report: dict):
        """Crear tab de recomendaciones"""
        recommendations_frame = ttk.Frame(parent, style="Modern.TFrame")
        recommendations_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        recommendations = report.get("recommendations", [])
        
        if not recommendations:
            no_rec_label = ttk.Label(recommendations_frame, 
                                    text="✅ No hay recomendaciones específicas.\nEl procesamiento fue óptimo.", 
                                    style="Success.TLabel")
            no_rec_label.pack(pady=50)
            return
        
        # Mostrar cada recomendación
        for i, rec in enumerate(recommendations):
            rec_frame = ttk.LabelFrame(recommendations_frame, 
                                      text=f"💡 {rec['title']}", 
                                      style="Modern.TLabelframe")
            rec_frame.pack(fill="x", pady=(0, 15))
            
            # Icono según tipo
            type_icons = {
                "success": "✅",
                "warning": "⚠️",
                "info": "ℹ️",
                "danger": "❌"
            }
            
            icon = type_icons.get(rec["type"], "💡")
            
            # Mensaje
            message_label = ttk.Label(rec_frame, 
                                     text=f"{icon} {rec['message']}", 
                                     style="Body.TLabel")
            message_label.pack(anchor="w", padx=15, pady=(10, 5))
            
            # Acción
            if rec.get("action"):
                action_label = ttk.Label(rec_frame, 
                                        text=f"👉 {rec['action']}", 
                                        style="Accent.TLabel")
                action_label.pack(anchor="w", padx=15, pady=(0, 10))
    
    def _create_action_buttons(self, parent, window, report: dict):
        """Crear botones de acción"""
        button_frame = ttk.Frame(parent, style="Modern.TFrame")
        button_frame.pack(fill="x", pady=(20, 0))
        
        # Botón exportar reporte
        export_btn = ttk.Button(button_frame, text="📄 Exportar Reporte", 
                               command=lambda: self._export_report(report),
                               style="Secondary.TButton")
        export_btn.pack(side="left")
        
        # Botón cerrar
        close_btn = ttk.Button(button_frame, text="❌ Cerrar", 
                              command=window.destroy,
                              style="Primary.TButton")
        close_btn.pack(side="right")
        
        # Botón procesar siguiente (si hay más archivos)
        continue_btn = ttk.Button(button_frame, text="➡️ Continuar Procesamiento", 
                                 command=window.destroy,
                                 style="Success.TButton")
        continue_btn.pack(side="right", padx=(0, 10))
    
    def _export_report(self, report: dict):
        """Exportar reporte a archivo"""
        try:
            # Crear archivo de texto con el reporte
            timestamp = report["timestamp"].strftime("%Y%m%d_%H%M%S")
            filename = f"quality_report_{timestamp}.txt"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("🎮 WORKSHOPART PRO - REPORTE DE CALIDAD\n")
                f.write("=" * 50 + "\n\n")
                
                f.write(f"📅 Fecha: {report['timestamp'].strftime('%d/%m/%Y %H:%M:%S')}\n")
                f.write(f"📁 Archivo original: {report['original_file'].name}\n")
                f.write(f"✨ Archivo procesado: {report['processed_file'].name}\n")
                f.write(f"🎯 Puntuación general: {report['overall_score']:.1f}/100\n\n")
                
                # Métricas
                f.write("📊 MÉTRICAS DETALLADAS\n")
                f.write("-" * 30 + "\n")
                
                original = report["original_metrics"]
                processed = report["processed_metrics"]
                improvements = report["improvements"]
                
                metrics_data = [
                    ("Resolución", original.get('resolution', (0,0)), processed.get('resolution', (0,0))),
                    ("Tamaño (MB)", f"{original.get('file_size_mb', 0):.2f}", f"{processed.get('file_size_mb', 0):.2f}"),
                    ("Nitidez", f"{original.get('sharpness', 0):.0f}", f"{processed.get('sharpness', 0):.0f}"),
                    ("Contraste", f"{original.get('contrast', 0):.1f}", f"{processed.get('contrast', 0):.1f}"),
                ]
                
                for metric, orig, proc in metrics_data:
                    f.write(f"{metric:15} | {str(orig):15} | {str(proc):15}\n")
                
                # Recomendaciones
                f.write("\n💡 RECOMENDACIONES\n")
                f.write("-" * 30 + "\n")
                
                for rec in report.get("recommendations", []):
                    f.write(f"• {rec['title']}: {rec['message']}\n")
                    if rec.get('action'):
                        f.write(f"  Acción: {rec['action']}\n")
                    f.write("\n")
            
            logger.info("Reporte exportado: %s", filename)
            
        except Exception as e:
            logger.error("Error exportando reporte: %s", e)