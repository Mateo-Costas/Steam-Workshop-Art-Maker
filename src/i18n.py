"""
i18n.py - Interface texts in Spanish, English and Portuguese (Brazil).

Every text is one entry of _STRINGS: key -> (ES, EN, PT). Keeping the three
languages side by side makes a missing translation impossible. Texts may
contain {placeholders}, filled by t(key, name=value).

Usage:
    from i18n import t, set_language
    set_language("EN")
    button.configure(text=t("fragment_now"))
    t("info_size", mb=1.5)   # -> "Size: 1.50 MB"
"""

_STRINGS = {
    # ---- Main window -------------------------------------------------------
    "help": ("Ayuda", "Help", "Ajuda"),
    "tip_help": ("Guía completa (F1)", "Full guide (F1)", "Guia completo (F1)"),
    "font_scale": ("Tamaño de texto", "Text size", "Tamanho do texto"),
    "tip_font_scale": ("Tamaño del texto (requiere reiniciar)", "Text size (restart required)",
                       "Tamanho do texto (requer reiniciar)"),
    "restart_for_scale": ("El nuevo tamaño de texto se aplicará al reiniciar la aplicación.",
                          "The new text size will be applied when the app restarts.",
                          "O novo tamanho de texto será aplicado ao reiniciar o aplicativo."),
    "step_file": ("Archivo", "File", "Arquivo"),
    "step_process": ("Procesar", "Process", "Processar"),
    "step_fragment": ("Fragmentar", "Fragment", "Fragmentar"),
    "step_upload": ("Subir", "Upload", "Enviar"),
    "log_title": ("Log de proceso", "Process log", "Log do processo"),
    "status_ready": ("Listo", "Ready", "Pronto"),
    "cancel_btn": ("Cancelar", "Cancel", "Cancelar"),
    "cancelling": ("Cancelando...", "Cancelling...", "Cancelando..."),
    "cancel_requested_log": ("Cancelación solicitada", "Cancellation requested", "Cancelamento solicitado"),
    "close_btn": ("Cerrar", "Close", "Fechar"),
    "yes": ("Sí", "Yes", "Sim"),
    "no": ("No", "No", "Não"),
    "warning_title": ("Aviso", "Warning", "Aviso"),
    "error_title": ("Error", "Error", "Erro"),
    "models_label": ("Modelos", "Models", "Modelos"),
    "available": ("OK", "OK", "OK"),
    "not_detected": ("No detectada", "Not detected", "Não detectada"),
    "not_found": ("No encontrado", "Not found", "Não encontrado"),
    "unsupported_format_title": ("Formato no soportado", "Unsupported format", "Formato não suportado"),
    "unsupported_format_msg": ("El archivo arrastrado no es un formato multimedia soportado.",
                               "The dropped file is not a supported media format.",
                               "O arquivo arrastado não é um formato de mídia suportado."),
    "status_file_loaded": ("Archivo cargado", "File loaded", "Arquivo carregado"),
    "status_done": ("Completado", "Done", "Concluído"),
    "status_error": ("Error", "Error", "Erro"),
    "status_cancelled": ("Cancelado", "Cancelled", "Cancelado"),
    "status_extracting": ("Extrayendo frames...", "Extracting frames...", "Extraindo frames..."),
    "status_building_gif": ("Creando GIF...", "Building GIF...", "Criando GIF..."),
    "status_colors": ("Mejorando colores...", "Adjusting colors...", "Ajustando cores..."),
    "status_converting": ("Convirtiendo video a GIF...", "Converting video to GIF...",
                          "Convertendo vídeo em GIF..."),
    "status_rife": ("Interpolando con RIFE...", "Interpolating with RIFE...", "Interpolando com RIFE..."),
    "status_fragmenting": ("Fragmentando...", "Fragmenting...", "Fragmentando..."),
    "status_optimizing": ("Optimizando...", "Optimizing...", "Otimizando..."),
    "saved_in": ("Guardado en:\n{path}", "Saved to:\n{path}", "Salvo em:\n{path}"),

    # ---- Step 1: file ----------------------------------------------------------
    "drop_here": ("Arrastra tu archivo aquí", "Drop your file here", "Arraste seu arquivo aqui"),
    "supported_formats": ("GIF · MP4 · MOV · MKV · WEBM · AVI · JPG · PNG · WEBP",
                          "GIF · MP4 · MOV · MKV · WEBM · AVI · JPG · PNG · WEBP",
                          "GIF · MP4 · MOV · MKV · WEBM · AVI · JPG · PNG · WEBP"),
    "select_file_btn": ("Seleccionar archivo", "Select file", "Selecionar arquivo"),
    "tip_open_file": ("Abrir un archivo multimedia (Ctrl+O)", "Open a media file (Ctrl+O)",
                      "Abrir um arquivo de mídia (Ctrl+O)"),
    "is_anime_question": ("¿Tu contenido es anime?", "Is your content anime?", "Seu conteúdo é anime?"),
    "anime_yes": ("Sí, anime", "Yes, anime", "Sim, anime"),
    "anime_no": ("No", "No", "Não"),
    "tip_is_anime": ("Elige el tipo de contenido para recomendar el mejor modelo de IA",
                     "Choose the content type to pick the best AI model",
                     "Escolha o tipo de conteúdo para recomendar o melhor modelo de IA"),
    "recent_files": ("Recientes:", "Recent:", "Recentes:"),
    "file_missing": ("El archivo ya no existe:\n{path}", "The file no longer exists:\n{path}",
                     "O arquivo não existe mais:\n{path}"),
    "media_files": ("Archivos multimedia", "Media files", "Arquivos de mídia"),
    "videos": ("Videos", "Videos", "Vídeos"),
    "images": ("Imágenes", "Images", "Imagens"),
    "all_files": ("Todos", "All files", "Todos"),
    "loading_preview": ("Cargando preview...", "Loading preview...", "Carregando preview..."),
    "preview_unavailable": ("(preview no disponible)", "(preview unavailable)", "(preview indisponível)"),
    "info_size": ("Tamaño: {mb:.2f} MB", "Size: {mb:.2f} MB", "Tamanho: {mb:.2f} MB"),
    "info_dims": ("Dimensiones: {w}x{h}", "Dimensions: {w}x{h}", "Dimensões: {w}x{h}"),
    "info_frames": ("Frames: {n}", "Frames: {n}", "Frames: {n}"),
    "info_duration": ("Duración: {s:.1f} s", "Duration: {s:.1f} s", "Duração: {s:.1f} s"),
    "info_unreadable": ("No se pudo leer el archivo: {err}", "Could not read the file: {err}",
                        "Não foi possível ler o arquivo: {err}"),
    "info_suggested": ("Formato sugerido: {preset}", "Suggested format: {preset}",
                       "Formato sugerido: {preset}"),

    # ---- Step 2: process -------------------------------------------------------
    "ai_model": ("Modelo de IA", "AI model", "Modelo de IA"),
    "model_scores": ("Calidad: {q}/10 | Velocidad: {s}/10", "Quality: {q}/10 | Speed: {s}/10",
                     "Qualidade: {q}/10 | Velocidade: {s}/10"),
    "model_desc_realesr-animevideov3-x2": ("Anime/juegos 2x · rápido", "Anime/games 2x · fast",
                                           "Anime/jogos 2x · rápido"),
    "model_desc_realesr-animevideov3-x3": ("Anime/juegos 3x · equilibrado", "Anime/games 3x · balanced",
                                           "Anime/jogos 3x · equilibrado"),
    "model_desc_realesr-animevideov3-x4": ("Anime/juegos 4x · alta calidad", "Anime/games 4x · high quality",
                                           "Anime/jogos 4x · alta qualidade"),
    "model_desc_realesrgan-x4plus-anime": ("Ilustración anime 4x · máxima calidad",
                                           "Anime illustration 4x · best quality",
                                           "Ilustração anime 4x · máxima qualidade"),
    "model_desc_realesrgan-x4plus": ("Uso general 4x · versátil", "General purpose 4x · versatile",
                                     "Uso geral 4x · versátil"),
    "model_desc_realesrnet-x4plus": ("Fotos realistas 4x", "Realistic photos 4x", "Fotos realistas 4x"),
    "model_desc_realesr-general-x4v3": ("General 4x · ligero y rápido", "General 4x · light and fast",
                                        "Geral 4x · leve e rápido"),
    "model_desc_cugan-se-2x-no-denoise": ("CUGAN anime 2x · sin reducción de ruido", "CUGAN anime 2x · no denoise",
                                          "CUGAN anime 2x · sem redução de ruído"),
    "model_desc_cugan-se-2x-denoise3": ("CUGAN anime 2x · reducción de ruido fuerte",
                                        "CUGAN anime 2x · strong denoise",
                                        "CUGAN anime 2x · redução de ruído forte"),
    "model_desc_cugan-se-3x-no-denoise": ("CUGAN anime 3x", "CUGAN anime 3x", "CUGAN anime 3x"),
    "model_desc_cugan-se-4x-no-denoise": ("CUGAN anime 4x · máxima calidad", "CUGAN anime 4x · best quality",
                                          "CUGAN anime 4x · máxima qualidade"),
    "processing_section": ("Procesamiento", "Processing", "Processamento"),
    "use_gpu": ("Usar GPU", "Use GPU", "Usar GPU"),
    "tip_use_gpu": ("La GPU es de 5 a 10 veces más rápida que la CPU",
                    "The GPU is 5 to 10 times faster than the CPU",
                    "A GPU é de 5 a 10 vezes mais rápida que a CPU"),
    "enhance_colors": ("Aplicar ajustes de color tras la IA", "Apply color adjustments after the AI",
                       "Aplicar ajustes de cor após a IA"),
    "tip_enhance_colors": ("Usa los ajustes de la derecha al terminar la IA y en el pipeline",
                           "Uses the adjustments on the right after the AI and in the pipeline",
                           "Usa os ajustes da direita ao terminar a IA e no pipeline"),
    "live_preview": ("Preview en vivo", "Live preview", "Preview ao vivo"),
    "preview_no_file": ("Carga un GIF o imagen para ver el preview", "Load a GIF or image to see the preview",
                        "Carregue um GIF ou imagem para ver o preview"),
    "color_adjustments": ("Ajustes de color", "Color adjustments", "Ajustes de cor"),
    "contrast": ("Contraste", "Contrast", "Contraste"),
    "saturation": ("Saturación", "Saturation", "Saturação"),
    "vibrance": ("Vibrance", "Vibrance", "Vibrância"),
    "sharpness": ("Nitidez", "Sharpness", "Nitidez"),
    "temperature": ("Temperatura", "Temperature", "Temperatura"),
    "process_ai": ("Procesar con IA", "Process with AI", "Processar com IA"),
    "tip_process_ai": ("Mejorar la resolución con Real-ESRGAN / Real-CUGAN",
                       "Improve the resolution with Real-ESRGAN / Real-CUGAN",
                       "Melhorar a resolução com Real-ESRGAN / Real-CUGAN"),
    "colors_only": ("Solo colores", "Colors only", "Só cores"),
    "tip_colors_only": ("Aplicar los ajustes de color sin IA (rápido)",
                        "Apply the color adjustments without AI (fast)",
                        "Aplicar os ajustes de cor sem IA (rápido)"),
    "mp4_to_gif": ("Video → GIF", "Video → GIF", "Vídeo → GIF"),
    "tip_mp4_to_gif": ("Convertir un video a GIF con recorte y FPS a elegir",
                       "Convert a video to GIF choosing trim and FPS",
                       "Converter um vídeo em GIF escolhendo corte e FPS"),
    "enhance_animation": ("Mejorar animación", "Smooth animation", "Suavizar animação"),
    "tip_enhance_animation": ("Interpolar frames con RIFE para una animación más fluida",
                              "Interpolate frames with RIFE for a smoother animation",
                              "Interpolar frames com RIFE para uma animação mais fluida"),
    "download_models": ("Descargar modelos", "Download models", "Baixar modelos"),
    "tip_download_models": ("Descargar los modelos de IA (unos 90 MB)", "Download the AI models (about 90 MB)",
                            "Baixar os modelos de IA (cerca de 90 MB)"),
    "download_models_confirm": (
        "Se descargarán los modelos de IA (unos 90 MB):\n\n"
        "• Real-ESRGAN: Anime Video v3 (2x, 3x, 4x), x4plus Anime y x4plus\n"
        "• Real-CUGAN: modelos anime SE (2x, 3x, 4x)\n\n¿Continuar?",
        "The AI models will be downloaded (about 90 MB):\n\n"
        "• Real-ESRGAN: Anime Video v3 (2x, 3x, 4x), x4plus Anime and x4plus\n"
        "• Real-CUGAN: SE anime models (2x, 3x, 4x)\n\nContinue?",
        "Os modelos de IA serão baixados (cerca de 90 MB):\n\n"
        "• Real-ESRGAN: Anime Video v3 (2x, 3x, 4x), x4plus Anime e x4plus\n"
        "• Real-CUGAN: modelos anime SE (2x, 3x, 4x)\n\nContinuar?"),
    "models_ready": ("Modelos descargados", "Models downloaded", "Modelos baixados"),
    "models_ready_msg": ("{n} modelos listos en:\n{path}", "{n} models ready in:\n{path}",
                         "{n} modelos prontos em:\n{path}"),
    "models_download_failed": (
        "No se pudieron descargar los modelos.\n\nComprueba la conexión a internet o el firewall.\n"
        "Detalles en el log de proceso.",
        "The models could not be downloaded.\n\nCheck your internet connection or firewall.\n"
        "Details in the process log.",
        "Não foi possível baixar os modelos.\n\nVerifique a conexão com a internet ou o firewall.\n"
        "Detalhes no log do processo."),
    "select_file_first": ("Primero selecciona un archivo", "Select a file first", "Primeiro selecione um arquivo"),
    "select_model_first": ("No hay modelos de IA. Usa 'Descargar modelos' primero.",
                           "There are no AI models. Use 'Download models' first.",
                           "Não há modelos de IA. Use 'Baixar modelos' primeiro."),
    "confirm_ai": (
        "¿Procesar con IA?\n\nArchivo: {file}\nModelo: {model}\nModo: {mode}\n"
        "Mejorar colores: {colors}\n\nPuede tardar varios minutos.",
        "Process with AI?\n\nFile: {file}\nModel: {model}\nMode: {mode}\n"
        "Adjust colors: {colors}\n\nIt may take several minutes.",
        "Processar com IA?\n\nArquivo: {file}\nModelo: {model}\nModo: {mode}\n"
        "Ajustar cores: {colors}\n\nPode levar vários minutos."),
    "ai_done": (
        "Procesamiento completado.\n\nArchivo: {file}\nTamaño: {mb:.2f} MB\n\n"
        "Ya puedes fragmentarlo en el paso 3.",
        "Processing finished.\n\nFile: {file}\nSize: {mb:.2f} MB\n\nYou can now fragment it in step 3.",
        "Processamento concluído.\n\nArquivo: {file}\nTamanho: {mb:.2f} MB\n\n"
        "Agora você pode fragmentá-lo na etapa 3."),
    "err_ai_failed": ("El procesamiento con IA ha fallado. Prueba con otro modelo o desactiva la GPU.",
                      "AI processing failed. Try another model or turn off the GPU.",
                      "O processamento com IA falhou. Tente outro modelo ou desative a GPU."),
    "err_extract_frames": ("No se pudieron extraer los frames", "The frames could not be extracted",
                           "Não foi possível extrair os frames"),
    "err_build_gif": ("No se pudo crear el GIF", "The GIF could not be created", "Não foi possível criar o GIF"),
    "colors_need_gif": ("Convierte primero el video a GIF (botón Video → GIF).",
                        "Convert the video to GIF first (Video → GIF button).",
                        "Converta primeiro o vídeo em GIF (botão Vídeo → GIF)."),
    "err_colors": ("No se pudieron aplicar los ajustes de color. Revisa el log de proceso.",
                   "The color adjustments could not be applied. Check the process log.",
                   "Não foi possível aplicar os ajustes de cor. Veja o log do processo."),
    "not_a_video": ("El archivo seleccionado no es un video.", "The selected file is not a video.",
                    "O arquivo selecionado não é um vídeo."),
    "convert_title": ("Convertir video a GIF", "Convert video to GIF", "Converter vídeo em GIF"),
    "gif_fps": ("FPS del GIF", "GIF FPS", "FPS do GIF"),
    "custom_fps": ("Otro valor (1-50):", "Other value (1-50):", "Outro valor (1-50):"),
    "invalid_fps": ("FPS no válido", "Invalid FPS", "FPS inválido"),
    "trim": ("Recorte", "Trim", "Corte"),
    "trim_range": ("De {a:.1f} s a {b:.1f} s → {d:.1f} s de GIF", "From {a:.1f} s to {b:.1f} s → {d:.1f} s of GIF",
                   "De {a:.1f} s a {b:.1f} s → {d:.1f} s de GIF"),
    "gif_size": ("Tamaño", "Size", "Tamanho"),
    "shrink_to_steam": ("Reducir a {w} px de ancho (Steam)", "Shrink to {w} px wide (Steam)",
                        "Reduzir para {w} px de largura (Steam)"),
    "shrink_hint": ("Desmárcalo para conservar la resolución original (útil para Panorama).",
                    "Untick it to keep the original resolution (useful for Panorama).",
                    "Desmarque para manter a resolução original (útil para Panorama)."),
    "apply_color_sliders": ("Aplicar también los ajustes de color del paso 2",
                            "Also apply the color adjustments from step 2",
                            "Aplicar também os ajustes de cor da etapa 2"),
    "size_estimate": ("Tamaño estimado: ~{mb:.1f} MB", "Estimated size: ~{mb:.1f} MB",
                      "Tamanho estimado: ~{mb:.1f} MB"),
    "convert_btn": ("Convertir a GIF", "Convert to GIF", "Converter em GIF"),
    "err_convert": ("No se pudo convertir el video. Revisa el log de proceso.",
                    "The video could not be converted. Check the process log.",
                    "Não foi possível converter o vídeo. Veja o log do processo."),
    "rife_needs_animation": ("RIFE necesita un GIF o un video.", "RIFE needs a GIF or a video.",
                             "O RIFE precisa de um GIF ou de um vídeo."),
    "rife_missing": ("RIFE no está instalado. Reinicia la aplicación para que se descargue automáticamente.",
                     "RIFE is not installed. Restart the app to download it automatically.",
                     "O RIFE não está instalado. Reinicie o aplicativo para baixá-lo automaticamente."),
    "rife_multiplier": ("Multiplicar frames:", "Multiply frames:", "Multiplicar frames:"),
    "rife_tta": ("Calidad máxima (TTA), unas 4 veces más lento", "Maximum quality (TTA), about 4 times slower",
                 "Qualidade máxima (TTA), cerca de 4 vezes mais lento"),
    "rife_fps_note": ("Los GIF no pasan de 50 FPS: si el resultado los supera se ajusta sin cambiar la velocidad.",
                      "GIFs cannot go above 50 FPS: faster results are adjusted without changing the speed.",
                      "GIFs não passam de 50 FPS: se o resultado passar, é ajustado sem mudar a velocidade."),
    "apply_rife": ("Aplicar RIFE", "Apply RIFE", "Aplicar RIFE"),

    # ---- Step 3: fragment ------------------------------------------------------
    "section_workshop_banner": ("WORKSHOP SHOWCASE · BANNER ANIMADO", "WORKSHOP SHOWCASE · ANIMATED BANNER",
                                "WORKSHOP SHOWCASE · BANNER ANIMADO"),
    "section_artwork": ("ARTWORK SHOWCASE", "ARTWORK SHOWCASE", "ARTWORK SHOWCASE"),
    "section_screenshot": ("SCREENSHOT SHOWCASE", "SCREENSHOT SHOWCASE", "SCREENSHOT SHOWCASE"),
    "section_workshop_grid": ("WORKSHOP SHOWCASE · CUADRADOS", "WORKSHOP SHOWCASE · SQUARES",
                              "WORKSHOP SHOWCASE · QUADRADOS"),
    "most_used": ("MÁS USADO", "MOST USED", "MAIS USADO"),
    "dims_free_height": ("{widths} px de ancho · alto libre", "{widths} px wide · any height",
                         "{widths} px de largura · altura livre"),
    "preset_workshop_5part": ("Workshop Showcase · 5 partes", "Workshop Showcase · 5 parts",
                              "Workshop Showcase · 5 partes"),
    "note_workshop_5part": ("Una imagen 638×354 cortada en 5 columnas: el formato más usado para GIF de perfil",
                            "A 638×354 image cut into 5 columns: the most used format for profile GIFs",
                            "Uma imagem 638×354 cortada em 5 colunas: o formato mais usado para GIFs de perfil"),
    "preset_artwork_2part": ("Artwork · principal + lateral", "Artwork · main + side", "Artwork · principal + lateral"),
    "note_artwork_2part": ("Diseño clásico de 2 columnas; acepta GIF e imágenes",
                           "Classic 2-column layout; works with GIFs and images",
                           "Layout clássico de 2 colunas; aceita GIFs e imagens"),
    "preset_featured_630": ("Featured Artwork · 1 hueco grande", "Featured Artwork · 1 large slot",
                            "Featured Artwork · 1 espaço grande"),
    "note_featured_630": ("Imagen o GIF grande en la parte superior del perfil",
                          "A large image or GIF at the top of the profile",
                          "Imagem ou GIF grande no topo do perfil"),
    "preset_artwork_single_630": ("Artwork único · 16:9", "Single artwork · 16:9", "Artwork único · 16:9"),
    "note_artwork_single_630": ("Un único GIF o imagen en proporción 16:9", "A single GIF or image in 16:9",
                                "Um único GIF ou imagem em 16:9"),
    "preset_artwork_4grid": ("Artwork 4-grid · cuadrícula", "Artwork 4-grid", "Artwork 4-grid"),
    "note_artwork_4grid": ("Cuatro cuadrados iguales formando una tira", "Four equal squares forming a strip",
                           "Quatro quadrados iguais formando uma faixa"),
    "preset_panorama_5_630": ("Panorama · banner ultra-ancho", "Panorama · ultra-wide banner",
                              "Panorama · banner ultralargo"),
    "note_panorama_5_630": ("Banner horizontal de 5 piezas (se sube con el truco de dimensiones)",
                            "5-piece horizontal banner (uploaded with the size trick)",
                            "Banner horizontal de 5 peças (enviado com o truque de dimensões)"),
    "preset_screenshot_638": ("Screenshot · 1 hueco", "Screenshot · 1 slot", "Screenshot · 1 espaço"),
    "note_screenshot_638": ("Una sola captura animada en el showcase de capturas",
                            "A single animated screenshot in the screenshot showcase",
                            "Uma única captura animada no showcase de capturas"),
    "preset_screenshot_4grid": ("Screenshot · 4 piezas", "Screenshot · 4 pieces", "Screenshot · 4 peças"),
    "note_screenshot_4grid": ("Cuatro capturas formando una tira horizontal",
                              "Four screenshots forming a horizontal strip",
                              "Quatro capturas formando uma faixa horizontal"),
    "preset_workshop_5slot_150": ("Workshop · 5 cuadrados de 150 px", "Workshop · 5 squares, 150 px",
                                  "Workshop · 5 quadrados de 150 px"),
    "note_workshop_5slot_150": ("Tamaño de subida recomendado, sin bordes negros",
                                "Recommended upload size, no black borders",
                                "Tamanho de envio recomendado, sem bordas pretas"),
    "preset_workshop_5slot_119": ("Workshop · 5 cuadrados de 119 px (nativo)",
                                  "Workshop · 5 squares, 119 px (native)",
                                  "Workshop · 5 quadrados de 119 px (nativo)"),
    "note_workshop_5slot_119": ("Tamaño real de los huecos del Workshop", "Real size of the Workshop slots",
                                "Tamanho real dos espaços do Workshop"),
    "fragment_now": ("Fragmentar", "Fragment", "Fragmentar"),
    "tip_fragment_steam": ("Cortar en piezas listas para Steam (máx. 5 MB cada una)",
                           "Cut into Steam-ready pieces (max 5 MB each)",
                           "Cortar em peças prontas para a Steam (máx. 5 MB cada)"),
    "open_preview": ("Preview de fragmentos", "Fragment preview", "Preview dos fragmentos"),
    "tip_open_preview": ("Ver cómo quedará el corte antes de fragmentar",
                         "See how the cut will look before fragmenting",
                         "Ver como ficará o corte antes de fragmentar"),
    "pipeline_one_click": ("Pipeline 1-clic", "1-click pipeline", "Pipeline 1 clique"),
    "tip_pipeline": ("Todo automático: IA + colores + fragmentar", "Fully automatic: AI + colors + fragment",
                     "Tudo automático: IA + cores + fragmentar"),
    "pipeline_step_ai": ("Mejorar con IA ({model})", "Improve with AI ({model})", "Melhorar com IA ({model})"),
    "pipeline_step_colors": ("Aplicar los ajustes de color", "Apply the color adjustments",
                             "Aplicar os ajustes de cor"),
    "pipeline_step_fragment": ("Fragmentar: {preset}", "Fragment: {preset}", "Fragmentar: {preset}"),
    "pipeline_confirm": ("Se ejecutará todo automáticamente:\n\n{steps}\n\nPuede tardar varios minutos. ¿Continuar?",
                         "Everything will run automatically:\n\n{steps}\n\nIt may take several minutes. Continue?",
                         "Tudo será executado automaticamente:\n\n{steps}\n\nPode levar vários minutos. Continuar?"),
    "optimize_size": ("Optimizar ≤ 5 MB", "Optimize ≤ 5 MB", "Otimizar ≤ 5 MB"),
    "tip_optimize_size": ("Reducir GIF que ya tengas por debajo de 5 MB sin desincronizarlos",
                          "Shrink GIFs you already have below 5 MB without desyncing them",
                          "Reduzir GIFs que você já tem para menos de 5 MB sem dessincronizá-los"),
    "pick_gifs_to_optimize": ("Selecciona los GIF a optimizar", "Select the GIFs to optimize",
                              "Selecione os GIFs para otimizar"),
    "ask_max_mb": ("Tamaño máximo por archivo (MB).\nSteam rechaza más de 5 MB.",
                   "Maximum size per file (MB).\nSteam rejects more than 5 MB.",
                   "Tamanho máximo por arquivo (MB).\nA Steam recusa mais de 5 MB."),
    "optimize_failed": ("No se pudo bajar del límite: recorta la duración del GIF.",
                        "Could not get under the limit: trim the GIF duration.",
                        "Não foi possível ficar abaixo do limite: reduza a duração do GIF."),
    "err_fragment": ("La fragmentación ha fallado", "Fragmentation failed", "A fragmentação falhou"),
    "fragments_ready": ("Fragmentos generados", "Generated fragments", "Fragmentos gerados"),
    "fragments_summary": ("{n} archivo(s) · {mb:.2f} MB en total", "{n} file(s) · {mb:.2f} MB in total",
                          "{n} arquivo(s) · {mb:.2f} MB no total"),
    "js_instructions": ("En la página de subida de Steam, abre la consola (F12 → Console) y pega esto ANTES de guardar:",
                        "On Steam's upload page, open the console (F12 → Console) and paste this BEFORE saving:",
                        "Na página de envio da Steam, abra o console (F12 → Console) e cole isto ANTES de salvar:"),
    "artwork_2part_hint": ("Sube los dos archivos y en Editar perfil → Artwork Showcase asigna el principal y el lateral a su hueco.",
                           "Upload both files, then in Edit Profile → Artwork Showcase put the main and side images in their slots.",
                           "Envie os dois arquivos e em Editar perfil → Artwork Showcase coloque o principal e o lateral em seus espaços."),
    "copy_js": ("Copiar JS", "Copy JS", "Copiar JS"),
    "copied": ("¡Copiado!", "Copied!", "Copiado!"),

    # ---- Fragment preview window ----------------------------------------------
    "preset_label": ("Preset:", "Preset:", "Preset:"),
    "show_my_profile": ("Mostrar mi perfil", "Show my profile", "Mostrar meu perfil"),
    "profile_short": ("Tu perfil:", "Your profile:", "Seu perfil:"),
    "preview_load_failed": ("No se pudo cargar {file}: {err}", "Could not load {file}: {err}",
                            "Não foi possível carregar {file}: {err}"),
    "steam_unreachable": ("No se pudo conectar con Steam: {err}", "Could not connect to Steam: {err}",
                          "Não foi possível conectar à Steam: {err}"),
    "steam_bad_answer": ("Respuesta inesperada de Steam (¿perfil privado?)",
                         "Unexpected answer from Steam (private profile?)",
                         "Resposta inesperada da Steam (perfil privado?)"),
    "profile_unavailable": ("Perfil no disponible: {err}", "Profile unavailable: {err}", "Perfil indisponível: {err}"),

    # ---- Step 4: upload --------------------------------------------------------
    "refresh_fragments": ("Actualizar lista", "Refresh list", "Atualizar lista"),
    "no_file_yet": ("Carga un archivo en el paso 1.", "Load a file in step 1.", "Carregue um arquivo na etapa 1."),
    "no_fragments_yet": ("Aún no hay fragmentos: usa el paso 3.", "No fragments yet: use step 3.",
                         "Ainda não há fragmentos: use a etapa 3."),
    "format_label": ("Formato: {preset}", "Format: {preset}", "Formato: {preset}"),
    "manual_upload": ("Subida manual", "Manual upload", "Envio manual"),
    "manual_steps": (
        "1. Abre la página de subida de Steam (botón Abrir Steam).\n"
        "2. Abre la consola del navegador (F12 → Console).\n"
        "3. Pega el código (botón Copiar JS, ya adaptado a tu formato) y pulsa Enter.\n"
        "4. Sube el fragmento, ponle título, marca la casilla y guarda.\n"
        "5. Repite con cada parte y colócalas en tu perfil (Editar perfil → Showcase).",
        "1. Open Steam's upload page (Open Steam button).\n"
        "2. Open the browser console (F12 → Console).\n"
        "3. Paste the code (Copy JS button, already matched to your format) and press Enter.\n"
        "4. Upload the fragment, give it a title, tick the checkbox and save.\n"
        "5. Repeat for each part and place them on your profile (Edit Profile → Showcase).",
        "1. Abra a página de envio da Steam (botão Abrir Steam).\n"
        "2. Abra o console do navegador (F12 → Console).\n"
        "3. Cole o código (botão Copiar JS, já adaptado ao seu formato) e pressione Enter.\n"
        "4. Envie o fragmento, dê um título, marque a caixa e salve.\n"
        "5. Repita para cada parte e coloque-as no seu perfil (Editar perfil → Showcase)."),
    "open_fragments_folder": ("Abrir carpeta", "Open folder", "Abrir pasta"),
    "tip_open_folder": ("Abrir la carpeta de fragmentos del archivo actual",
                        "Open the fragments folder of the current file",
                        "Abrir a pasta de fragmentos do arquivo atual"),
    "tip_copy_js": ("Copiar el código de consola adecuado para este formato",
                    "Copy the console code that matches this format",
                    "Copiar o código de console adequado para este formato"),
    "js_copied": ("Snippet JS copiado: pégalo en la consola del navegador (F12)",
                  "JS snippet copied: paste it in the browser console (F12)",
                  "Snippet JS copiado: cole no console do navegador (F12)"),
    "open_workshop": ("Abrir Steam", "Open Steam", "Abrir Steam"),
    "tip_open_workshop": ("Abrir la página de subida de Steam", "Open Steam's upload page",
                          "Abrir a página de envio da Steam"),
    "upload_tool": ("Upload Tool", "Upload Tool", "Upload Tool"),
    "tip_upload_tool": ("Subida automática con tu sesión de Steam", "Automatic upload with your Steam session",
                        "Envio automático com a sua sessão da Steam"),
    "validate_profile": ("Validar perfil", "Check profile", "Validar perfil"),
    "tip_validate_profile": ("Comprobar que tu perfil es público y de nivel 10+",
                             "Check that your profile is public and level 10+",
                             "Verificar se seu perfil é público e nível 10+"),
    "profile_prompt": ("Tu nombre personalizado o la URL de tu perfil:", "Your custom name or profile URL:",
                       "Seu nome personalizado ou a URL do seu perfil:"),
    "validate_btn": ("Validar", "Check", "Validar"),
    "profile_checking": ("Consultando Steam...", "Contacting Steam...", "Consultando a Steam..."),
    "profile_found": ("✅ Perfil encontrado: {name}", "✅ Profile found: {name}", "✅ Perfil encontrado: {name}"),
    "profile_level_ok": ("✅ Nivel {level}: puedes usar showcases", "✅ Level {level}: you can use showcases",
                         "✅ Nível {level}: você pode usar showcases"),
    "profile_level_low": ("⚠️ Nivel {level}: los showcases requieren nivel 10",
                          "⚠️ Level {level}: showcases require level 10",
                          "⚠️ Nível {level}: os showcases exigem nível 10"),
    "profile_level_unknown": ("ℹ️ No se pudo leer el nivel (los showcases requieren nivel 10)",
                              "ℹ️ The level could not be read (showcases require level 10)",
                              "ℹ️ Não foi possível ler o nível (os showcases exigem nível 10)"),
    "export_zip": ("Exportar ZIP", "Export ZIP", "Exportar ZIP"),
    "tip_export_zip": ("Empaquetar fragmentos + instrucciones en un ZIP", "Pack fragments + instructions into a ZIP",
                       "Empacotar fragmentos + instruções em um ZIP"),
    "zip_readme": (
        "WorkshopArt - pack para Steam\n\nFormato: {preset}\nArchivos: {count}\n\nCómo subirlos:\n"
        "1. Abre {url}\n"
        "2. Abre la consola del navegador (F12 -> Console), pega este código y pulsa Enter:\n\n{js}\n\n"
        "3. Sube cada archivo, ponle título y guarda (repite para cada parte).\n"
        "4. En tu perfil: Editar perfil -> Showcase -> asigna cada pieza a su hueco.\n\n"
        "Los showcases requieren una cuenta de Steam de nivel 10 o más.\n",
        "WorkshopArt - Steam pack\n\nFormat: {preset}\nFiles: {count}\n\nHow to upload them:\n"
        "1. Open {url}\n"
        "2. Open the browser console (F12 -> Console), paste this code and press Enter:\n\n{js}\n\n"
        "3. Upload each file, give it a title and save (repeat for every part).\n"
        "4. On your profile: Edit Profile -> Showcase -> put each piece in its slot.\n\n"
        "Showcases require a Steam account of level 10 or higher.\n",
        "WorkshopArt - pacote para a Steam\n\nFormato: {preset}\nArquivos: {count}\n\nComo enviá-los:\n"
        "1. Abra {url}\n"
        "2. Abra o console do navegador (F12 -> Console), cole este código e pressione Enter:\n\n{js}\n\n"
        "3. Envie cada arquivo, dê um título e salve (repita para cada parte).\n"
        "4. No seu perfil: Editar perfil -> Showcase -> coloque cada peça em seu espaço.\n\n"
        "Os showcases exigem uma conta Steam de nível 10 ou mais.\n"),

    # ---- Help window -----------------------------------------------------------
    "help_window_title": ("Ayuda - WorkshopArt", "Help - WorkshopArt", "Ajuda - WorkshopArt"),
    "help_text": (
        "WorkshopArt v{version} · Guía rápida\n\n"
        "WorkshopArt convierte tus videos, GIF e imágenes en piezas listas para los showcases del "
        "perfil de Steam: respeta el límite de 5 MB por archivo, mantiene las partes sincronizadas "
        "y aplica el truco del último byte para que Steam las muestre a tamaño completo.\n\n"
        "1 · ARCHIVO\n"
        "• Arrastra un archivo a la ventana o pulsa Seleccionar archivo (Ctrl+O).\n"
        "• Acepta GIF, videos (MP4, MOV, MKV, WEBM, AVI...) e imágenes (JPG, PNG, WEBP).\n"
        "• Indica si tu contenido es anime: sirve para elegir el mejor modelo de IA.\n\n"
        "2 · PROCESAR (opcional)\n"
        "• Procesar con IA: mejora la resolución con Real-ESRGAN o Real-CUGAN (mejor con GPU).\n"
        "• Solo colores: aplica contraste, saturación, vibrance, nitidez y temperatura; "
        "el preview muestra el resultado en vivo.\n"
        "• Video → GIF: convierte un video eligiendo FPS, recorte y tamaño.\n"
        "• Mejorar animación: interpola frames con RIFE para una animación más fluida.\n\n"
        "3 · FRAGMENTAR\n"
        "• Elige el formato del showcase y pulsa Fragmentar. Todas las piezas comparten FPS y "
        "calidad para que se vean sincronizadas.\n"
        "• Preview de fragmentos: muestra cómo quedará el corte antes de hacerlo.\n"
        "• Pipeline 1-clic: IA + colores + fragmentar, todo seguido.\n"
        "• Optimizar ≤ 5 MB: reduce GIF que ya tengas sin desincronizarlos.\n"
        "Los resultados se guardan en <nombre>_workshop/ junto al archivo original "
        "(los fragmentos, en la subcarpeta fragmentos).\n\n"
        "4 · SUBIR\n"
        "• Upload Tool: sube los fragmentos automáticamente con tu sesión de Steam en "
        "Firefox (Chrome y Edge ya no dejan leerla) o con un archivo steam_cookies.json.\n"
        "• Subida manual: abre la página de subida, pega en la consola (F12) el código de "
        "Copiar JS (ya adaptado a tu formato), sube cada archivo y guarda.\n"
        "• Validar perfil: comprueba que tu perfil es público y de nivel 10 o más, necesario "
        "para los showcases.\n\n"
        "ATAJOS\n"
        "Ctrl+O abrir archivo · Ctrl+1...4 ir a cada paso · F1 esta ayuda\n\n"
        "PROBLEMAS FRECUENTES\n"
        "• GPU no detectada: actualiza los drivers de la tarjeta gráfica.\n"
        "• La IA falla con la GPU: desactiva «Usar GPU» y vuelve a intentarlo.\n"
        "• Un formato no cabe en 5 MB: recorta la duración del clip.\n"
        "• Steam rechaza la subida: pega el código de consola antes de guardar.\n"
        "• Detalles técnicos: SteamWorkshopAppData/logs/runtime.log",
        "WorkshopArt v{version} · Quick guide\n\n"
        "WorkshopArt turns your videos, GIFs and images into pieces ready for Steam profile "
        "showcases: it respects the 5 MB limit per file, keeps the parts in sync and applies "
        "the last-byte trick so Steam shows them at full size.\n\n"
        "1 · FILE\n"
        "• Drop a file on the window or click Select file (Ctrl+O).\n"
        "• Accepts GIFs, videos (MP4, MOV, MKV, WEBM, AVI...) and images (JPG, PNG, WEBP).\n"
        "• Say whether your content is anime: it picks the best AI model.\n\n"
        "2 · PROCESS (optional)\n"
        "• Process with AI: improves the resolution with Real-ESRGAN or Real-CUGAN (best with a GPU).\n"
        "• Colors only: applies contrast, saturation, vibrance, sharpness and temperature; "
        "the preview shows the result live.\n"
        "• Video → GIF: converts a video choosing FPS, trim and size.\n"
        "• Smooth animation: interpolates frames with RIFE for a smoother animation.\n\n"
        "3 · FRAGMENT\n"
        "• Choose the showcase format and click Fragment. All pieces share FPS and quality so "
        "they play in sync.\n"
        "• Fragment preview: shows how the cut will look before doing it.\n"
        "• 1-click pipeline: AI + colors + fragment, in one go.\n"
        "• Optimize ≤ 5 MB: shrinks GIFs you already have without desyncing them.\n"
        "Results are saved in <name>_workshop/ next to the original file (the fragments in "
        "its fragmentos subfolder).\n\n"
        "4 · UPLOAD\n"
        "• Upload Tool: uploads the fragments automatically using your Steam session in "
        "Firefox (Chrome and Edge no longer allow reading it) or a steam_cookies.json file.\n"
        "• Manual upload: open the upload page, paste the Copy JS code (already matched to "
        "your format) in the console (F12), upload each file and save.\n"
        "• Check profile: checks that your profile is public and level 10 or higher, which "
        "showcases require.\n\n"
        "SHORTCUTS\n"
        "Ctrl+O open file · Ctrl+1...4 go to each step · F1 this help\n\n"
        "TROUBLESHOOTING\n"
        "• GPU not detected: update your graphics drivers.\n"
        "• The AI fails on the GPU: turn off \"Use GPU\" and try again.\n"
        "• A format does not fit in 5 MB: trim the clip.\n"
        "• Steam rejects the upload: paste the console code before saving.\n"
        "• Technical details: SteamWorkshopAppData/logs/runtime.log",
        "WorkshopArt v{version} · Guia rápido\n\n"
        "O WorkshopArt transforma seus vídeos, GIFs e imagens em peças prontas para os showcases "
        "do perfil da Steam: respeita o limite de 5 MB por arquivo, mantém as partes "
        "sincronizadas e aplica o truque do último byte para que a Steam as mostre em tamanho "
        "completo.\n\n"
        "1 · ARQUIVO\n"
        "• Arraste um arquivo para a janela ou clique em Selecionar arquivo (Ctrl+O).\n"
        "• Aceita GIFs, vídeos (MP4, MOV, MKV, WEBM, AVI...) e imagens (JPG, PNG, WEBP).\n"
        "• Diga se seu conteúdo é anime: isso escolhe o melhor modelo de IA.\n\n"
        "2 · PROCESSAR (opcional)\n"
        "• Processar com IA: melhora a resolução com Real-ESRGAN ou Real-CUGAN (melhor com GPU).\n"
        "• Só cores: aplica contraste, saturação, vibrância, nitidez e temperatura; o preview "
        "mostra o resultado ao vivo.\n"
        "• Vídeo → GIF: converte um vídeo escolhendo FPS, corte e tamanho.\n"
        "• Suavizar animação: interpola frames com RIFE para uma animação mais fluida.\n\n"
        "3 · FRAGMENTAR\n"
        "• Escolha o formato do showcase e clique em Fragmentar. Todas as peças compartilham FPS "
        "e qualidade para ficarem sincronizadas.\n"
        "• Preview dos fragmentos: mostra como ficará o corte antes de fazê-lo.\n"
        "• Pipeline 1 clique: IA + cores + fragmentar, tudo seguido.\n"
        "• Otimizar ≤ 5 MB: reduz GIFs que você já tem sem dessincronizá-los.\n"
        "Os resultados ficam em <nome>_workshop/ ao lado do arquivo original (os fragmentos na "
        "subpasta fragmentos).\n\n"
        "4 · ENVIAR\n"
        "• Upload Tool: envia os fragmentos automaticamente com a sua sessão da Steam no "
        "Firefox (Chrome e Edge não permitem mais lê-la) ou com um arquivo steam_cookies.json.\n"
        "• Envio manual: abra a página de envio, cole no console (F12) o código de Copiar JS "
        "(já adaptado ao seu formato), envie cada arquivo e salve.\n"
        "• Validar perfil: verifica se seu perfil é público e de nível 10 ou mais, exigido "
        "pelos showcases.\n\n"
        "ATALHOS\n"
        "Ctrl+O abrir arquivo · Ctrl+1...4 ir para cada etapa · F1 esta ajuda\n\n"
        "PROBLEMAS COMUNS\n"
        "• GPU não detectada: atualize os drivers da placa de vídeo.\n"
        "• A IA falha na GPU: desative \"Usar GPU\" e tente de novo.\n"
        "• Um formato não cabe em 5 MB: reduza a duração do clipe.\n"
        "• A Steam recusa o envio: cole o código do console antes de salvar.\n"
        "• Detalhes técnicos: SteamWorkshopAppData/logs/runtime.log"),
}

_LANGS = ("ES", "EN", "PT")
_current = 0  # index into _LANGS


def t(key: str, fallback: str = None, **kwargs) -> str:
    """Return the text for ``key`` in the current language, with {placeholders} filled.

    Unknown keys return ``fallback`` (or the key itself); formatting errors
    return the unformatted text instead of raising.
    """
    entry = _STRINGS.get(key)
    text = entry[_current] if entry else (fallback if fallback is not None else key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass
    return text


def set_language(lang: str) -> None:
    """Set the active language: "ES", "EN" or "PT" (anything else is ignored)."""
    global _current
    if lang in _LANGS:
        _current = _LANGS.index(lang)


def get_language() -> str:
    """Return the active language code."""
    return _LANGS[_current]
