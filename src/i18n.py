"""
i18n.py - Sistema de internacionalizacion (ES/EN)
Diccionarios simples, sin dependencias externas.
"""

_current_lang = "ES"

# ---------------------------------------------------------------------------
# Diccionarios
# ---------------------------------------------------------------------------

ES = {
    # ---- gui.py  Sidebar ----
    "app_title": "WorkshopArt PRO",
    "version": "v3.0",
    "open_file": "Abrir archivo",
    "process_ai": "Procesar con IA",
    "colors_only": "Solo colores",
    "mp4_to_gif": "MP4 a GIF",
    "enhance_animation": "Mejorar animacion",
    "fragment_steam": "Fragmentar Steam",
    "fragment_showcase": "Showcase (presets)",
    "optimize_size": "Optimizar a 5MB",
    "tip_open_file": "Carga un video, GIF o imagen (MP4, AVI, MOV, GIF, JPG, PNG)",
    "tip_process_ai": "Escala 4x con IA y mejora colores",
    "tip_colors_only": "Mejora contraste y saturacion sin upscaling",
    "tip_mp4_to_gif": "Convierte un video MP4 a GIF animado",
    "tip_enhance_animation": "Mejora FPS y fluidez de la animacion",
    "tip_fragment_steam": "Divide el GIF en 5 partes para Steam Workshop",
    "tip_fragment_showcase": "Elige preset: Featured 630, 506x506, Screenshot 638x354, Workshop 5x150, Panorama 5x630, 4-grid...",
    "tip_optimize_size": "Reduce fragmentos por debajo del limite de 5MB manteniendo maxima calidad",
    "download_models": "Descargar modelos IA",
    "tip_download_models": "Descarga modelos Real-ESRGAN y Real-CUGAN (~200 MB)",
    "help": "Ayuda",
    "gpu_label": "GPU: ...",
    "ffmpeg_label": "FFmpeg: ...",
    "models_label": "Modelos: ...",

    # ---- gui.py  Center ----
    "drop_here": "Arrastra un archivo aqui",
    "supported_formats": "MP4 / AVI / MOV / GIF / JPG / PNG",
    "select_file_btn": "Seleccionar archivo",
    "log_title": "Registro",

    # ---- gui.py  Right panel ----
    "config_title": "Configuracion",
    "ai_model": "Modelo IA",
    "auto_detect_model": "Auto-detectar modelo",
    "processing_section": "Procesamiento",
    "use_gpu": "Usar GPU",
    "tip_use_gpu": "Procesa ~10x mas rapido si tienes GPU compatible",
    "quality_section": "Calidad",
    "quality_high": "Alta",
    "quality_balanced": "Balanceada",
    "visual_enhancements": "Mejoras visuales",
    "enhance_colors": "Mejorar colores",
    "enhance_animation_check": "Mejorar animacion",
    "contrast": "Contraste",
    "saturation": "Saturacion",
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
        "RAM: 8 GB minimo\n"
        "VRAM: 2 GB minimo\n"
        "Sin GPU: procesamiento por CPU\n"
        "(mucho mas lento, ~10x)"
    ),

    # ---- gui.py  Status bar ----
    "status_ready": "Listo",
    "cancel_processing": "Cancelar",
    "cancelling": "Cancelando...",
    "cancel_requested_log": "Cancelacion solicitada por el usuario",

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
    "size_label": "Tamano: {size:.2f} MB",
    "dimensions_label": "Dimensiones: {w}x{h}",
    "frames_label": "Frames: {n}",
    "fps_label": "FPS: {fps:.1f}",
    "duration_label": "Duracion: {dur:.1f}s",
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
    "analysis_completed_status": "Analisis completado",
    "analysis_error_log": "Error analizando contenido: {e}",
    "analysis_error_status": "Error en analisis",

    # ---- gui_methods.py  download_models ----
    "preparing_download_status": "Preparando descarga...",
    "download_header_log": "=== DESCARGA DE MODELOS ===",
    "downloading_models_log": "Descargando 5 modelos de Real-ESRGAN...",
    "download_completed_log": "Descarga completada",
    "models_downloaded_status": "¡Modelos descargados!",
    "download_completed_header_log": "=== DESCARGA COMPLETADA ===",
    "models_available_count_log": "Modelos disponibles: {count}/5",
    "download_success_title": "¡Exito!",
    "download_success_msg": (
        "¡Descarga completada!\n\n"
        "{check} {count} modelos disponibles\n"
        "Ubicacion: {location}\n\n"
        "¡Ya puedes procesar con IA!"
    ),
    "download_error_status": "Error en descarga",
    "download_error_log": "Error descargando modelos",
    "download_error_title": "Error",
    "download_error_msg": (
        "Error descargando modelos.\n\n"
        "Posibles causas:\n"
        "- Sin conexion a internet\n"
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
        "- x4plus Anime (maxima calidad)\n"
        "- ESRNet (fotos realistas)\n"
        "- x2plus (rapido)\n\n"
        "~200 MB de descarga\n"
        "2-5 minutos segun conexion\n\n"
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
    "frames_extracted_log": "Frames extraidos: {count}, FPS: {fps:.1f}",
    "applying_ai_status": "Aplicando IA con {mode}...",
    "upscale_error": "Error en el upscaling con IA",
    "ai_applied_log": "IA aplicada: {count} frames mejorados",
    "empty_frames_error": "Lista de frames upscaleados esta vacia",
    "invalid_frame_log": "Frame no valido: {path}",
    "no_valid_frames_error": "No hay frames validos despues del upscaling",
    "valid_frames_log": "Frames validos: {count}",
    "color_prep_status": "Preparando mejoras de color...",
    "color_prep_log": "Mejoras de color se aplicaran al GIF final...",
    "creating_gif_status": "Creando GIF final...",
    "gif_created_log": "GIF base creado correctamente: {size:.2f} MB",
    "applying_colors_status": "Aplicando mejoras de color...",
    "applying_colors_log": "Aplicando mejoras de color...",
    "gif_valid_log": "GIF valido: {count} frames",
    "gif_invalid_warning": "GIF no valido para mejoras: {e}",
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
    "size_log": "Tamano: {size:.2f} MB",
    "generating_report_log": "Generando reporte de calidad...",
    "report_generated_log": "Reporte de calidad generado",
    "report_failed_log": "No se pudo generar reporte de calidad",
    "report_system_unavailable": "Sistema de reportes no disponible",
    "report_error_log": "Error en reporte de calidad: {e}",
    "success_title": "¡Exito!",
    "ai_success_msg": (
        "¡Procesamiento completado exitosamente!\n\n"
        "Archivo: {name}\n"
        "Tamano: {size:.2f} MB\n"
        "Modelo: {model}\n"
        "Procesado con: {mode}\n\n"
        "Mejoras aplicadas: {enhanced}\n"
        "Se abrira el reporte de calidad...\n"
        "¡Listo para fragmentar para Steam!"
    ),
    "critical_error_log": "ERROR CRITICO: {e}",
    "error_title": "Error",
    "ai_error_msg": (
        "Error en procesamiento con IA:\n\n{e}\n\n"
        "Posibles causas:\n"
        "- Modelo de IA no disponible\n"
        "- GPU no compatible\n"
        "- Frames de entrada corruptos\n"
        "- Memoria insuficiente\n\n"
        "Soluciones:\n"
        "- Verifica que el modelo este descargado\n"
        "- Cambia a modo CPU\n"
        "- Usa archivo mas pequeno\n"
        "- Reinicia WorkshopArt PRO"
    ),
    "gif_error_msg": (
        "Error creando GIF final:\n\n{e}\n\n"
        "Posibles causas:\n"
        "- Frames de IA corruptos\n"
        "- Memoria insuficiente\n"
        "- Archivo original demasiado largo\n\n"
        "Soluciones:\n"
        "- Usar archivo mas corto (<10s)\n"
        "- Cerrar otras aplicaciones\n"
        "- Reiniciar WorkshopArt PRO"
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
        "Se generara reporte de calidad\n\n"
        "¿Continuar?"
    ),
    "yes_label": "Si",
    "no_label": "No",

    # ---- gui_methods.py  enhance_colors_only ----
    "enhancing_colors_status": "Mejorando colores...",
    "applying_color_log": "Aplicando mejoras de color...",
    "contrast_log": "Contraste: {val:.1f}",
    "saturation_log": "Saturacion: {val:.1f}",
    "colors_improved_status": "¡Colores mejorados!",
    "enhanced_file_log": "Archivo mejorado: {name}",
    "colors_success_msg": (
        "¡Colores mejorados exitosamente!\n\n"
        "Archivo: {name}\n"
        "Contraste: {contrast:.1f}\n"
        "Saturacion: {saturation:.1f}"
    ),

    # ---- gui_methods.py  convert_mp4_to_gif ----
    "not_video_warning": (
        "El archivo seleccionado no es un video.\n"
        "Formatos soportados: MP4, AVI, MOV, MKV, WEBM"
    ),
    "convert_window_title": "Convertir Video a GIF",
    "conversion_title": "Conversion Video a GIF",
    "selected_file_label": "Archivo seleccionado",
    "file_label": "Archivo: {name}",
    "video_info_label": "Duracion: {dur:.1f}s | FPS: {fps:.1f} | {size}",
    "video_read_error": "No se pudo leer info del video",
    "fps_for_gif": "FPS para el GIF",
    "custom_fps": "FPS personalizado:",
    "quality_label": "Calidad",
    "quality_fast": "Rapido",
    "quality_balanced_label": "Balanceado",
    "quality_high_label": "Alta calidad",
    "options_label": "Opciones",
    "resize_steam": "Redimensionar a 638x354 (Steam)",
    "auto_enhance_colors": "Mejorar colores automaticamente",
    "estimated_size": "Tamano estimado: ~{size:.1f} MB",
    "estimated_size_unavailable": "Tamano estimado: No disponible",
    "estimated_size_calculating": "Tamano estimado: Calculando...",
    "convert_to_gif_btn": "Convertir a GIF",
    "cancel_btn": "Cancelar",
    "converting_status": "Convirtiendo video a GIF...",
    "conversion_header_log": "=== CONVERSION MP4 -> GIF ===",
    "fps_log": "FPS: {fps}",
    "quality_log": "Calidad: {quality}",
    "resize_log": "Redimensionar: {resize}",
    "conversion_completed_status": "Conversion completada",
    "conversion_completed_full_status": "¡Conversion completada!",
    "gif_created_file_log": "GIF creado: {name}",
    "final_size_log": "Tamano final: {size:.2f} MB",
    "conversion_success_title": "¡Conversion Exitosa!",
    "conversion_success_msg": (
        "¡Video convertido a GIF!\n\n"
        "Archivo: {name}\n"
        "FPS: {fps}\n"
        "Tamano: {size:.2f} MB\n"
        "Mejoras: {enhanced}\n\n"
        "Listo para procesar con IA o fragmentar"
    ),
    "conversion_failed": "No se pudo convertir el video",
    "conversion_error_status": "Error en conversion",
    "conversion_error_msg": "Error convirtiendo video:\n\n{e}",

    # ---- gui_methods.py  enhance_animation ----
    "enhance_anim_window_title": "Mejorar Animacion",
    "enhance_anim_title": "Mejora de Animacion",
    "interpolation_60fps": "Interpolacion a 60 FPS",
    "interpolation_desc": "Duplica/triplica frames para mayor fluidez",
    "smooth_motion": "Suavizado de Movimiento",
    "smooth_desc": "Aplica motion blur suave",
    "optimize_playback": "Optimizar Reproduccion",
    "optimize_desc": "Normaliza timing para reproduccion estable",
    "apply_btn": "Aplicar",
    "interpolating_status": "Interpolando a 60 FPS...",
    "interpolation_header_log": "=== INTERPOLACION A 60 FPS ===",
    "interpolation_success": "¡Interpolacion a 60 FPS completada!",
    "smoothing_status": "Aplicando suavizado...",
    "smoothing_header_log": "=== SUAVIZADO DE MOVIMIENTO ===",
    "smoothing_success": "¡Efecto de suavizado aplicado!",
    "optimizing_status": "Optimizando reproduccion...",
    "optimizing_header_log": "=== OPTIMIZACION DE REPRODUCCION ===",
    "optimizing_success": "¡Reproduccion optimizada!",
    "enhancement_completed_status": "¡Mejora completada!",
    "enhanced_file_success_log": "Archivo mejorado: {name}",
    "no_changes_status": "No se requieren cambios",
    "already_optimized_title": "Informacion",
    "already_optimized_msg": "El archivo ya esta optimizado o no requiere cambios.",
    "enhancement_error_msg": "Error en mejora: {e}",

    # ---- gui_methods.py  optimization dialog ----
    "optimization_needed_title": "Optimizacion Recomendada",
    "optimization_needed_msg": (
        "OPTIMIZACION NECESARIA\n\n"
        "- Fragmentos pequenos: {small}/5\n"
        "- Fragmentos grandes: {large}/5\n\n"
    ),
    "small_fragments_warning": (
        "Los fragmentos pequenos pueden ser rechazados por Steam.\n"
        "La optimizacion aprovechara mejor el espacio disponible.\n\n"
    ),
    "optimization_question": (
        "¿Aplicar optimizacion automatica?\n\n"
        "SI: Mejora la calidad automaticamente\n"
        "NO: Mantiene fragmentos como estan"
    ),

    # ---- gui_methods.py  fragment reports ----
    "fragment_completed_title": "Fragmentacion Completada",
    "fragment_completed_msg": (
        "¡FRAGMENTACION COMPLETADA EXITOSAMENTE!\n\n"
        "ESTADISTICAS FINALES:\n"
        "Fragmentos optimos: {optimal}/5\n"
        "Fragmentos pequenos: {small}/5\n"
        "Fragmentos grandes: {large}/5\n\n"
        "ARCHIVOS CREADOS:\n"
    ),
    "fragment_total": "Total: {total:.2f} MB",
    "fragment_perfect": "¡PERFECTO! Todos los fragmentos estan en el rango optimo.\nSteam Workshop obtendra la maxima calidad posible.",
    "fragment_excellent": "¡EXCELENTE! La mayoria de fragmentos estan optimizados.",
    "fragment_next_step": (
        "SIGUIENTE PASO:\n"
        "1. Sube los 5 archivos a Steam Workshop\n"
        "2. Abre la consola del navegador (F12)\n"
        "3. Ejecuta estos comandos:\n\n"
    ),
    "fragment_ready": "¡Listo para subir a Steam Workshop!",

    # ---- gui_methods.py  show_help ----
    "help_window_title": "Ayuda - WorkshopArt PRO",
    "close_btn": "Cerrar",
    "help_text": """WORKSHOPART PRO v3.0 - GUIA COMPLETA

    PASO 1: SELECCIONAR ARCHIVO
    - Haz clic en "Seleccionar Archivo"
    - Formatos soportados: MP4, AVI, MOV, GIF
    - La deteccion automatica sugerira el mejor modelo de IA

    PASO 2: CONFIGURAR IA
    - Si es la primera vez, descarga los modelos (boton "Descargar")
    - El modelo se selecciona automaticamente segun tu contenido
    - Elige GPU para velocidad o CPU para compatibilidad

    PASO 3: PROCESAR
    - Procesar con IA: Mejora todo el archivo con IA 4x (mejor calidad)
    - Solo Colores: Ajusta contraste/saturacion sin IA (mas rapido)
    - Mejorar Animacion: Interpola frames para mayor fluidez

    PASO 4: FRAGMENTAR
    - Divide el GIF en 5 partes para Steam Workshop
    - Cada parte sera ~4.6 MB (ajuste automatico)
    - Redimensiona a 638x354 px automaticamente

    PASO 5: SUBIR A STEAM
    1. Ve a Steam Workshop Uploader
    2. Sube los 5 archivos .gif creados
    3. Abre la consola del navegador (F12)
    4. Ejecuta los comandos mostrados

    CONSEJOS PRO:
    - Usa "Auto-detectar" para mejores resultados automaticos
    - GPU es 5-10x mas rapido que CPU
    - Para videos largos, recorta a 5-10 segundos primero
    - Ajusta colores DESPUES de aplicar IA para mejor resultado

    MODELOS DE IA DISPONIBLES:
    - Anime Video v3: Perfecto para gaming/anime (RECOMENDADO)
    - x4plus: Uso general, muy versatil
    - x4plus Anime: Maxima calidad para ilustraciones
    - ESRNet: Fotos realistas y retratos
    - x2plus: Escalado 2x, el mas rapido
    - Real-CUGAN: Especializado en anime (Bilibili)

    SOLUCION DE PROBLEMAS:
    - Si la GPU no se detecta: Actualiza drivers
    - Si falla la fragmentacion: Instala FFmpeg
    - Si los modelos no descargan: Verifica firewall/antivirus
    - Si el proceso es lento: Cierra otras aplicaciones

    Tutorial completo en video:
    youtube.com/watch?v=BQ-9E7sFWc0""",

    # ---- gui_methods.py  on_closing / run ----
    "app_closed_log": "Aplicacion cerrada correctamente",
    "welcome_log": "WorkshopArt PRO v3.0 iniciado",
    "welcome_modular_log": "Version modular con todas las funciones",
    "welcome_start_log": "Selecciona un archivo para comenzar",
    "tutorial_opened_log": "Tutorial de Steam abierto",
    "tutorial_error_log": "Error abriendo tutorial: {e}",

    # ---- gui_methods.py  fragment_for_steam ----
    "fragment_options_title": "Opciones de Fragmentacion",
    "fragment_options_msg": (
        "¿Como quieres fragmentar {name}?\n\n"
        "SI: Ver preview primero\n"
        "NO: Fragmentar directamente\n\n"
        "Recomendado: Ver preview primero"
    ),
    "preview_error_title": "Error en Preview",
    "preview_error_msg": "Error creando preview:\n{e}\n\nFragmentando directamente...",

    # ---- gui_methods.py  fragment_for_steam_direct ----
    "starting_fragment_status": "Iniciando fragmentacion...",
    "direct_fragment_header_log": "=== FRAGMENTACION DIRECTA ===",
    "converting_to_gif_log": "Convirtiendo a GIF...",
    "converting_to_gif_status": "Convirtiendo a GIF...",
    "convert_to_gif_error": "Error convirtiendo a GIF",
    "fragmenting_status": "Fragmentando en 5 partes...",
    "fragmenting_log": "Fragmentando para Steam Workshop...",
    "fragment_success_status": "¡Fragmentacion completada!",
    "fragment_success_log": "Fragmentacion completada exitosamente",
    "created_log": "Creado: {name} ({size:.2f} MB)",
    "fragment_success_title": "¡Fragmentacion Exitosa!",
    "fragment_success_msg": (
        "¡Fragmentacion completada!\n\n"
        "Archivos creados:\n{files}\n\n"
        "Tamano total: {total:.2f} MB\n\n"
        "¡Listos para subir a Steam Workshop!"
    ),
    "fragment_failed": "La fragmentacion fallo",
    "fragment_error_status": "Error en fragmentacion",
    "fragment_error_msg": "Error en fragmentacion:\n\n{e}",

    # ---- gui_methods.py  fragment_for_steam_ffmpeg_only ----
    "ffmpeg_fragment_header_log": "=== FRAGMENTACION STEAM (SOLO FFMPEG) ===",
    "verifying_file_status": "Verificando archivo...",
    "analyzing_fragments_status": "Analizando fragmentos...",
    "fragment_status_optimal": "OPTIMO",
    "fragment_status_small": "PEQUENO",
    "fragment_not_created": "No se creo fragmento {i}",
    "optimizing_ffmpeg_status": "Optimizando con FFmpeg...",
    "optimizing_fragments_log": "Optimizando {count} fragmentos...",
    "optimizing_fragment_log": "Optimizando fragmento {part}...",
    "optimized_log": "Optimizado: {size:.2f} MB",
    "not_fully_optimized_log": "No se pudo optimizar completamente",
    "optimized_count_log": "Optimizados: {done}/{total}",
    "ffmpeg_confirm_title": "Fragmentacion FFmpeg",
    "ffmpeg_confirm_msg": (
        "¿Fragmentar usando solo FFmpeg?\n\n"
        "{name}\n"
        "Optimizacion automatica\n"
        "Sin procesamiento IA (mas rapido)\n\n"
        "¿Continuar?"
    ),

    # ---- gui_methods.py  optimization internal ----
    "current_size_log": "   Tamano actual: {current:.2f} MB, objetivo: {target:.2f} MB",
    "ffmpeg_not_available": "   FFmpeg no disponible",
    "trying_strategies_log": "   Probando {count} estrategias FFmpeg...",
    "strategy_result_log": "   Estrategia FFmpeg {i}: {size:.2f} MB",
    "strategy_success_log": "   FFmpeg estrategia {i} EXITO: {old:.2f} -> {new:.2f} MB",
    "best_result_log": "   Mejor resultado hasta ahora: {size:.2f} MB",
    "strategy_error_log": "   Estrategia {i} error: {msg}",
    "strategy_timeout_log": "   Estrategia {i} timeout (>60s)",
    "strategy_exception_log": "   Error estrategia {i}: {msg}",
    "ffmpeg_best_result_log": "   FFmpeg mejor resultado: {old:.2f} -> {new:.2f} MB (+{diff:.2f})",
    "ffmpeg_insufficient_log": "   Mejora FFmpeg insuficiente: +{diff:.2f} MB",
    "ffmpeg_no_strategy_log": "   FFmpeg: ninguna estrategia alcanzo objetivo",
    "ffmpeg_general_error_log": "   Error general FFmpeg: {e}",

    # ---- gui_methods.py  show_help ----
    "help_window_title": "Ayuda - WorkshopArt PRO",
    "close_btn": "Cerrar",
}

EN = {
    # ---- gui.py  Sidebar ----
    "app_title": "WorkshopArt PRO",
    "version": "v3.0",
    "open_file": "Open file",
    "process_ai": "Process with AI",
    "colors_only": "Colors only",
    "mp4_to_gif": "MP4 to GIF",
    "enhance_animation": "Enhance animation",
    "fragment_steam": "Fragment for Steam",
    "fragment_showcase": "Showcase (presets)",
    "optimize_size": "Optimize to 5MB",
    "tip_open_file": "Load a video, GIF or image (MP4, AVI, MOV, GIF, JPG, PNG)",
    "tip_process_ai": "4x upscale with AI and enhance colors",
    "tip_colors_only": "Enhance contrast and saturation without upscaling",
    "tip_mp4_to_gif": "Convert an MP4 video to an animated GIF",
    "tip_enhance_animation": "Improve FPS and animation smoothness",
    "tip_fragment_steam": "Split the GIF into 5 parts for Steam Workshop",
    "tip_fragment_showcase": "Pick preset: Featured 630, 506x506, Screenshot 638x354, Workshop 5x150, Panorama 5x630, 4-grid...",
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
        "- Restart WorkshopArt PRO"
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
        "- Restart WorkshopArt PRO"
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
    "help_window_title": "Help - WorkshopArt PRO",
    "close_btn": "Close",
    "help_text": """WORKSHOPART PRO v3.0 - COMPLETE GUIDE

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

    PRO TIPS:
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
    "welcome_log": "WorkshopArt PRO v3.0 started",
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

    # ---- gui_methods.py  show_help ----
    "help_window_title": "Help - WorkshopArt PRO",
    "close_btn": "Close",
}

_LANGS = {"ES": ES, "EN": EN}


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
    """Set the active language ('ES' or 'EN')."""
    global _current_lang
    if lang in _LANGS:
        _current_lang = lang


def get_language() -> str:
    """Return the current language code."""
    return _current_lang
