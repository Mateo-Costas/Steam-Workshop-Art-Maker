"""
fragment_preview.py - Sistema de preview de fragmentos para Steam Workshop
"""

import logging
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageTk, ImageDraw, ImageFont
import numpy as np

logger = logging.getLogger("WorkshopArtPRO.fragment_preview")

class FragmentPreviewSystem:
    """Sistema para previsualizar fragmentos antes de Steam Workshop"""
    
    def __init__(self, theme_colors):
        self.theme = theme_colors
        self.preview_window = None
        self.fragments = []
        
    def create_fragment_preview(self, gif_path: Path, parent_window):
        """Crear preview de cómo se verá fragmentado el GIF"""
        try:
            logger.info("Generando preview de fragmentos...")
            
            # Crear ventana de preview
            self.preview_window = tk.Toplevel(parent_window)
            self.preview_window.title("👁️ Preview de Fragmentos - Steam Workshop")
            self.preview_window.geometry("1000x700")
            self.preview_window.configure(bg=self.theme["bg_primary"])
            
            # Hacer modal
            self.preview_window.transient(parent_window)
            self.preview_window.grab_set()
            
            # Frame principal
            main_frame = ttk.Frame(self.preview_window, style="Modern.TFrame")
            main_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            # Header
            self._create_preview_header(main_frame, gif_path)
            
            # Análisis del GIF
            gif_analysis = self._analyze_gif_for_fragments(gif_path)
            
            # Preview de fragmentos
            self._create_fragments_preview(main_frame, gif_path, gif_analysis)
            
            # Información detallada
            self._create_fragment_details(main_frame, gif_analysis)
            
            # Botones de acción
            self._create_preview_action_buttons(main_frame, gif_path)
            
            # Centrar ventana
            self.preview_window.update_idletasks()
            width = self.preview_window.winfo_width()
            height = self.preview_window.winfo_height()
            x = (self.preview_window.winfo_screenwidth() // 2) - (width // 2)
            y = (self.preview_window.winfo_screenheight() // 2) - (height // 2)
            self.preview_window.geometry(f'{width}x{height}+{x}+{y}')
            
            logger.info("Preview de fragmentos creado")
            
        except Exception as e:
            logger.error("Error creando preview: %s", e)
    
    def _create_preview_header(self, parent, gif_path: Path):
        """Crear header del preview"""
        header_frame = ttk.Frame(parent, style="Header.TFrame")
        header_frame.pack(fill="x", pady=(0, 20))
        
        # Título
        title = ttk.Label(header_frame, text="👁️ Preview de Fragmentos", style="Title.TLabel")
        title.pack(side="left")
        
        # Nombre del archivo
        filename = ttk.Label(header_frame, text=f"📁 {gif_path.name}", style="Body.TLabel")
        filename.pack(side="left", padx=(20, 0))
        
        # Información Steam Workshop
        steam_info = ttk.Label(header_frame, text="🎮 Para Steam Workshop", style="Accent.TLabel")
        steam_info.pack(side="right")
    
    def _analyze_gif_for_fragments(self, gif_path: Path) -> dict:
        """Analizar GIF para determinar cómo se verá fragmentado"""
        try:
            analysis = {}
            
            with Image.open(gif_path) as img:
                # Información básica
                analysis["original_size"] = img.size
                analysis["frame_count"] = getattr(img, 'n_frames', 1)
                analysis["duration"] = img.info.get('duration', 100)
                analysis["fps"] = 1000 / analysis["duration"] if analysis["duration"] > 0 else 10
                
                # Verificar si cumple dimensiones Steam
                expected_width = 638
                expected_height = 354
                analysis["steam_compliant"] = img.size == (expected_width, expected_height)
                analysis["target_dimensions"] = (expected_width, expected_height)
                
                # Calcular dimensiones de fragmentos
                fragment_width = expected_width // 5
                analysis["fragment_dimensions"] = (fragment_width, expected_height)
                
                # Analizar contenido de cada fragmento
                first_frame = img.convert('RGB')
                analysis["fragments"] = self._analyze_fragment_content(first_frame, fragment_width, expected_height)
                
                # Estimar tamaños de archivo
                file_size_mb = gif_path.stat().st_size / (1024 * 1024)
                estimated_fragment_size = file_size_mb / 5
                analysis["estimated_fragment_size"] = estimated_fragment_size
                
                # Verificar compatibilidad con Steam Workshop
                min_size = 4.2  # MB
                max_size = 4.8  # MB
                analysis["size_warnings"] = []
                
                if estimated_fragment_size < min_size:
                    analysis["size_warnings"].append(f"Fragmentos muy pequeños ({estimated_fragment_size:.2f} MB < {min_size} MB)")
                elif estimated_fragment_size > max_size:
                    analysis["size_warnings"].append(f"Fragmentos muy grandes ({estimated_fragment_size:.2f} MB > {max_size} MB)")
                
                return analysis
                
        except Exception as e:
            logger.warning("Error analizando GIF: %s", e)
            return {}
    
    def _analyze_fragment_content(self, image: Image.Image, fragment_width: int, height: int) -> list:
        """Analizar el contenido de cada fragmento"""
        fragments = []
        img_array = np.array(image)
        
        for i in range(5):
            left = i * fragment_width
            right = min(left + fragment_width, image.width)
            
            # Extraer región del fragmento
            fragment_region = img_array[:, left:right]
            
            # Analizar contenido
            fragment_analysis = {
                "index": i + 1,
                "position": (left, 0, right, height),
                "dimensions": (right - left, height),
                "has_content": self._has_meaningful_content(fragment_region),
                "complexity": self._calculate_visual_complexity(fragment_region),
                "dominant_colors": self._get_dominant_colors(fragment_region),
                "estimated_quality": self._estimate_fragment_quality(fragment_region)
            }
            
            fragments.append(fragment_analysis)
        
        return fragments
    
    def _has_meaningful_content(self, region: np.ndarray) -> bool:
        """Verificar si el fragmento tiene contenido significativo"""
        try:
            # Calcular varianza para detectar contenido
            gray = np.mean(region, axis=2)
            variance = np.var(gray)
            
            # Si la varianza es muy baja, probablemente es fondo uniforme
            return variance > 100
            
        except Exception:
            return True
    
    def _calculate_visual_complexity(self, region: np.ndarray) -> float:
        """Calcular complejidad visual del fragmento (0-1)"""
        try:
            import cv2
            
            gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
            
            # Detectar bordes
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            
            # Calcular varianza de color
            color_variance = np.var(region)
            
            # Combinar métricas
            complexity = (edge_density * 2 + color_variance / 10000) / 3
            return min(1.0, complexity)
            
        except Exception:
            return 0.5
    
    def _get_dominant_colors(self, region: np.ndarray) -> list:
        """Obtener colores dominantes del fragmento"""
        try:
            # Simplificar usando clustering básico
            pixels = region.reshape(-1, 3)
            
            # Tomar muestra para eficiencia
            if len(pixels) > 1000:
                indices = np.random.choice(len(pixels), 1000, replace=False)
                pixels = pixels[indices]
            
            # Encontrar colores únicos más frecuentes
            unique_colors, counts = np.unique(pixels, axis=0, return_counts=True)
            
            # Ordenar por frecuencia
            sorted_indices = np.argsort(counts)[::-1]
            
            # Devolver top 3 colores en formato hex
            top_colors = []
            for i in range(min(3, len(unique_colors))):
                color = unique_colors[sorted_indices[i]]
                hex_color = f'#{color[0]:02x}{color[1]:02x}{color[2]:02x}'
                top_colors.append(hex_color)
            
            return top_colors
            
        except Exception:
            return ['#888888']
    
    def _estimate_fragment_quality(self, region: np.ndarray) -> str:
        """Estimar calidad del fragmento"""
        try:
            complexity = self._calculate_visual_complexity(region)
            has_content = self._has_meaningful_content(region)
            
            if not has_content:
                return "Bajo (poco contenido)"
            elif complexity > 0.7:
                return "Alto (muy detallado)"
            elif complexity > 0.4:
                return "Medio (buen balance)"
            else:
                return "Básico (simple)"
                
        except Exception:
            return "Desconocido"
    
    def _create_fragments_preview(self, parent, gif_path: Path, analysis: dict):
        """Crear preview visual de los fragmentos"""
        try:
            # Frame para el preview
            preview_frame = ttk.LabelFrame(parent, text="🖼️ Vista Previa de Fragmentos", 
                                         style="Modern.TLabelframe")
            preview_frame.pack(fill="x", pady=(0, 20))
            
            # Cargar imagen original
            with Image.open(gif_path) as img:
                if img.format == 'GIF':
                    display_img = img.convert('RGB')
                else:
                    display_img = img.convert('RGB')
                
                # Redimensionar para mostrar
                display_width = 800
                aspect_ratio = display_img.height / display_img.width
                display_height = int(display_width * aspect_ratio)
                
                display_img = display_img.resize((display_width, display_height), Image.Resampling.LANCZOS)
                
                # Dibujar líneas de división
                draw = ImageDraw.Draw(display_img)
                fragment_width = display_width // 5
                
                # Líneas de división
                for i in range(1, 5):
                    x = i * fragment_width
                    draw.line([(x, 0), (x, display_height)], fill='red', width=3)
                
                # Números de fragmentos
                try:
                    font = ImageFont.truetype("arial.ttf", 24)
                except Exception:
                    font = ImageFont.load_default()
                
                for i in range(5):
                    x_center = (i * fragment_width) + (fragment_width // 2)
                    y_center = display_height // 2
                    
                    # Fondo para el número
                    bbox = draw.textbbox((x_center, y_center), str(i + 1), font=font)
                    draw.rectangle(bbox, fill='black', outline='white', width=2)
                    draw.text((x_center, y_center), str(i + 1), fill='white', font=font, anchor='mm')
                
                # Convertir a PhotoImage
                photo = ImageTk.PhotoImage(display_img)
                
                # Mostrar imagen
                img_label = ttk.Label(preview_frame, image=photo)
                img_label.image = photo  # Mantener referencia
                img_label.pack(pady=15)
                
                # Leyenda
                legend_text = "🔴 Líneas rojas: Puntos de división | 🔢 Números: Fragmentos individuales"
                legend_label = ttk.Label(preview_frame, text=legend_text, style="Caption.TLabel")
                legend_label.pack()
                
        except Exception as e:
            logger.warning("Error creando preview visual: %s", e)
            error_label = ttk.Label(preview_frame, text=f"Error generando preview: {e}", 
                                   style="Danger.TLabel")
            error_label.pack(pady=20)
    
    def _create_fragment_details(self, parent, analysis: dict):
        """Crear tabla detallada de fragmentos"""
        details_frame = ttk.LabelFrame(parent, text="📊 Análisis Detallado de Fragmentos", 
                                      style="Modern.TLabelframe")
        details_frame.pack(fill="both", expand=True, pady=(0, 20))
        
        # Información general
        info_frame = ttk.Frame(details_frame, style="Modern.TFrame")
        info_frame.pack(fill="x", padx=15, pady=10)
        
        # Grid de información
        info_grid = ttk.Frame(info_frame, style="Modern.TFrame")
        info_grid.pack(fill="x")
        
        # Columna izquierda
        left_col = ttk.Frame(info_grid, style="Modern.TFrame")
        left_col.pack(side="left", fill="x", expand=True)
        
        ttk.Label(left_col, text=f"📐 Dimensiones originales: {analysis.get('original_size', 'N/A')}", 
                 style="Body.TLabel").pack(anchor="w")
        ttk.Label(left_col, text=f"🎯 Dimensiones objetivo: {analysis.get('target_dimensions', 'N/A')}", 
                 style="Body.TLabel").pack(anchor="w")
        ttk.Label(left_col, text=f"✂️ Tamaño por fragmento: {analysis.get('fragment_dimensions', 'N/A')}", 
                 style="Body.TLabel").pack(anchor="w")
        
        # Columna derecha
        right_col = ttk.Frame(info_grid, style="Modern.TFrame")
        right_col.pack(side="right", fill="x", expand=True)
        
        ttk.Label(right_col, text=f"🎞️ Frames: {analysis.get('frame_count', 'N/A')}", 
                 style="Body.TLabel").pack(anchor="w")
        ttk.Label(right_col, text=f"⚡ FPS: {analysis.get('fps', 0):.1f}", 
                 style="Body.TLabel").pack(anchor="w")
        ttk.Label(right_col, text=f"💾 Tamaño estimado/fragmento: {analysis.get('estimated_fragment_size', 0):.2f} MB", 
                 style="Body.TLabel").pack(anchor="w")
        
        # Advertencias si las hay
        warnings = analysis.get('size_warnings', [])
        if warnings:
            warning_frame = ttk.Frame(details_frame, style="Modern.TFrame")
            warning_frame.pack(fill="x", padx=15, pady=(10, 0))
            
            ttk.Label(warning_frame, text="⚠️ Advertencias:", style="Warning.TLabel").pack(anchor="w")
            for warning in warnings:
                ttk.Label(warning_frame, text=f"  • {warning}", style="Caption.TLabel").pack(anchor="w")
        
        # Tabla de fragmentos
        if 'fragments' in analysis:
            self._create_fragments_table(details_frame, analysis['fragments'])
    
    def _create_fragments_table(self, parent, fragments: list):
        """Crear tabla con detalles de cada fragmento"""
        table_frame = ttk.Frame(parent, style="Modern.TFrame")
        table_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Crear Treeview
        columns = ("Fragmento", "Dimensiones", "Contenido", "Complejidad", "Calidad", "Colores Dominantes")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=6)
        
        # Configurar columnas
        column_widths = [80, 120, 100, 100, 120, 200]
        for i, (col, width) in enumerate(zip(columns, column_widths)):
            tree.heading(col, text=col)
            tree.column(col, width=width, anchor="center")
        
        # Llenar datos
        for fragment in fragments:
            content_status = "✅ Sí" if fragment.get('has_content', False) else "❌ No"
            complexity = f"{fragment.get('complexity', 0):.2f}"
            colors = " | ".join(fragment.get('dominant_colors', ['N/A'])[:2])  # Solo primeros 2
            
            row_data = (
                f"Parte {fragment['index']}",
                f"{fragment['dimensions'][0]}x{fragment['dimensions'][1]}",
                content_status,
                complexity,
                fragment.get('estimated_quality', 'N/A'),
                colors
            )
            
            tree.insert("", "end", values=row_data)
        
        tree.pack(fill="both", expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
    
    def _create_preview_action_buttons(self, parent, gif_path: Path):
        """Crear botones de acción del preview"""
        button_frame = ttk.Frame(parent, style="Modern.TFrame")
        button_frame.pack(fill="x", pady=(20, 0))
        
        # Botón proceder con fragmentación
        proceed_btn = ttk.Button(button_frame, text="✂️ Proceder con Fragmentación", 
                                command=lambda: self._proceed_with_fragmentation(gif_path),
                                style="Success.TButton")
        proceed_btn.pack(side="left")
        
        # Botón ajustar configuración
        adjust_btn = ttk.Button(button_frame, text="⚙️ Ajustar Configuración", 
                               command=lambda: self._show_fragment_settings(gif_path),
                               style="Secondary.TButton")
        adjust_btn.pack(side="left", padx=(10, 0))
        
        # Botón exportar preview
        export_btn = ttk.Button(button_frame, text="📄 Exportar Preview", 
                               command=lambda: self._export_preview_report(gif_path),
                               style="Secondary.TButton")
        export_btn.pack(side="left", padx=(10, 0))
        
        # Botón cerrar
        close_btn = ttk.Button(button_frame, text="❌ Cerrar", 
                              command=self.preview_window.destroy,
                              style="Danger.TButton")
        close_btn.pack(side="right")
        
        # Botón ayuda
        help_btn = ttk.Button(button_frame, text="❓ Ayuda Steam Workshop", 
                             command=self._show_steam_help,
                             style="Secondary.TButton")
        help_btn.pack(side="right", padx=(0, 10))
    
    def _proceed_with_fragmentation(self, gif_path: Path):
        """Proceder con la fragmentación"""
        logger.info("Procediendo con fragmentacion de %s", gif_path.name)
        self.preview_window.destroy()
        # 🆕 SOLUCIÓN SIMPLE: Usar messagebox para indicar que continúe manualmente
        from tkinter import messagebox
        messagebox.showinfo(
            "Continuar Fragmentación", 
            f"Preview completado para: {gif_path.name}\n\n" +
            f"Para continuar:\n" +
            f"1. Cierra esta ventana\n" +
            f"2. Haz clic en '✂️ Fragmentar' en la ventana principal\n" +
            f"3. Se ejecutará la fragmentación directamente"
        )
        # Aquí se conectaría con el sistema de fragmentación principal
        # Por ahora solo cerramos el preview
    
    def _show_fragment_settings(self, gif_path: Path):
        """Mostrar configuraciones avanzadas de fragmentación"""
        settings_window = tk.Toplevel(self.preview_window)
        settings_window.title("⚙️ Configuración de Fragmentación")
        settings_window.geometry("500x400")
        settings_window.configure(bg=self.theme["bg_primary"])
        
        # Contenido de configuración
        main_frame = ttk.Frame(settings_window, style="Modern.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(main_frame, text="⚙️ Configuración Avanzada", style="Heading.TLabel").pack(pady=(0, 20))
        
        # Opciones de configuración
        options_frame = ttk.LabelFrame(main_frame, text="Opciones de Fragmentación", 
                                      style="Modern.TLabelframe")
        options_frame.pack(fill="x", pady=(0, 20))
        
        # Variables de configuración
        quality_var = tk.StringVar(value="Alta")
        compression_var = tk.BooleanVar(value=True)
        optimization_var = tk.BooleanVar(value=True)
        
        ttk.Label(options_frame, text="Calidad de fragmentos:", style="Body.TLabel").pack(anchor="w", padx=15, pady=(15, 5))
        quality_combo = ttk.Combobox(options_frame, textvariable=quality_var, 
                                    values=["Alta", "Media", "Básica"], 
                                    style="Modern.TCombobox", state="readonly")
        quality_combo.pack(fill="x", padx=15, pady=(0, 10))
        
        ttk.Checkbutton(options_frame, text="🗜️ Optimizar compresión para Steam", 
                       variable=compression_var, style="Modern.TCheckbutton").pack(anchor="w", padx=15, pady=5)
        
        ttk.Checkbutton(options_frame, text="🔧 Ajustar tamaños automáticamente", 
                       variable=optimization_var, style="Modern.TCheckbutton").pack(anchor="w", padx=15, pady=(5, 15))
        
        # Botones
        btn_frame = ttk.Frame(main_frame, style="Modern.TFrame")
        btn_frame.pack(fill="x")
        
        ttk.Button(btn_frame, text="💾 Aplicar", command=settings_window.destroy,
                  style="Primary.TButton").pack(side="right")
        ttk.Button(btn_frame, text="❌ Cancelar", command=settings_window.destroy,
                  style="Secondary.TButton").pack(side="right", padx=(0, 10))
    
    def _export_preview_report(self, gif_path: Path):
        """Exportar reporte del preview"""
        try:
            timestamp = Path().resolve().name
            filename = f"fragment_preview_{gif_path.stem}_{timestamp}.txt"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("👁️ WORKSHOPART PRO - PREVIEW DE FRAGMENTOS\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"📁 Archivo: {gif_path.name}\n")
                f.write(f"📅 Generado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n")
                
                f.write("📊 ANÁLISIS DE FRAGMENTACIÓN\n")
                f.write("-" * 30 + "\n")
                f.write("Este reporte muestra cómo se verá el archivo fragmentado\n")
                f.write("para Steam Workshop (5 partes de 127x354 px cada una).\n\n")
                
                f.write("🎮 PRÓXIMOS PASOS:\n")
                f.write("1. Fragmentar el archivo usando WorkshopArt PRO\n")
                f.write("2. Subir las 5 partes a Steam Workshop\n")
                f.write("3. Aplicar comandos de consola para completar\n")
            
            logger.info("Preview exportado: %s", filename)
            
        except Exception as e:
            logger.error("Error exportando preview: %s", e)
    
    def _show_steam_help(self):
        """Mostrar ayuda sobre Steam Workshop"""
        help_window = tk.Toplevel(self.preview_window)
        help_window.title("❓ Ayuda - Steam Workshop")
        help_window.geometry("600x500")
        help_window.configure(bg=self.theme["bg_primary"])
        
        # Contenido de ayuda
        main_frame = ttk.Frame(help_window, style="Modern.TFrame")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(main_frame, text="🎮 Guía Steam Workshop", style="Title.TLabel").pack(pady=(0, 20))
        
        help_text = """
📋 PASOS PARA SUBIR A STEAM WORKSHOP:

1️⃣ FRAGMENTAR EL GIF
   • WorkshopArt PRO dividirá tu GIF en 5 partes
   • Cada parte será de 127x354 píxeles
   • Tamaño optimal: 4.2-4.8 MB por parte

2️⃣ SUBIR A STEAM WORKSHOP
   • Ve a Steam Workshop Uploader
   • Sube los 5 archivos .gif generados
   • Espera a que se procesen

3️⃣ CONFIGURAR EN STEAM
   • Abre la consola del navegador (F12)
   • Ejecuta estos comandos:
   
   $J('[name=consumer_app_id]').val(480);
   $J('[name=file_type]').val(0);
   $J('[name=visibility]').val(0);

4️⃣ PUBLICAR
   • Completa la descripción
   • Agrega tags apropiados
   • ¡Publica tu GIF animado!

💡 CONSEJOS:
   • Prueba tu GIF antes de subir
   • Usa nombres descriptivos
   • Verifica que todas las partes se subieron
        """
        
        text_widget = tk.Text(main_frame, wrap=tk.WORD, height=20,
                             bg=self.theme["bg_elevated"],
                             fg=self.theme["text_primary"],
                             font=('Segoe UI', 10),
                             padx=15, pady=15)
        text_widget.pack(fill="both", expand=True)
        text_widget.insert("1.0", help_text)
        text_widget.config(state="disabled")
        
        # Botón cerrar
        ttk.Button(main_frame, text="❌ Cerrar", command=help_window.destroy,
                  style="Primary.TButton").pack(pady=(20, 0))

    def create_live_fragment_preview(self, gif_path: Path, parent_frame):
        """Crear preview en vivo integrado en la interfaz principal"""
        try:
            # Frame para preview en vivo
            live_preview_frame = ttk.LabelFrame(parent_frame, text="👁️ Preview de Fragmentos", 
                                              style="Modern.TLabelframe")
            live_preview_frame.pack(fill="x", pady=(10, 0))
            
            with Image.open(gif_path) as img:
                if img.format == 'GIF':
                    display_img = img.convert('RGB')
                else:
                    display_img = img.convert('RGB')
                
                # Redimensionar para preview pequeño
                display_width = 400
                aspect_ratio = display_img.height / display_img.width
                display_height = int(display_width * aspect_ratio)
                
                display_img = display_img.resize((display_width, display_height), Image.Resampling.LANCZOS)
                
                # Dibujar líneas de división
                draw = ImageDraw.Draw(display_img)
                fragment_width = display_width // 5
                
                for i in range(1, 5):
                    x = i * fragment_width
                    draw.line([(x, 0), (x, display_height)], fill='#ff4444', width=2)
                
                # Convertir a PhotoImage
                photo = ImageTk.PhotoImage(display_img)
                
                # Mostrar imagen
                img_label = ttk.Label(live_preview_frame, image=photo)
                img_label.image = photo  # Mantener referencia
                img_label.pack(pady=10)
                
                # Info rápida
                fragment_width_px = 638 // 5  # Dimensiones reales
                info_text = f"5 fragmentos de {fragment_width_px}x354 px cada uno"
                ttk.Label(live_preview_frame, text=info_text, style="Caption.TLabel").pack()
                
            return live_preview_frame
            
        except Exception as e:
            logger.warning("Error en preview en vivo: %s", e)
            return None