"""
i18n.py - Internationalization for ES, EN, and PT locales.

All UI strings are stored in three flat dicts (ES, EN, PT). The active locale
is held in the module-level _current_lang variable and switched at runtime via
set_language(). Lookups fall back to ES if a key is missing in EN or PT.

Usage:
    from i18n import t, set_language, get_language
    set_language("EN")
    label.configure(text=t("open_file"))          # "Open file"
    msg = t("welcome_log")                        # "WorkshopArt v1.0 started"
    fmt = t("current_size_log", current=1.2, target=4.5)  # format placeholders

String keys are organized by the file/method that uses them (see inline comments
in each dict). Format placeholders use {name} syntax and are resolved by t().
"""

# Active locale — module-level so t() always reads the latest value without passing state around.
_current_lang = "ES"

# ---------------------------------------------------------------------------
# Translation dictionaries
# ---------------------------------------------------------------------------

ES = {
    # ---- gui.py  Sidebar ----
    "app_title": "WorkshopArt",
    "version": "v1.0",
    "open_file": "Abrir archivo",
    "process_ai": "Procesar con IA",
    "colors_only": "Solo colores",
    "mp4_to_gif": "MP4 a GIF",
    "enhance_animation": "Mejorar animación",
    "fragment_steam": "Fragmentar...",
    "optimize_size": "Optimizar a 5MB",
    "tip_open_file": "Carga un video, GIF o imagen (MP4, AVI, MOV, GIF, JPG, PNG)",
    "tip_process_ai": "Escala 4x con IA y mejora colores",
    "tip_colors_only": "Mejora contraste y saturación sin upscaling",
    "tip_mp4_to_gif": "Convierte un video MP4 a GIF animado",
    "tip_enhance_animation": "Mejora FPS y fluidez de la animación",
    "tip_fragment_steam": "Elige formato: Workshop, Artwork, Screenshot, Panorama, Grids...",
    "tip_optimize_size": "Reduce fragmentos por debajo del límite de 5MB manteniendo máxima calidad",
    "download_models": "Descargar modelos IA",
    "tip_download_models": "Descarga modelos Real-ESRGAN y Real-CUGAN (~200 MB)",
    "help": "Ayuda",
    "gpu_label": "GPU: ...",
    "ffmpeg_label": "FFmpeg: ...",
    "models_label": "Modelos: ...",

    # ---- gui.py  Center ----
    "drop_here": "Arrastra un archivo aquí",
    "supported_formats": "MP4 / AVI / MOV / GIF / JPG / PNG",
    "select_file_btn": "Seleccionar archivo",
    "log_title": "Registro",

    # ---- gui.py  Right panel ----
    "config_title": "Configuración",
    "ai_model": "Modelo IA",
    "auto_detect_model": "Auto-detectar modelo",
    "processing_section": "Procesamiento",
    "use_gpu": "Usar GPU",
    "tip_use_gpu": "Procesa ~10x más rápido si tienes GPU compatible",
    "quality_section": "Calidad",
    "quality_high": "Alta",
    "quality_balanced": "Balanceada",
    "visual_enhancements": "Mejoras visuales",
    "enhance_colors": "Mejorar colores",
    "enhance_animation_check": "Mejorar animación",
    "contrast": "Contraste",
    "saturation": "Saturación",
    "vibrance": "Vibrance",
    "sharpness": "Nitidez",
    "temperature": "Temperatura de color",
    "model_info": "Info modelo",
    "steam_workshop": "Steam Workshop",
    "steam_instructions": (
        "1. Fragmenta tu GIF\n"
        "2. Sube los 5 archivos\n"
        "3. Consola F12 > comandos JS\n"
        "4. Publica en tu perfil"
    ),
    "view_tutorial": "Ver tutorial",

    # ---- gui.py  Hardware requirements ----
    "hw_requirements": "Requisitos IA",
    "hw_info": (
        "GPU: NVIDIA / AMD con Vulkan\n"
        "(GTX 1060+ / RX 570+)\n"
        "RAM: 8 GB mínimo\n"
        "VRAM: 2 GB mínimo\n"
        "Sin GPU: procesamiento por CPU\n"
        "(mucho más lento, ~10x)"
    ),

    # ---- gui.py  Status bar ----
    "status_ready": "Listo",
    "cancel_processing": "Cancelar",
    "cancelling": "Cancelando...",
    "cancel_requested_log": "Cancelación solicitada por el usuario",

    # ---- gui.py  Drag & drop ----
    "unsupported_format_title": "Formato no soportado",
    "unsupported_format_msg": "Arrastra un archivo MP4, AVI, MOV, MKV, WEBM, GIF, JPG o PNG.",

    # ---- gui.py  Language selector ----
    "language_label": "Idioma",

    # ---- gui_methods.py  check_dependencies ----
    "checking_gpu": "Verificando GPU...",
    "gpu_detected": "GPU detectada: {info}",
    "gpu_not_detected_status": "No detectada",
    "gpu_not_detected_log": "GPU no detectada, usando CPU",
    "ffmpeg_available_status": "Disponible",
    "ffmpeg_available_log": "FFmpeg disponible",
    "ffmpeg_not_found_status": "No encontrado",
    "ffmpeg_not_found_log": "FFmpeg no encontrado - Algunas funciones limitadas",
    "models_count_status": "{count}/5 modelos",
    "models_available_log": "{count} modelos disponibles",
    "models_not_available_status": "No disponibles",
    "models_not_available_log": "No hay modelos disponibles - Descarga necesaria",
    "error_checking_deps": "Error verificando dependencias: {e}",

    # ---- gui_methods.py  model info ----
    "quality_score": "Calidad: {quality}/10 | Velocidad: {speed}/10",
    "ideal_for": "Ideal para: {uses}",

    # ---- gui_methods.py  select_file ----
    "filetypes_media": "Archivos multimedia",
    "filetypes_videos": "Videos",
    "filetypes_gifs": "GIFs",
    "filetypes_all": "Todos",
    "select_file_title": "Seleccionar archivo",

    # ---- gui_methods.py  show_file_info ----
    "size_label": "Tamaño: {size:.2f} MB",
    "dimensions_label": "Dimensiones: {w}x{h}",
    "frames_label": "Frames: {n}",
    "fps_label": "FPS: {fps:.1f}",
    "duration_label": "Duración: {dur:.1f}s",
    "video_info_error": "No se pudo leer info del video",
    "type_label": "Tipo: {content_type} ({confidence:.0f}%)",
    "file_selected_log": "Archivo seleccionado: {name}",
    "file_loaded_status": "Archivo cargado",
    "error_prefix": "Error: {e}",
    "error_file_info_log": "Error mostrando info del archivo: {e}",

    # ---- gui_methods.py  analyze_content ----
    "analyzing_status": "Analizando contenido...",
    "analyzing_log": "Analizando tipo de contenido...",
    "type_detected_log": "Tipo detectado: {content_type}",
    "model_recommended_log": "Modelo recomendado: {model}",
    "analysis_completed_status": "Análisis completado",
    "analysis_error_log": "Error analizando contenido: {e}",
    "analysis_error_status": "Error en análisis",

    # ---- gui_methods.py  download_models ----
    "preparing_download_status": "Preparando descarga...",
    "download_header_log": "=== DESCARGA DE MODELOS ===",
    "downloading_models_log": "Descargando 5 modelos de Real-ESRGAN...",
    "download_completed_log": "Descarga completada",
    "models_downloaded_status": "¡Modelos descargados!",
    "download_completed_header_log": "=== DESCARGA COMPLETADA ===",
    "models_available_count_log": "Modelos disponibles: {count}/5",
    "download_success_title": "¡Éxito!",
    "download_success_msg": (
        "¡Descarga completada!\n\n"
        "{check} {count} modelos disponibles\n"
        "Ubicación: {location}\n\n"
        "¡Ya puedes procesar con IA!"
    ),
    "download_error_status": "Error en descarga",
    "download_error_log": "Error descargando modelos",
    "download_error_title": "Error",
    "download_error_msg": (
        "Error descargando modelos.\n\n"
        "Posibles causas:\n"
        "- Sin conexión a internet\n"
        "- Firewall bloqueando GitHub\n"
        "- Espacio insuficiente en disco\n\n"
        "Intenta descargar manualmente desde:\n"
        "github.com/xinntao/Real-ESRGAN/releases"
    ),
    "confirm_download_title": "Confirmar Descarga",
    "confirm_download_msg": (
        "¿Descargar todos los modelos de IA?\n\n"
        "5 modelos especializados:\n"
        "- Anime Video v3 (gaming/anime)\n"
        "- x4plus (uso general)\n"
        "- x4plus Anime (máxima calidad)\n"
        "- ESRNet (fotos realistas)\n"
        "- x2plus (rápido)\n\n"
        "~200 MB de descarga\n"
        "2-5 minutos según conexión\n\n"
        "¿Continuar?"
    ),

    # ---- gui_methods.py  process_full_ai ----
    "warning_title": "Advertencia",
    "select_file_first": "Primero selecciona un archivo",
    "select_model_first": "Selecciona un modelo de IA",
    "starting_ai_status": "Iniciando procesamiento con IA...",
    "ai_header_log": "=== PROCESAMIENTO CON IA ===",
    "file_log": "Archivo: {name}",
    "model_log": "Modelo: {model}",
    "processing_mode_log": "Modo de procesamiento: {mode}",
    "preparing_file_status": "Preparando archivo...",
    "converting_video_log": "Convirtiendo video a GIF...",
    "convert_error": "Error convirtiendo video a GIF",
    "video_converted_log": "Video convertido: {name}",
    "extracting_frames_status": "Extrayendo frames...",
    "extracting_frames_log": "Extrayendo frames...",
    "extract_error": "Error extrayendo frames",
    "frames_extracted_log": "Frames extraídos: {count}, FPS: {fps:.1f}",
    "applying_ai_status": "Aplicando IA con {mode}...",
    "upscale_error": "Error en el upscaling con IA",
    "ai_applied_log": "IA aplicada: {count} frames mejorados",
    "empty_frames_error": "Lista de frames upscaleados está vacía",
    "invalid_frame_log": "Frame no válido: {path}",
    "no_valid_frames_error": "No hay frames válidos después del upscaling",
    "valid_frames_log": "Frames válidos: {count}",
    "color_prep_status": "Preparando mejoras de color...",
    "color_prep_log": "Mejoras de color se aplicarán al GIF final...",
    "creating_gif_status": "Creando GIF final...",
    "gif_created_log": "GIF base creado correctamente: {size:.2f} MB",
    "applying_colors_status": "Aplicando mejoras de color...",
    "applying_colors_log": "Aplicando mejoras de color...",
    "gif_valid_log": "GIF válido: {count} frames",
    "gif_invalid_warning": "GIF no válido para mejoras: {e}",
    "gif_corrupt_error": "GIF base corrupto: {e}",
    "color_timeout_warning": "Timeout en mejoras de color (>60s)",
    "continue_no_colors": "Continuando sin mejoras de color...",
    "color_error_warning": "Error en mejoras: {e}",
    "colors_applied_log": "Mejoras aplicadas: {size:.2f} MB",
    "no_colors_needed": "No se requirieron mejoras de color",
    "skip_colors_warning": "Saltando mejoras de color: {e}",
    "processing_completed_status": "¡Procesamiento completado!",
    "processing_completed_header": "=== PROCESAMIENTO COMPLETADO ===",
    "final_file_log": "Archivo final: {name}",
    "size_log": "Tamaño: {size:.2f} MB",
    "generating_report_log": "Generando reporte de calidad...",
    "report_generated_log": "Reporte de calidad generado",
    "report_failed_log": "No se pudo generar reporte de calidad",
    "report_system_unavailable": "Sistema de reportes no disponible",
    "report_error_log": "Error en reporte de calidad: {e}",
    "success_title": "¡Éxito!",
    "ai_success_msg": (
        "¡Procesamiento completado exitosamente!\n\n"
        "Archivo: {name}\n"
        "Tamaño: {size:.2f} MB\n"
        "Modelo: {model}\n"
        "Procesado con: {mode}\n\n"
        "Mejoras aplicadas: {enhanced}\n"
        "Se abrirá el reporte de calidad...\n"
        "¡Listo para fragmentar para Steam!"
    ),
    "critical_error_log": "ERROR CRÍTICO: {e}",
    "error_title": "Error",
    "ai_error_msg": (
        "Error en procesamiento con IA:\n\n{e}\n\n"
        "Posibles causas:\n"
        "- Modelo de IA no disponible\n"
        "- GPU no compatible\n"
        "- Frames de entrada corruptos\n"
        "- Memoria insuficiente\n\n"
        "Soluciones:\n"
        "- Verifica que el modelo esté descargado\n"
        "- Cambia a modo CPU\n"
        "- Usa un archivo más pequeño\n"
        "- Reinicia WorkshopArt"
    ),
    "gif_error_msg": (
        "Error creando GIF final:\n\n{e}\n\n"
        "Posibles causas:\n"
        "- Frames de IA corruptos\n"
        "- Memoria insuficiente\n"
        "- Archivo original demasiado largo\n\n"
        "Soluciones:\n"
        "- Usar archivo más corto (<10s)\n"
        "- Cerrar otras aplicaciones\n"
        "- Reiniciar WorkshopArt"
    ),
    "generic_error_msg": "Error en procesamiento:\n\n{e}",
    "temp_cleaned_log": "Archivos temporales limpiados",
    "temp_clean_warning": "Advertencia limpiando temporales: {e}",
    "confirm_process_title": "Confirmar Procesamiento",
    "confirm_process_msg": (
        "¿Procesar archivo con IA?\n\n"
        "Archivo: {name}\n"
        "Modelo: {model}\n"
        "Procesamiento: {mode}\n"
        "Calidad: {quality}\n"
        "Tiempo estimado: 2-10 minutos\n\n"
        "Mejoras de color: {enhanced}\n"
        "Se generará reporte de calidad\n\n"
        "¿Continuar?"
    ),
    "yes_label": "Sí",
    "no_label": "No",

    # ---- gui_methods.py  enhance_colors_only ----
    "enhancing_colors_status": "Mejorando colores...",
    "applying_color_log": "Aplicando mejoras de color...",
    "contrast_log": "Contraste: {val:.1f}",
    "saturation_log": "Saturación: {val:.1f}",
    "colors_improved_status": "¡Colores mejorados!",
    "enhanced_file_log": "Archivo mejorado: {name}",
    "colors_success_msg": (
        "¡Colores mejorados exitosamente!\n\n"
        "Archivo: {name}\n"
        "Contraste: {contrast:.1f}\n"
        "Saturación: {saturation:.1f}"
    ),

    # ---- gui_methods.py  convert_mp4_to_gif ----
    "not_video_warning": (
        "El archivo seleccionado no es un video.\n"
        "Formatos soportados: MP4, AVI, MOV, MKV, WEBM"
    ),
    "convert_window_title": "Convertir Video a GIF",
    "conversion_title": "Conversión Video a GIF",
    "selected_file_label": "Archivo seleccionado",
    "file_label": "Archivo: {name}",
    "video_info_label": "Duración: {dur:.1f}s | FPS: {fps:.1f} | {size}",
    "video_read_error": "No se pudo leer info del video",
    "fps_for_gif": "FPS para el GIF",
    "custom_fps": "FPS personalizado:",
    "quality_label": "Calidad",
    "quality_fast": "Rápido",
    "quality_balanced_label": "Balanceado",
    "quality_high_label": "Alta calidad",
    "options_label": "Opciones",
    "resize_steam": "Redimensionar a 638x354 (Steam)",
    "auto_enhance_colors": "Mejorar colores automáticamente",
    "estimated_size": "Tamaño estimado: ~{size:.1f} MB",
    "estimated_size_unavailable": "Tamaño estimado: No disponible",
    "estimated_size_calculating": "Tamaño estimado: Calculando...",
    "convert_to_gif_btn": "Convertir a GIF",
    "cancel_btn": "Cancelar",
    "converting_status": "Convirtiendo video a GIF...",
    "conversion_header_log": "=== CONVERSIÓN MP4 -> GIF ===",
    "fps_log": "FPS: {fps}",
    "quality_log": "Calidad: {quality}",
    "resize_log": "Redimensionar: {resize}",
    "conversion_completed_status": "Conversión completada",
    "conversion_completed_full_status": "¡Conversión completada!",
    "gif_created_file_log": "GIF creado: {name}",
    "final_size_log": "Tamaño final: {size:.2f} MB",
    "conversion_success_title": "¡Conversión Exitosa!",
    "conversion_success_msg": (
        "¡Video convertido a GIF!\n\n"
        "Archivo: {name}\n"
        "FPS: {fps}\n"
        "Tamaño: {size:.2f} MB\n"
        "Mejoras: {enhanced}\n\n"
        "Listo para procesar con IA o fragmentar"
    ),
    "conversion_failed": "No se pudo convertir el video",
    "conversion_error_status": "Error en conversión",
    "conversion_error_msg": "Error convirtiendo video:\n\n{e}",

    # ---- gui_methods.py  enhance_animation ----
    "enhance_anim_window_title": "Mejorar Animación",
    "enhance_anim_title": "Mejora de Animación",
    "interpolation_60fps": "Interpolación a 60 FPS",
    "interpolation_desc": "Duplica/triplica frames para mayor fluidez",
    "smooth_motion": "Suavizado de Movimiento",
    "smooth_desc": "Aplica motion blur suave",
    "optimize_playback": "Optimizar Reproducción",
    "optimize_desc": "Normaliza timing para reproducción estable",
    "apply_btn": "Aplicar",
    "interpolating_status": "Interpolando a 60 FPS...",
    "interpolation_header_log": "=== INTERPOLACIÓN A 60 FPS ===",
    "interpolation_success": "¡Interpolación a 60 FPS completada!",
    "smoothing_status": "Aplicando suavizado...",
    "smoothing_header_log": "=== SUAVIZADO DE MOVIMIENTO ===",
    "smoothing_success": "¡Efecto de suavizado aplicado!",
    "optimizing_status": "Optimizando reproducción...",
    "optimizing_header_log": "=== OPTIMIZACIÓN DE REPRODUCCIÓN ===",
    "optimizing_success": "¡Reproducción optimizada!",
    "enhancement_completed_status": "¡Mejora completada!",
    "enhanced_file_success_log": "Archivo mejorado: {name}",
    "no_changes_status": "No se requieren cambios",
    "already_optimized_title": "Información",
    "already_optimized_msg": "El archivo ya está optimizado o no requiere cambios.",
    "enhancement_error_msg": "Error en mejora: {e}",

    # ---- gui_methods.py  optimization dialog ----
    "optimization_needed_title": "Optimización Recomendada",
    "optimization_needed_msg": (
        "OPTIMIZACIÓN NECESARIA\n\n"
        "- Fragmentos pequeños: {small}/5\n"
        "- Fragmentos grandes: {large}/5\n\n"
    ),
    "small_fragments_warning": (
        "Los fragmentos pequeños pueden ser rechazados por Steam.\n"
        "La optimización aprovechará mejor el espacio disponible.\n\n"
    ),
    "optimization_question": (
        "¿Aplicar optimización automática?\n\n"
        "SÍ: Mejora la calidad automáticamente\n"
        "NO: Mantiene fragmentos como están"
    ),

    # ---- gui_methods.py  fragment reports ----
    "fragment_completed_title": "Fragmentación Completada",
    "fragment_completed_msg": (
        "¡FRAGMENTACIÓN COMPLETADA EXITOSAMENTE!\n\n"
        "ESTADÍSTICAS FINALES:\n"
        "Fragmentos óptimos: {optimal}/5\n"
        "Fragmentos pequeños: {small}/5\n"
        "Fragmentos grandes: {large}/5\n\n"
        "ARCHIVOS CREADOS:\n"
    ),
    "fragment_total": "Total: {total:.2f} MB",
    "fragment_perfect": "¡PERFECTO! Todos los fragmentos están en el rango óptimo.\nSteam Workshop obtendrá la máxima calidad posible.",
    "fragment_excellent": "¡EXCELENTE! La mayoría de fragmentos están optimizados.",
    "fragment_next_step": (
        "SIGUIENTE PASO:\n"
        "1. Sube los 5 archivos a Steam Workshop\n"
        "2. Abre la consola del navegador (F12)\n"
        "3. Ejecuta estos comandos:\n\n"
    ),
    "fragment_ready": "¡Listo para subir a Steam Workshop!",

    # ---- gui_methods.py  show_help ----
    "help_window_title": "Ayuda - WorkshopArt",
    "close_btn": "Cerrar",
    "help_text": """WORKSHOPART v1.0 - GUÍA COMPLETA

    PASO 1: SELECCIONAR ARCHIVO
    - Haz clic en "Seleccionar Archivo"
    - Formatos soportados: MP4, AVI, MOV, GIF
    - La detección automática sugerirá el mejor modelo de IA

    PASO 2: CONFIGURAR IA
    - Si es la primera vez, descarga los modelos (botón "Descargar")
    - El modelo se selecciona automáticamente según tu contenido
    - Elige GPU para velocidad o CPU para compatibilidad

    PASO 3: PROCESAR
    - Procesar con IA: Mejora todo el archivo con IA 4x (mejor calidad)
    - Solo Colores: Ajusta contraste/saturación sin IA (más rápido)
    - Mejorar Animación: Interpola frames para mayor fluidez

    PASO 4: FRAGMENTAR
    - Divide el GIF en 5 partes para Steam Workshop
    - Cada parte será ~4.6 MB (ajuste automático)
    - Redimensiona a 638x354 px automáticamente

    PASO 5: SUBIR A STEAM
    1. Ve a Steam Workshop Uploader
    2. Sube los 5 archivos .gif creados
    3. Abre la consola del navegador (F12)
    4. Ejecuta los comandos mostrados

    CONSEJOS:
    - Usa "Auto-detectar" para mejores resultados automáticos
    - GPU es 5-10x más rápido que CPU
    - Para videos largos, recorta a 5-10 segundos primero
    - Ajusta colores DESPUÉS de aplicar IA para mejor resultado

    MODELOS DE IA DISPONIBLES:
    - Anime Video v3: Perfecto para gaming/anime (RECOMENDADO)
    - x4plus: Uso general, muy versátil
    - x4plus Anime: Máxima calidad para ilustraciones
    - ESRNet: Fotos realistas y retratos
    - x2plus: Escalado 2x, el más rápido
    - Real-CUGAN: Especializado en anime (Bilibili)

    SOLUCIÓN DE PROBLEMAS:
    - Si la GPU no se detecta: Actualiza drivers
    - Si falla la fragmentación: Instala FFmpeg
    - Si los modelos no descargan: Verifica firewall/antivirus
    - Si el proceso es lento: Cierra otras aplicaciones

    Tutorial completo en video:
    youtube.com/watch?v=BQ-9E7sFWc0""",

    # ---- gui_methods.py  on_closing / run ----
    "app_closed_log": "Aplicación cerrada correctamente",
    "welcome_log": "WorkshopArt v2.0 iniciado",
    "welcome_modular_log": "Versión modular con todas las funciones",
    "welcome_start_log": "Selecciona un archivo para comenzar",
    "tutorial_opened_log": "Tutorial de Steam abierto",
    "tutorial_error_log": "Error abriendo tutorial: {e}",

    # ---- gui_methods.py  fragment_for_steam ----
    "fragment_options_title": "Opciones de Fragmentación",
    "fragment_options_msg": (
        "¿Cómo quieres fragmentar {name}?\n\n"
        "SÍ: Ver preview primero\n"
        "NO: Fragmentar directamente\n\n"
        "Recomendado: Ver preview primero"
    ),
    "preview_error_title": "Error en Preview",
    "preview_error_msg": "Error creando preview:\n{e}\n\nFragmentando directamente...",

    # ---- gui_methods.py  fragment_for_steam_direct ----
    "starting_fragment_status": "Iniciando fragmentación...",
    "direct_fragment_header_log": "=== FRAGMENTACIÓN DIRECTA ===",
    "converting_to_gif_log": "Convirtiendo a GIF...",
    "converting_to_gif_status": "Convirtiendo a GIF...",
    "convert_to_gif_error": "Error convirtiendo a GIF",
    "fragmenting_status": "Fragmentando en 5 partes...",
    "fragmenting_log": "Fragmentando para Steam Workshop...",
    "fragment_success_status": "¡Fragmentación completada!",
    "fragment_success_log": "Fragmentación completada exitosamente",
    "created_log": "Creado: {name} ({size:.2f} MB)",
    "fragment_success_title": "¡Fragmentación Exitosa!",
    "fragment_success_msg": (
        "¡Fragmentación completada!\n\n"
        "Archivos creados:\n{files}\n\n"
        "Tamaño total: {total:.2f} MB\n\n"
        "¡Listos para subir a Steam Workshop!"
    ),
    "fragment_failed": "La fragmentación falló",
    "fragment_error_status": "Error en fragmentación",
    "fragment_error_msg": "Error en fragmentación:\n\n{e}",

    # ---- gui_methods.py  fragment_for_steam_ffmpeg_only ----
    "ffmpeg_fragment_header_log": "=== FRAGMENTACIÓN STEAM (SOLO FFMPEG) ===",
    "verifying_file_status": "Verificando archivo...",
    "analyzing_fragments_status": "Analizando fragmentos...",
    "fragment_status_optimal": "ÓPTIMO",
    "fragment_status_small": "PEQUEÑO",
    "fragment_not_created": "No se creó fragmento {i}",
    "optimizing_ffmpeg_status": "Optimizando con FFmpeg...",
    "optimizing_fragments_log": "Optimizando {count} fragmentos...",
    "optimizing_fragment_log": "Optimizando fragmento {part}...",
    "optimized_log": "Optimizado: {size:.2f} MB",
    "not_fully_optimized_log": "No se pudo optimizar completamente",
    "optimized_count_log": "Optimizados: {done}/{total}",
    "ffmpeg_confirm_title": "Fragmentación FFmpeg",
    "ffmpeg_confirm_msg": (
        "¿Fragmentar usando solo FFmpeg?\n\n"
        "{name}\n"
        "Optimización automática\n"
        "Sin procesamiento IA (más rápido)\n\n"
        "¿Continuar?"
    ),

    # ---- gui_methods.py  optimization internal ----
    "current_size_log": "   Tamaño actual: {current:.2f} MB, objetivo: {target:.2f} MB",
    "ffmpeg_not_available": "   FFmpeg no disponible",
    "trying_strategies_log": "   Probando {count} estrategias FFmpeg...",
    "strategy_result_log": "   Estrategia FFmpeg {i}: {size:.2f} MB",
    "strategy_success_log": "   Estrategia FFmpeg {i} ÉXITO: {old:.2f} -> {new:.2f} MB",
    "best_result_log": "   Mejor resultado hasta ahora: {size:.2f} MB",
    "strategy_error_log": "   Estrategia {i} error: {msg}",
    "strategy_timeout_log": "   Estrategia {i} timeout (>60s)",
    "strategy_exception_log": "   Error estrategia {i}: {msg}",
    "ffmpeg_best_result_log": "   FFmpeg mejor resultado: {old:.2f} -> {new:.2f} MB (+{diff:.2f})",
    "ffmpeg_insufficient_log": "   Mejora FFmpeg insuficiente: +{diff:.2f} MB",
    "ffmpeg_no_strategy_log": "   FFmpeg: ninguna estrategia alcanzó objetivo",
    "ffmpeg_general_error_log": "   Error general FFmpeg: {e}",
}

EN = {
    # ---- gui.py  Sidebar ----
    "app_title": "WorkshopArt",
    "version": "v1.0",
    "open_file": "Open file",
    "process_ai": "Process with AI",
    "colors_only": "Colors only",
    "mp4_to_gif": "MP4 to GIF",
    "enhance_animation": "Enhance animation",
    "fragment_steam": "Fragment...",
    "optimize_size": "Optimize to 5MB",
    "tip_open_file": "Load a video, GIF or image (MP4, AVI, MOV, GIF, JPG, PNG)",
    "tip_process_ai": "4x upscale with AI and enhance colors",
    "tip_colors_only": "Enhance contrast and saturation without upscaling",
    "tip_mp4_to_gif": "Convert an MP4 video to an animated GIF",
    "tip_enhance_animation": "Improve FPS and animation smoothness",
    "tip_fragment_steam": "Pick format: Workshop, Artwork, Screenshot, Panorama, Grids...",
    "tip_optimize_size": "Shrink fragments below the 5MB limit while preserving max quality",
    "download_models": "Download AI models",
    "tip_download_models": "Download Real-ESRGAN and Real-CUGAN models (~200 MB)",
    "help": "Help",
    "gpu_label": "GPU: ...",
    "ffmpeg_label": "FFmpeg: ...",
    "models_label": "Models: ...",

    # ---- gui.py  Center ----
    "drop_here": "Drop a file here",
    "supported_formats": "MP4 / AVI / MOV / GIF / JPG / PNG",
    "select_file_btn": "Select file",
    "log_title": "Log",

    # ---- gui.py  Right panel ----
    "config_title": "Settings",
    "ai_model": "AI Model",
    "auto_detect_model": "Auto-detect model",
    "processing_section": "Processing",
    "use_gpu": "Use GPU",
    "tip_use_gpu": "~10x faster processing with a compatible GPU",
    "quality_section": "Quality",
    "quality_high": "High",
    "quality_balanced": "Balanced",
    "visual_enhancements": "Visual enhancements",
    "enhance_colors": "Enhance colors",
    "enhance_animation_check": "Enhance animation",
    "contrast": "Contrast",
    "saturation": "Saturation",
    "vibrance": "Vibrance",
    "sharpness": "Sharpness",
    "temperature": "Color temperature",
    "model_info": "Model info",
    "steam_workshop": "Steam Workshop",
    "steam_instructions": (
        "1. Fragment your GIF\n"
        "2. Upload all 5 files\n"
        "3. F12 console > JS commands\n"
        "4. Publish to your profile"
    ),
    "view_tutorial": "View tutorial",

    # ---- gui.py  Hardware requirements ----
    "hw_requirements": "AI Requirements",
    "hw_info": (
        "GPU: NVIDIA / AMD with Vulkan\n"
        "(GTX 1060+ / RX 570+)\n"
        "RAM: 8 GB minimum\n"
        "VRAM: 2 GB minimum\n"
        "No GPU: CPU processing\n"
        "(much slower, ~10x)"
    ),

    # ---- gui.py  Status bar ----
    "status_ready": "Ready",
    "cancel_processing": "Cancel",
    "cancelling": "Cancelling...",
    "cancel_requested_log": "Cancellation requested by user",

    # ---- gui.py  Drag & drop ----
    "unsupported_format_title": "Unsupported format",
    "unsupported_format_msg": "Drop an MP4, AVI, MOV, MKV, WEBM, GIF, JPG or PNG file.",

    # ---- gui.py  Language selector ----
    "language_label": "Language",

    # ---- gui_methods.py  check_dependencies ----
    "checking_gpu": "Checking GPU...",
    "gpu_detected": "GPU detected: {info}",
    "gpu_not_detected_status": "Not detected",
    "gpu_not_detected_log": "GPU not detected, using CPU",
    "ffmpeg_available_status": "Available",
    "ffmpeg_available_log": "FFmpeg available",
    "ffmpeg_not_found_status": "Not found",
    "ffmpeg_not_found_log": "FFmpeg not found - Some features limited",
    "models_count_status": "{count}/5 models",
    "models_available_log": "{count} models available",
    "models_not_available_status": "Not available",
    "models_not_available_log": "No models available - Download required",
    "error_checking_deps": "Error checking dependencies: {e}",

    # ---- gui_methods.py  model info ----
    "quality_score": "Quality: {quality}/10 | Speed: {speed}/10",
    "ideal_for": "Best for: {uses}",

    # ---- gui_methods.py  select_file ----
    "filetypes_media": "Media files",
    "filetypes_videos": "Videos",
    "filetypes_gifs": "GIFs",
    "filetypes_all": "All",
    "select_file_title": "Select file",

    # ---- gui_methods.py  show_file_info ----
    "size_label": "Size: {size:.2f} MB",
    "dimensions_label": "Dimensions: {w}x{h}",
    "frames_label": "Frames: {n}",
    "fps_label": "FPS: {fps:.1f}",
    "duration_label": "Duration: {dur:.1f}s",
    "video_info_error": "Could not read video info",
    "type_label": "Type: {content_type} ({confidence:.0f}%)",
    "file_selected_log": "File selected: {name}",
    "file_loaded_status": "File loaded",
    "error_prefix": "Error: {e}",
    "error_file_info_log": "Error showing file info: {e}",

    # ---- gui_methods.py  analyze_content ----
    "analyzing_status": "Analyzing content...",
    "analyzing_log": "Analyzing content type...",
    "type_detected_log": "Detected type: {content_type}",
    "model_recommended_log": "Recommended model: {model}",
    "analysis_completed_status": "Analysis completed",
    "analysis_error_log": "Error analyzing content: {e}",
    "analysis_error_status": "Analysis error",

    # ---- gui_methods.py  download_models ----
    "preparing_download_status": "Preparing download...",
    "download_header_log": "=== MODEL DOWNLOAD ===",
    "downloading_models_log": "Downloading 5 Real-ESRGAN models...",
    "download_completed_log": "Download completed",
    "models_downloaded_status": "Models downloaded!",
    "download_completed_header_log": "=== DOWNLOAD COMPLETED ===",
    "models_available_count_log": "Models available: {count}/5",
    "download_success_title": "Success!",
    "download_success_msg": (
        "Download completed!\n\n"
        "{check} {count} models available\n"
        "Location: {location}\n\n"
        "You can now process with AI!"
    ),
    "download_error_status": "Download error",
    "download_error_log": "Error downloading models",
    "download_error_title": "Error",
    "download_error_msg": (
        "Error downloading models.\n\n"
        "Possible causes:\n"
        "- No internet connection\n"
        "- Firewall blocking GitHub\n"
        "- Insufficient disk space\n\n"
        "Try downloading manually from:\n"
        "github.com/xinntao/Real-ESRGAN/releases"
    ),
    "confirm_download_title": "Confirm Download",
    "confirm_download_msg": (
        "Download all AI models?\n\n"
        "5 specialized models:\n"
        "- Anime Video v3 (gaming/anime)\n"
        "- x4plus (general purpose)\n"
        "- x4plus Anime (max quality)\n"
        "- ESRNet (realistic photos)\n"
        "- x2plus (fast)\n\n"
        "~200 MB download\n"
        "2-5 minutes depending on connection\n\n"
        "Continue?"
    ),

    # ---- gui_methods.py  process_full_ai ----
    "warning_title": "Warning",
    "select_file_first": "Please select a file first",
    "select_model_first": "Please select an AI model",
    "starting_ai_status": "Starting AI processing...",
    "ai_header_log": "=== AI PROCESSING ===",
    "file_log": "File: {name}",
    "model_log": "Model: {model}",
    "processing_mode_log": "Processing mode: {mode}",
    "preparing_file_status": "Preparing file...",
    "converting_video_log": "Converting video to GIF...",
    "convert_error": "Error converting video to GIF",
    "video_converted_log": "Video converted: {name}",
    "extracting_frames_status": "Extracting frames...",
    "extracting_frames_log": "Extracting frames...",
    "extract_error": "Error extracting frames",
    "frames_extracted_log": "Frames extracted: {count}, FPS: {fps:.1f}",
    "applying_ai_status": "Applying AI with {mode}...",
    "upscale_error": "Error in AI upscaling",
    "ai_applied_log": "AI applied: {count} frames enhanced",
    "empty_frames_error": "Upscaled frames list is empty",
    "invalid_frame_log": "Invalid frame: {path}",
    "no_valid_frames_error": "No valid frames after upscaling",
    "valid_frames_log": "Valid frames: {count}",
    "color_prep_status": "Preparing color enhancements...",
    "color_prep_log": "Color enhancements will be applied to final GIF...",
    "creating_gif_status": "Creating final GIF...",
    "gif_created_log": "Base GIF created successfully: {size:.2f} MB",
    "applying_colors_status": "Applying color enhancements...",
    "applying_colors_log": "Applying color enhancements...",
    "gif_valid_log": "Valid GIF: {count} frames",
    "gif_invalid_warning": "GIF not valid for enhancements: {e}",
    "gif_corrupt_error": "Corrupt base GIF: {e}",
    "color_timeout_warning": "Color enhancement timeout (>60s)",
    "continue_no_colors": "Continuing without color enhancements...",
    "color_error_warning": "Enhancement error: {e}",
    "colors_applied_log": "Enhancements applied: {size:.2f} MB",
    "no_colors_needed": "No color enhancements needed",
    "skip_colors_warning": "Skipping color enhancements: {e}",
    "processing_completed_status": "Processing completed!",
    "processing_completed_header": "=== PROCESSING COMPLETED ===",
    "final_file_log": "Final file: {name}",
    "size_log": "Size: {size:.2f} MB",
    "generating_report_log": "Generating quality report...",
    "report_generated_log": "Quality report generated",
    "report_failed_log": "Could not generate quality report",
    "report_system_unavailable": "Report system not available",
    "report_error_log": "Quality report error: {e}",
    "success_title": "Success!",
    "ai_success_msg": (
        "Processing completed successfully!\n\n"
        "File: {name}\n"
        "Size: {size:.2f} MB\n"
        "Model: {model}\n"
        "Processed with: {mode}\n\n"
        "Enhancements applied: {enhanced}\n"
        "Quality report will open...\n"
        "Ready to fragment for Steam!"
    ),
    "critical_error_log": "CRITICAL ERROR: {e}",
    "error_title": "Error",
    "ai_error_msg": (
        "AI processing error:\n\n{e}\n\n"
        "Possible causes:\n"
        "- AI model not available\n"
        "- Incompatible GPU\n"
        "- Corrupt input frames\n"
        "- Insufficient memory\n\n"
        "Solutions:\n"
        "- Verify model is downloaded\n"
        "- Switch to CPU mode\n"
        "- Use a smaller file\n"
        "- Restart WorkshopArt"
    ),
    "gif_error_msg": (
        "Error creating final GIF:\n\n{e}\n\n"
        "Possible causes:\n"
        "- Corrupt AI frames\n"
        "- Insufficient memory\n"
        "- Source file too long\n\n"
        "Solutions:\n"
        "- Use a shorter file (<10s)\n"
        "- Close other applications\n"
        "- Restart WorkshopArt"
    ),
    "generic_error_msg": "Processing error:\n\n{e}",
    "temp_cleaned_log": "Temporary files cleaned",
    "temp_clean_warning": "Warning cleaning temp files: {e}",
    "confirm_process_title": "Confirm Processing",
    "confirm_process_msg": (
        "Process file with AI?\n\n"
        "File: {name}\n"
        "Model: {model}\n"
        "Processing: {mode}\n"
        "Quality: {quality}\n"
        "Estimated time: 2-10 minutes\n\n"
        "Color enhancements: {enhanced}\n"
        "Quality report will be generated\n\n"
        "Continue?"
    ),
    "yes_label": "Yes",
    "no_label": "No",

    # ---- gui_methods.py  enhance_colors_only ----
    "enhancing_colors_status": "Enhancing colors...",
    "applying_color_log": "Applying color enhancements...",
    "contrast_log": "Contrast: {val:.1f}",
    "saturation_log": "Saturation: {val:.1f}",
    "colors_improved_status": "Colors enhanced!",
    "enhanced_file_log": "Enhanced file: {name}",
    "colors_success_msg": (
        "Colors enhanced successfully!\n\n"
        "File: {name}\n"
        "Contrast: {contrast:.1f}\n"
        "Saturation: {saturation:.1f}"
    ),

    # ---- gui_methods.py  convert_mp4_to_gif ----
    "not_video_warning": (
        "Selected file is not a video.\n"
        "Supported formats: MP4, AVI, MOV, MKV, WEBM"
    ),
    "convert_window_title": "Convert Video to GIF",
    "conversion_title": "Video to GIF Conversion",
    "selected_file_label": "Selected file",
    "file_label": "File: {name}",
    "video_info_label": "Duration: {dur:.1f}s | FPS: {fps:.1f} | {size}",
    "video_read_error": "Could not read video info",
    "fps_for_gif": "GIF FPS",
    "custom_fps": "Custom FPS:",
    "quality_label": "Quality",
    "quality_fast": "Fast",
    "quality_balanced_label": "Balanced",
    "quality_high_label": "High quality",
    "options_label": "Options",
    "resize_steam": "Resize to 638x354 (Steam)",
    "auto_enhance_colors": "Auto-enhance colors",
    "estimated_size": "Estimated size: ~{size:.1f} MB",
    "estimated_size_unavailable": "Estimated size: Unavailable",
    "estimated_size_calculating": "Estimated size: Calculating...",
    "convert_to_gif_btn": "Convert to GIF",
    "cancel_btn": "Cancel",
    "converting_status": "Converting video to GIF...",
    "conversion_header_log": "=== MP4 -> GIF CONVERSION ===",
    "fps_log": "FPS: {fps}",
    "quality_log": "Quality: {quality}",
    "resize_log": "Resize: {resize}",
    "conversion_completed_status": "Conversion completed",
    "conversion_completed_full_status": "Conversion completed!",
    "gif_created_file_log": "GIF created: {name}",
    "final_size_log": "Final size: {size:.2f} MB",
    "conversion_success_title": "Conversion Successful!",
    "conversion_success_msg": (
        "Video converted to GIF!\n\n"
        "File: {name}\n"
        "FPS: {fps}\n"
        "Size: {size:.2f} MB\n"
        "Enhancements: {enhanced}\n\n"
        "Ready to process with AI or fragment"
    ),
    "conversion_failed": "Could not convert the video",
    "conversion_error_status": "Conversion error",
    "conversion_error_msg": "Error converting video:\n\n{e}",

    # ---- gui_methods.py  enhance_animation ----
    "enhance_anim_window_title": "Enhance Animation",
    "enhance_anim_title": "Animation Enhancement",
    "interpolation_60fps": "Interpolate to 60 FPS",
    "interpolation_desc": "Double/triple frames for smoother playback",
    "smooth_motion": "Motion Smoothing",
    "smooth_desc": "Apply soft motion blur",
    "optimize_playback": "Optimize Playback",
    "optimize_desc": "Normalize timing for stable playback",
    "apply_btn": "Apply",
    "interpolating_status": "Interpolating to 60 FPS...",
    "interpolation_header_log": "=== 60 FPS INTERPOLATION ===",
    "interpolation_success": "60 FPS interpolation completed!",
    "smoothing_status": "Applying smoothing...",
    "smoothing_header_log": "=== MOTION SMOOTHING ===",
    "smoothing_success": "Smoothing effect applied!",
    "optimizing_status": "Optimizing playback...",
    "optimizing_header_log": "=== PLAYBACK OPTIMIZATION ===",
    "optimizing_success": "Playback optimized!",
    "enhancement_completed_status": "Enhancement completed!",
    "enhanced_file_success_log": "Enhanced file: {name}",
    "no_changes_status": "No changes needed",
    "already_optimized_title": "Information",
    "already_optimized_msg": "The file is already optimized or needs no changes.",
    "enhancement_error_msg": "Enhancement error: {e}",

    # ---- gui_methods.py  optimization dialog ----
    "optimization_needed_title": "Optimization Recommended",
    "optimization_needed_msg": (
        "OPTIMIZATION NEEDED\n\n"
        "- Small fragments: {small}/5\n"
        "- Large fragments: {large}/5\n\n"
    ),
    "small_fragments_warning": (
        "Small fragments may be rejected by Steam.\n"
        "Optimization will make better use of available space.\n\n"
    ),
    "optimization_question": (
        "Apply automatic optimization?\n\n"
        "YES: Automatically improve quality\n"
        "NO: Keep fragments as they are"
    ),

    # ---- gui_methods.py  fragment reports ----
    "fragment_completed_title": "Fragmentation Completed",
    "fragment_completed_msg": (
        "FRAGMENTATION COMPLETED SUCCESSFULLY!\n\n"
        "FINAL STATISTICS:\n"
        "Optimal fragments: {optimal}/5\n"
        "Small fragments: {small}/5\n"
        "Large fragments: {large}/5\n\n"
        "FILES CREATED:\n"
    ),
    "fragment_total": "Total: {total:.2f} MB",
    "fragment_perfect": "PERFECT! All fragments are in the optimal range.\nSteam Workshop will get the best possible quality.",
    "fragment_excellent": "EXCELLENT! Most fragments are optimized.",
    "fragment_next_step": (
        "NEXT STEP:\n"
        "1. Upload the 5 files to Steam Workshop\n"
        "2. Open the browser console (F12)\n"
        "3. Run these commands:\n\n"
    ),
    "fragment_ready": "Ready to upload to Steam Workshop!",

    # ---- gui_methods.py  show_help ----
    "help_window_title": "Help - WorkshopArt",
    "close_btn": "Close",
    "help_text": """WORKSHOPART v1.0 - COMPLETE GUIDE

    STEP 1: SELECT FILE
    - Click "Select File"
    - Supported formats: MP4, AVI, MOV, GIF
    - Auto-detection will suggest the best AI model

    STEP 2: CONFIGURE AI
    - If first time, download models ("Download" button)
    - Model is automatically selected based on your content
    - Choose GPU for speed or CPU for compatibility

    STEP 3: PROCESS
    - Process with AI: Enhance entire file with 4x AI (best quality)
    - Colors Only: Adjust contrast/saturation without AI (faster)
    - Enhance Animation: Interpolate frames for smoother playback

    STEP 4: FRAGMENT
    - Split the GIF into 5 parts for Steam Workshop
    - Each part will be ~4.6 MB (auto-adjusted)
    - Automatically resizes to 638x354 px

    STEP 5: UPLOAD TO STEAM
    1. Go to Steam Workshop Uploader
    2. Upload the 5 .gif files created
    3. Open browser console (F12)
    4. Run the displayed commands

    TIPS:
    - Use "Auto-detect" for best automatic results
    - GPU is 5-10x faster than CPU
    - For long videos, trim to 5-10 seconds first
    - Adjust colors AFTER applying AI for best results

    AVAILABLE AI MODELS:
    - Anime Video v3: Perfect for gaming/anime (RECOMMENDED)
    - x4plus: General purpose, very versatile
    - x4plus Anime: Maximum quality for illustrations
    - ESRNet: Realistic photos and portraits
    - x2plus: 2x scaling, the fastest
    - Real-CUGAN: Specialized in anime (Bilibili)

    TROUBLESHOOTING:
    - If GPU not detected: Update drivers
    - If fragmentation fails: Install FFmpeg
    - If models won't download: Check firewall/antivirus
    - If processing is slow: Close other applications

    Full video tutorial:
    youtube.com/watch?v=BQ-9E7sFWc0""",

    # ---- gui_methods.py  on_closing / run ----
    "app_closed_log": "Application closed correctly",
    "welcome_log": "WorkshopArt v1.0 started",
    "welcome_modular_log": "Modular version with all features",
    "welcome_start_log": "Select a file to begin",
    "tutorial_opened_log": "Steam tutorial opened",
    "tutorial_error_log": "Error opening tutorial: {e}",

    # ---- gui_methods.py  fragment_for_steam ----
    "fragment_options_title": "Fragmentation Options",
    "fragment_options_msg": (
        "How do you want to fragment {name}?\n\n"
        "YES: Preview first\n"
        "NO: Fragment directly\n\n"
        "Recommended: Preview first"
    ),
    "preview_error_title": "Preview Error",
    "preview_error_msg": "Error creating preview:\n{e}\n\nFragmenting directly...",

    # ---- gui_methods.py  fragment_for_steam_direct ----
    "starting_fragment_status": "Starting fragmentation...",
    "direct_fragment_header_log": "=== DIRECT FRAGMENTATION ===",
    "converting_to_gif_log": "Converting to GIF...",
    "converting_to_gif_status": "Converting to GIF...",
    "convert_to_gif_error": "Error converting to GIF",
    "fragmenting_status": "Fragmenting into 5 parts...",
    "fragmenting_log": "Fragmenting for Steam Workshop...",
    "fragment_success_status": "Fragmentation completed!",
    "fragment_success_log": "Fragmentation completed successfully",
    "created_log": "Created: {name} ({size:.2f} MB)",
    "fragment_success_title": "Fragmentation Successful!",
    "fragment_success_msg": (
        "Fragmentation completed!\n\n"
        "Files created:\n{files}\n\n"
        "Total size: {total:.2f} MB\n\n"
        "Ready to upload to Steam Workshop!"
    ),
    "fragment_failed": "Fragmentation failed",
    "fragment_error_status": "Fragmentation error",
    "fragment_error_msg": "Fragmentation error:\n\n{e}",

    # ---- gui_methods.py  fragment_for_steam_ffmpeg_only ----
    "ffmpeg_fragment_header_log": "=== STEAM FRAGMENTATION (FFMPEG ONLY) ===",
    "verifying_file_status": "Verifying file...",
    "analyzing_fragments_status": "Analyzing fragments...",
    "fragment_status_optimal": "OPTIMAL",
    "fragment_status_small": "SMALL",
    "fragment_not_created": "Fragment {i} was not created",
    "optimizing_ffmpeg_status": "Optimizing with FFmpeg...",
    "optimizing_fragments_log": "Optimizing {count} fragments...",
    "optimizing_fragment_log": "Optimizing fragment {part}...",
    "optimized_log": "Optimized: {size:.2f} MB",
    "not_fully_optimized_log": "Could not fully optimize",
    "optimized_count_log": "Optimized: {done}/{total}",
    "ffmpeg_confirm_title": "FFmpeg Fragmentation",
    "ffmpeg_confirm_msg": (
        "Fragment using only FFmpeg?\n\n"
        "{name}\n"
        "Automatic optimization\n"
        "No AI processing (faster)\n\n"
        "Continue?"
    ),

    # ---- gui_methods.py  optimization internal ----
    "current_size_log": "   Current size: {current:.2f} MB, target: {target:.2f} MB",
    "ffmpeg_not_available": "   FFmpeg not available",
    "trying_strategies_log": "   Trying {count} FFmpeg strategies...",
    "strategy_result_log": "   FFmpeg strategy {i}: {size:.2f} MB",
    "strategy_success_log": "   FFmpeg strategy {i} SUCCESS: {old:.2f} -> {new:.2f} MB",
    "best_result_log": "   Best result so far: {size:.2f} MB",
    "strategy_error_log": "   Strategy {i} error: {msg}",
    "strategy_timeout_log": "   Strategy {i} timeout (>60s)",
    "strategy_exception_log": "   Error strategy {i}: {msg}",
    "ffmpeg_best_result_log": "   FFmpeg best result: {old:.2f} -> {new:.2f} MB (+{diff:.2f})",
    "ffmpeg_insufficient_log": "   FFmpeg improvement insufficient: +{diff:.2f} MB",
    "ffmpeg_no_strategy_log": "   FFmpeg: no strategy reached target",
    "ffmpeg_general_error_log": "   General FFmpeg error: {e}",
}

PT = {
    # ---- gui.py  Sidebar ----
    "app_title": "WorkshopArt",
    "version": "v1.0",
    "open_file": "Abrir arquivo",
    "process_ai": "Processar com IA",
    "colors_only": "Só cores",
    "mp4_to_gif": "MP4 para GIF",
    "enhance_animation": "Melhorar animação",
    "fragment_steam": "Fragmentar...",
    "optimize_size": "Otimizar para 5MB",
    "tip_open_file": "Carregue um vídeo, GIF ou imagem (MP4, AVI, MOV, GIF, JPG, PNG)",
    "tip_process_ai": "Amplie 4x com IA e melhore as cores",
    "tip_colors_only": "Melhore contraste e saturação sem upscaling",
    "tip_mp4_to_gif": "Converta um vídeo MP4 em GIF animado",
    "tip_enhance_animation": "Melhore FPS e fluidez da animação",
    "tip_fragment_steam": "Escolha o formato: Workshop, Artwork, Screenshot, Panorama, Grids...",
    "tip_optimize_size": "Reduza fragmentos abaixo do limite de 5MB mantendo a máxima qualidade",
    "download_models": "Baixar modelos de IA",
    "tip_download_models": "Baixe modelos Real-ESRGAN e Real-CUGAN (~200 MB)",
    "help": "Ajuda",
    "gpu_label": "GPU: ...",
    "ffmpeg_label": "FFmpeg: ...",
    "models_label": "Modelos: ...",

    # ---- gui.py  Center ----
    "drop_here": "Arraste um arquivo aqui",
    "supported_formats": "MP4 / AVI / MOV / GIF / JPG / PNG",
    "select_file_btn": "Selecionar arquivo",
    "log_title": "Registro",

    # ---- gui.py  Right panel ----
    "config_title": "Configurações",
    "ai_model": "Modelo de IA",
    "auto_detect_model": "Detectar modelo automaticamente",
    "processing_section": "Processamento",
    "use_gpu": "Usar GPU",
    "tip_use_gpu": "~10x mais rápido com GPU compatível",
    "quality_section": "Qualidade",
    "quality_high": "Alta",
    "quality_balanced": "Equilibrada",
    "visual_enhancements": "Melhorias visuais",
    "enhance_colors": "Melhorar cores",
    "enhance_animation_check": "Melhorar animação",
    "contrast": "Contraste",
    "saturation": "Saturação",
    "vibrance": "Vibrance",
    "sharpness": "Nitidez",
    "temperature": "Temperatura de cor",
    "model_info": "Info do modelo",
    "steam_workshop": "Steam Workshop",
    "steam_instructions": (
        "1. Fragmente seu GIF\n"
        "2. Envie os 5 arquivos\n"
        "3. Console F12 > comandos JS\n"
        "4. Publique no seu perfil"
    ),
    "view_tutorial": "Ver tutorial",

    # ---- gui.py  Hardware requirements ----
    "hw_requirements": "Requisitos de IA",
    "hw_info": (
        "GPU: NVIDIA / AMD com Vulkan\n"
        "(GTX 1060+ / RX 570+)\n"
        "RAM: 8 GB mínimo\n"
        "VRAM: 2 GB mínimo\n"
        "Sem GPU: processamento por CPU\n"
        "(muito mais lento, ~10x)"
    ),

    # ---- gui.py  Status bar ----
    "status_ready": "Pronto",
    "cancel_processing": "Cancelar",
    "cancelling": "Cancelando...",
    "cancel_requested_log": "Cancelamento solicitado pelo usuário",

    # ---- gui.py  Drag & drop ----
    "unsupported_format_title": "Formato não suportado",
    "unsupported_format_msg": "Arraste um arquivo MP4, AVI, MOV, MKV, WEBM, GIF, JPG ou PNG.",

    # ---- gui.py  Language selector ----
    "language_label": "Idioma",

    # ---- gui_methods.py  check_dependencies ----
    "checking_gpu": "Verificando GPU...",
    "gpu_detected": "GPU detectada: {info}",
    "gpu_not_detected_status": "Não detectada",
    "gpu_not_detected_log": "GPU não detectada, usando CPU",
    "ffmpeg_available_status": "Disponível",
    "ffmpeg_available_log": "FFmpeg disponível",
    "ffmpeg_not_found_status": "Não encontrado",
    "ffmpeg_not_found_log": "FFmpeg não encontrado - Alguns recursos limitados",
    "models_count_status": "{count}/5 modelos",
    "models_available_log": "{count} modelos disponíveis",
    "models_not_available_status": "Não disponíveis",
    "models_not_available_log": "Nenhum modelo disponível - Download necessário",
    "error_checking_deps": "Erro ao verificar dependências: {e}",

    # ---- gui_methods.py  model info ----
    "quality_score": "Qualidade: {quality}/10 | Velocidade: {speed}/10",
    "ideal_for": "Ideal para: {uses}",

    # ---- gui_methods.py  select_file ----
    "filetypes_media": "Arquivos de mídia",
    "filetypes_videos": "Vídeos",
    "filetypes_gifs": "GIFs",
    "filetypes_all": "Todos",
    "select_file_title": "Selecionar arquivo",

    # ---- gui_methods.py  show_file_info ----
    "size_label": "Tamanho: {size:.2f} MB",
    "dimensions_label": "Dimensões: {w}x{h}",
    "frames_label": "Frames: {n}",
    "fps_label": "FPS: {fps:.1f}",
    "duration_label": "Duração: {dur:.1f}s",
    "video_info_error": "Não foi possível ler as informações do vídeo",
    "type_label": "Tipo: {content_type} ({confidence:.0f}%)",
    "file_selected_log": "Arquivo selecionado: {name}",
    "file_loaded_status": "Arquivo carregado",
    "error_prefix": "Erro: {e}",
    "error_file_info_log": "Erro ao exibir informações do arquivo: {e}",

    # ---- gui_methods.py  analyze_content ----
    "analyzing_status": "Analisando conteúdo...",
    "analyzing_log": "Analisando tipo de conteúdo...",
    "type_detected_log": "Tipo detectado: {content_type}",
    "model_recommended_log": "Modelo recomendado: {model}",
    "analysis_completed_status": "Análise concluída",
    "analysis_error_log": "Erro ao analisar conteúdo: {e}",
    "analysis_error_status": "Erro na análise",

    # ---- gui_methods.py  download_models ----
    "preparing_download_status": "Preparando download...",
    "download_header_log": "=== DOWNLOAD DE MODELOS ===",
    "downloading_models_log": "Baixando 5 modelos Real-ESRGAN...",
    "download_completed_log": "Download concluído",
    "models_downloaded_status": "Modelos baixados!",
    "download_completed_header_log": "=== DOWNLOAD CONCLUÍDO ===",
    "models_available_count_log": "Modelos disponíveis: {count}/5",
    "download_success_title": "Sucesso!",
    "download_success_msg": (
        "Download concluído!\n\n"
        "{check} {count} modelos disponíveis\n"
        "Local: {location}\n\n"
        "Você já pode processar com IA!"
    ),
    "download_error_status": "Erro no download",
    "download_error_log": "Erro ao baixar modelos",
    "download_error_title": "Erro",
    "download_error_msg": (
        "Erro ao baixar modelos.\n\n"
        "Possíveis causas:\n"
        "- Sem conexão com a internet\n"
        "- Firewall bloqueando o GitHub\n"
        "- Espaço insuficiente em disco\n\n"
        "Tente baixar manualmente em:\n"
        "github.com/xinntao/Real-ESRGAN/releases"
    ),
    "confirm_download_title": "Confirmar Download",
    "confirm_download_msg": (
        "Baixar todos os modelos de IA?\n\n"
        "5 modelos especializados:\n"
        "- Anime Video v3 (gaming/anime)\n"
        "- x4plus (uso geral)\n"
        "- x4plus Anime (máxima qualidade)\n"
        "- ESRNet (fotos realistas)\n"
        "- x2plus (rápido)\n\n"
        "~200 MB de download\n"
        "2-5 minutos dependendo da conexão\n\n"
        "Continuar?"
    ),

    # ---- gui_methods.py  process_full_ai ----
    "warning_title": "Aviso",
    "select_file_first": "Primeiro selecione um arquivo",
    "select_model_first": "Selecione um modelo de IA",
    "starting_ai_status": "Iniciando processamento com IA...",
    "ai_header_log": "=== PROCESSAMENTO COM IA ===",
    "file_log": "Arquivo: {name}",
    "model_log": "Modelo: {model}",
    "processing_mode_log": "Modo de processamento: {mode}",
    "preparing_file_status": "Preparando arquivo...",
    "converting_video_log": "Convertendo vídeo para GIF...",
    "convert_error": "Erro ao converter vídeo para GIF",
    "video_converted_log": "Vídeo convertido: {name}",
    "extracting_frames_status": "Extraindo frames...",
    "extracting_frames_log": "Extraindo frames...",
    "extract_error": "Erro ao extrair frames",
    "frames_extracted_log": "Frames extraídos: {count}, FPS: {fps:.1f}",
    "applying_ai_status": "Aplicando IA com {mode}...",
    "upscale_error": "Erro no upscaling com IA",
    "ai_applied_log": "IA aplicada: {count} frames melhorados",
    "empty_frames_error": "A lista de frames processados está vazia",
    "invalid_frame_log": "Frame inválido: {path}",
    "no_valid_frames_error": "Nenhum frame válido após o upscaling",
    "valid_frames_log": "Frames válidos: {count}",
    "color_prep_status": "Preparando melhorias de cor...",
    "color_prep_log": "Melhorias de cor serão aplicadas ao GIF final...",
    "creating_gif_status": "Criando GIF final...",
    "gif_created_log": "GIF base criado com sucesso: {size:.2f} MB",
    "applying_colors_status": "Aplicando melhorias de cor...",
    "applying_colors_log": "Aplicando melhorias de cor...",
    "gif_valid_log": "GIF válido: {count} frames",
    "gif_invalid_warning": "GIF inválido para melhorias: {e}",
    "gif_corrupt_error": "GIF base corrompido: {e}",
    "color_timeout_warning": "Timeout nas melhorias de cor (>60s)",
    "continue_no_colors": "Continuando sem melhorias de cor...",
    "color_error_warning": "Erro nas melhorias: {e}",
    "colors_applied_log": "Melhorias aplicadas: {size:.2f} MB",
    "no_colors_needed": "Nenhuma melhoria de cor necessária",
    "skip_colors_warning": "Pulando melhorias de cor: {e}",
    "processing_completed_status": "Processamento concluído!",
    "processing_completed_header": "=== PROCESSAMENTO CONCLUÍDO ===",
    "final_file_log": "Arquivo final: {name}",
    "size_log": "Tamanho: {size:.2f} MB",
    "generating_report_log": "Gerando relatório de qualidade...",
    "report_generated_log": "Relatório de qualidade gerado",
    "report_failed_log": "Não foi possível gerar o relatório de qualidade",
    "report_system_unavailable": "Sistema de relatórios não disponível",
    "report_error_log": "Erro no relatório de qualidade: {e}",
    "success_title": "Sucesso!",
    "ai_success_msg": (
        "Processamento concluído com sucesso!\n\n"
        "Arquivo: {name}\n"
        "Tamanho: {size:.2f} MB\n"
        "Modelo: {model}\n"
        "Processado com: {mode}\n\n"
        "Melhorias aplicadas: {enhanced}\n"
        "O relatório de qualidade será aberto...\n"
        "Pronto para fragmentar para o Steam!"
    ),
    "critical_error_log": "ERRO CRÍTICO: {e}",
    "error_title": "Erro",
    "ai_error_msg": (
        "Erro no processamento com IA:\n\n{e}\n\n"
        "Possíveis causas:\n"
        "- Modelo de IA não disponível\n"
        "- GPU incompatível\n"
        "- Frames de entrada corrompidos\n"
        "- Memória insuficiente\n\n"
        "Soluções:\n"
        "- Verifique se o modelo está baixado\n"
        "- Mude para modo CPU\n"
        "- Use um arquivo menor\n"
        "- Reinicie o WorkshopArt"
    ),
    "gif_error_msg": (
        "Erro ao criar GIF final:\n\n{e}\n\n"
        "Possíveis causas:\n"
        "- Frames de IA corrompidos\n"
        "- Memória insuficiente\n"
        "- Arquivo original muito longo\n\n"
        "Soluções:\n"
        "- Use um arquivo mais curto (<10s)\n"
        "- Feche outros aplicativos\n"
        "- Reinicie o WorkshopArt"
    ),
    "generic_error_msg": "Erro no processamento:\n\n{e}",
    "temp_cleaned_log": "Arquivos temporários limpos",
    "temp_clean_warning": "Aviso ao limpar temporários: {e}",
    "confirm_process_title": "Confirmar Processamento",
    "confirm_process_msg": (
        "Processar arquivo com IA?\n\n"
        "Arquivo: {name}\n"
        "Modelo: {model}\n"
        "Processamento: {mode}\n"
        "Qualidade: {quality}\n"
        "Tempo estimado: 2-10 minutos\n\n"
        "Melhorias de cor: {enhanced}\n"
        "Relatório de qualidade será gerado\n\n"
        "Continuar?"
    ),
    "yes_label": "Sim",
    "no_label": "Não",

    # ---- gui_methods.py  enhance_colors_only ----
    "enhancing_colors_status": "Melhorando cores...",
    "applying_color_log": "Aplicando melhorias de cor...",
    "contrast_log": "Contraste: {val:.1f}",
    "saturation_log": "Saturação: {val:.1f}",
    "colors_improved_status": "Cores melhoradas!",
    "enhanced_file_log": "Arquivo melhorado: {name}",
    "colors_success_msg": (
        "Cores melhoradas com sucesso!\n\n"
        "Arquivo: {name}\n"
        "Contraste: {contrast:.1f}\n"
        "Saturação: {saturation:.1f}"
    ),

    # ---- gui_methods.py  convert_mp4_to_gif ----
    "not_video_warning": (
        "O arquivo selecionado não é um vídeo.\n"
        "Formatos suportados: MP4, AVI, MOV, MKV, WEBM"
    ),
    "convert_window_title": "Converter Vídeo para GIF",
    "conversion_title": "Conversão de Vídeo para GIF",
    "selected_file_label": "Arquivo selecionado",
    "file_label": "Arquivo: {name}",
    "video_info_label": "Duração: {dur:.1f}s | FPS: {fps:.1f} | {size}",
    "video_read_error": "Não foi possível ler as informações do vídeo",
    "fps_for_gif": "FPS para o GIF",
    "custom_fps": "FPS personalizado:",
    "quality_label": "Qualidade",
    "quality_fast": "Rápido",
    "quality_balanced_label": "Equilibrado",
    "quality_high_label": "Alta qualidade",
    "options_label": "Opções",
    "resize_steam": "Redimensionar para 638x354 (Steam)",
    "auto_enhance_colors": "Melhorar cores automaticamente",
    "estimated_size": "Tamanho estimado: ~{size:.1f} MB",
    "estimated_size_unavailable": "Tamanho estimado: Indisponível",
    "estimated_size_calculating": "Tamanho estimado: Calculando...",
    "convert_to_gif_btn": "Converter para GIF",
    "cancel_btn": "Cancelar",
    "converting_status": "Convertendo vídeo para GIF...",
    "conversion_header_log": "=== CONVERSÃO MP4 -> GIF ===",
    "fps_log": "FPS: {fps}",
    "quality_log": "Qualidade: {quality}",
    "resize_log": "Redimensionar: {resize}",
    "conversion_completed_status": "Conversão concluída",
    "conversion_completed_full_status": "Conversão concluída!",
    "gif_created_file_log": "GIF criado: {name}",
    "final_size_log": "Tamanho final: {size:.2f} MB",
    "conversion_success_title": "Conversão Bem-sucedida!",
    "conversion_success_msg": (
        "Vídeo convertido para GIF!\n\n"
        "Arquivo: {name}\n"
        "FPS: {fps}\n"
        "Tamanho: {size:.2f} MB\n"
        "Melhorias: {enhanced}\n\n"
        "Pronto para processar com IA ou fragmentar"
    ),
    "conversion_failed": "Não foi possível converter o vídeo",
    "conversion_error_status": "Erro na conversão",
    "conversion_error_msg": "Erro ao converter vídeo:\n\n{e}",

    # ---- gui_methods.py  enhance_animation ----
    "enhance_anim_window_title": "Melhorar Animação",
    "enhance_anim_title": "Melhoria de Animação",
    "interpolation_60fps": "Interpolar para 60 FPS",
    "interpolation_desc": "Duplica/triplica frames para maior fluidez",
    "smooth_motion": "Suavização de Movimento",
    "smooth_desc": "Aplica motion blur suave",
    "optimize_playback": "Otimizar Reprodução",
    "optimize_desc": "Normaliza o timing para reprodução estável",
    "apply_btn": "Aplicar",
    "interpolating_status": "Interpolando para 60 FPS...",
    "interpolation_header_log": "=== INTERPOLAÇÃO PARA 60 FPS ===",
    "interpolation_success": "Interpolação para 60 FPS concluída!",
    "smoothing_status": "Aplicando suavização...",
    "smoothing_header_log": "=== SUAVIZAÇÃO DE MOVIMENTO ===",
    "smoothing_success": "Efeito de suavização aplicado!",
    "optimizing_status": "Otimizando reprodução...",
    "optimizing_header_log": "=== OTIMIZAÇÃO DE REPRODUÇÃO ===",
    "optimizing_success": "Reprodução otimizada!",
    "enhancement_completed_status": "Melhoria concluída!",
    "enhanced_file_success_log": "Arquivo melhorado: {name}",
    "no_changes_status": "Nenhuma alteração necessária",
    "already_optimized_title": "Informação",
    "already_optimized_msg": "O arquivo já está otimizado ou não precisa de alterações.",
    "enhancement_error_msg": "Erro na melhoria: {e}",

    # ---- gui_methods.py  optimization dialog ----
    "optimization_needed_title": "Otimização Recomendada",
    "optimization_needed_msg": (
        "OTIMIZAÇÃO NECESSÁRIA\n\n"
        "- Fragmentos pequenos: {small}/5\n"
        "- Fragmentos grandes: {large}/5\n\n"
    ),
    "small_fragments_warning": (
        "Fragmentos pequenos podem ser rejeitados pelo Steam.\n"
        "A otimização aproveitará melhor o espaço disponível.\n\n"
    ),
    "optimization_question": (
        "Aplicar otimização automática?\n\n"
        "SIM: Melhora a qualidade automaticamente\n"
        "NÃO: Mantém os fragmentos como estão"
    ),

    # ---- gui_methods.py  fragment reports ----
    "fragment_completed_title": "Fragmentação Concluída",
    "fragment_completed_msg": (
        "FRAGMENTAÇÃO CONCLUÍDA COM SUCESSO!\n\n"
        "ESTATÍSTICAS FINAIS:\n"
        "Fragmentos ótimos: {optimal}/5\n"
        "Fragmentos pequenos: {small}/5\n"
        "Fragmentos grandes: {large}/5\n\n"
        "ARQUIVOS CRIADOS:\n"
    ),
    "fragment_total": "Total: {total:.2f} MB",
    "fragment_perfect": "PERFEITO! Todos os fragmentos estão no intervalo ideal.\nO Steam Workshop receberá a melhor qualidade possível.",
    "fragment_excellent": "EXCELENTE! A maioria dos fragmentos está otimizada.",
    "fragment_next_step": (
        "PRÓXIMO PASSO:\n"
        "1. Envie os 5 arquivos para o Steam Workshop\n"
        "2. Abra o console do navegador (F12)\n"
        "3. Execute estes comandos:\n\n"
    ),
    "fragment_ready": "Pronto para enviar ao Steam Workshop!",

    # ---- gui_methods.py  show_help ----
    "help_window_title": "Ajuda - WorkshopArt",
    "close_btn": "Fechar",
    "help_text": """WORKSHOPART v1.0 - GUIA COMPLETO

    PASSO 1: SELECIONAR ARQUIVO
    - Clique em "Selecionar Arquivo"
    - Formatos suportados: MP4, AVI, MOV, GIF
    - A detecção automática sugerirá o melhor modelo de IA

    PASSO 2: CONFIGURAR IA
    - Se for a primeira vez, baixe os modelos (botão "Baixar")
    - O modelo é selecionado automaticamente conforme o conteúdo
    - Escolha GPU para velocidade ou CPU para compatibilidade

    PASSO 3: PROCESSAR
    - Processar com IA: Melhora todo o arquivo com IA 4x (melhor qualidade)
    - Só Cores: Ajusta contraste/saturação sem IA (mais rápido)
    - Melhorar Animação: Interpola frames para maior fluidez

    PASSO 4: FRAGMENTAR
    - Divide o GIF em 5 partes para o Steam Workshop
    - Cada parte terá ~4,6 MB (ajuste automático)
    - Redimensiona para 638x354 px automaticamente

    PASSO 5: ENVIAR PARA O STEAM
    1. Acesse o Steam Workshop Uploader
    2. Envie os 5 arquivos .gif criados
    3. Abra o console do navegador (F12)
    4. Execute os comandos exibidos

    DICAS:
    - Use "Detectar automaticamente" para melhores resultados
    - GPU é 5-10x mais rápido que CPU
    - Para vídeos longos, recorte para 5-10 segundos primeiro
    - Ajuste as cores DEPOIS de aplicar a IA para melhor resultado

    MODELOS DE IA DISPONÍVEIS:
    - Anime Video v3: Perfeito para gaming/anime (RECOMENDADO)
    - x4plus: Uso geral, muito versátil
    - x4plus Anime: Máxima qualidade para ilustrações
    - ESRNet: Fotos realistas e retratos
    - x2plus: Escala 2x, o mais rápido
    - Real-CUGAN: Especializado em anime (Bilibili)

    SOLUÇÃO DE PROBLEMAS:
    - Se a GPU não for detectada: Atualize os drivers
    - Se a fragmentação falhar: Instale o FFmpeg
    - Se os modelos não baixarem: Verifique o firewall/antivírus
    - Se o processo estiver lento: Feche outros aplicativos

    Tutorial completo em vídeo:
    youtube.com/watch?v=BQ-9E7sFWc0""",

    # ---- gui_methods.py  on_closing / run ----
    "app_closed_log": "Aplicativo fechado corretamente",
    "welcome_log": "WorkshopArt v2.0 iniciado",
    "welcome_modular_log": "Versão modular com todas as funções",
    "welcome_start_log": "Selecione um arquivo para começar",
    "tutorial_opened_log": "Tutorial do Steam aberto",
    "tutorial_error_log": "Erro ao abrir tutorial: {e}",

    # ---- gui_methods.py  fragment_for_steam ----
    "fragment_options_title": "Opções de Fragmentação",
    "fragment_options_msg": (
        "Como deseja fragmentar {name}?\n\n"
        "SIM: Ver preview primeiro\n"
        "NÃO: Fragmentar diretamente\n\n"
        "Recomendado: Ver preview primeiro"
    ),
    "preview_error_title": "Erro no Preview",
    "preview_error_msg": "Erro ao criar preview:\n{e}\n\nFragmentando diretamente...",

    # ---- gui_methods.py  fragment_for_steam_direct ----
    "starting_fragment_status": "Iniciando fragmentação...",
    "direct_fragment_header_log": "=== FRAGMENTAÇÃO DIRETA ===",
    "converting_to_gif_log": "Convertendo para GIF...",
    "converting_to_gif_status": "Convertendo para GIF...",
    "convert_to_gif_error": "Erro ao converter para GIF",
    "fragmenting_status": "Fragmentando em 5 partes...",
    "fragmenting_log": "Fragmentando para o Steam Workshop...",
    "fragment_success_status": "Fragmentação concluída!",
    "fragment_success_log": "Fragmentação concluída com sucesso",
    "created_log": "Criado: {name} ({size:.2f} MB)",
    "fragment_success_title": "Fragmentação Bem-sucedida!",
    "fragment_success_msg": (
        "Fragmentação concluída!\n\n"
        "Arquivos criados:\n{files}\n\n"
        "Tamanho total: {total:.2f} MB\n\n"
        "Prontos para enviar ao Steam Workshop!"
    ),
    "fragment_failed": "A fragmentação falhou",
    "fragment_error_status": "Erro na fragmentação",
    "fragment_error_msg": "Erro na fragmentação:\n\n{e}",

    # ---- gui_methods.py  fragment_for_steam_ffmpeg_only ----
    "ffmpeg_fragment_header_log": "=== FRAGMENTAÇÃO STEAM (SOMENTE FFMPEG) ===",
    "verifying_file_status": "Verificando arquivo...",
    "analyzing_fragments_status": "Analisando fragmentos...",
    "fragment_status_optimal": "ÓTIMO",
    "fragment_status_small": "PEQUENO",
    "fragment_not_created": "Fragmento {i} não foi criado",
    "optimizing_ffmpeg_status": "Otimizando com FFmpeg...",
    "optimizing_fragments_log": "Otimizando {count} fragmentos...",
    "optimizing_fragment_log": "Otimizando fragmento {part}...",
    "optimized_log": "Otimizado: {size:.2f} MB",
    "not_fully_optimized_log": "Não foi possível otimizar completamente",
    "optimized_count_log": "Otimizados: {done}/{total}",
    "ffmpeg_confirm_title": "Fragmentação FFmpeg",
    "ffmpeg_confirm_msg": (
        "Fragmentar usando somente FFmpeg?\n\n"
        "{name}\n"
        "Otimização automática\n"
        "Sem processamento de IA (mais rápido)\n\n"
        "Continuar?"
    ),

    # ---- gui_methods.py  optimization internal ----
    "current_size_log": "   Tamanho atual: {current:.2f} MB, objetivo: {target:.2f} MB",
    "ffmpeg_not_available": "   FFmpeg não disponível",
    "trying_strategies_log": "   Testando {count} estratégias FFmpeg...",
    "strategy_result_log": "   Estratégia FFmpeg {i}: {size:.2f} MB",
    "strategy_success_log": "   Estratégia FFmpeg {i} SUCESSO: {old:.2f} -> {new:.2f} MB",
    "best_result_log": "   Melhor resultado até agora: {size:.2f} MB",
    "strategy_error_log": "   Estratégia {i} erro: {msg}",
    "strategy_timeout_log": "   Estratégia {i} timeout (>60s)",
    "strategy_exception_log": "   Erro na estratégia {i}: {msg}",
    "ffmpeg_best_result_log": "   FFmpeg melhor resultado: {old:.2f} -> {new:.2f} MB (+{diff:.2f})",
    "ffmpeg_insufficient_log": "   Melhoria FFmpeg insuficiente: +{diff:.2f} MB",
    "ffmpeg_no_strategy_log": "   FFmpeg: nenhuma estratégia atingiu o objetivo",
    "ffmpeg_general_error_log": "   Erro geral FFmpeg: {e}",
}

_LANGS = {"ES": ES, "EN": EN, "PT": PT}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def t(key: str, fallback: str = None, **kwargs) -> str:
    """Return the translated string for *key* in the current language.
    Supports ``{placeholder}`` formatting via **kwargs.
    Falls back to ES, then to fallback, then to the raw key.
    """
    text = _LANGS.get(_current_lang, ES).get(key)
    if text is None:
        text = ES.get(key, fallback or key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass
    return text


def set_language(lang: str):
    """Set the active language ('ES', 'EN', or 'PT')."""
    global _current_lang
    if lang in _LANGS:
        _current_lang = lang


def get_language() -> str:
    """Return the current language code."""
    return _current_lang
