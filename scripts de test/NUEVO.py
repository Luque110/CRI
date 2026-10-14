    import os
    import time
    import re
    import cv2
    import numpy as np
    import pymupdf
    import pytesseract

    # Configuración de Tesseract
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

    # Coordenadas fijadas
    # 1. Cabecera (Rubro/Asiento)
    CAB_Y1, CAB_Y2 = 0.30, 0.38
    CAB_X1, CAB_X2 = 0.20, 0.70

    # 2. Cuerpo (Valores mapeados)
    CUE_X1, CUE_Y1 = 0.1706, 0.3592
    CUE_X2, CUE_Y2 = 0.8330, 0.8305

    def procesar_ocr_pagina(pagina, config_tess='--psm 6'):
        # Renderizar a 150 DPI directamente a escala de grises
        pix = pagina.get_pixmap(dpi=150)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, 3))
        gris = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        alto, ancho = gris.shape

        # Recortes en memoria
        crop_cabecera = gris[int(alto * CAB_Y1):int(alto * CAB_Y2), int(ancho * CAB_X1):int(ancho * CAB_X2)]
        crop_cuerpo = gris[int(alto * CUE_Y1):int(alto * CUE_Y2), int(ancho * CUE_X1):int(ancho * CUE_X2)]

        # OCR directo sobre imágenes en memoria
        texto_cabecera = pytesseract.image_to_string(crop_cabecera, lang='spa', config=config_tess).strip()
        texto_cuerpo = pytesseract.image_to_string(crop_cuerpo, lang='spa', config=config_tess).strip()

        # Extracción por Expresiones Regulares
        # 1. Asiento / Código desde la cabecera
        match_codigo = re.search(r'\b([A-Z]\d{5})\b', re.sub(r'\s+', '', texto_cabecera))
        asiento = match_codigo.group(1) if match_codigo else "No detectado"

        # 2. Fecha desde el cuerpo
        patron_fecha = r'\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b|\b\d{1,2}\s+de\s+[a-zA-ZáéíóúÁÉÍÓÚ]+\s+de\s+\d{4}\b'
        coincidencias_fecha = re.findall(patron_fecha, texto_cuerpo)
        fecha = coincidencias_fecha[-1] if coincidencias_fecha else "No detectada"

        return texto_cabecera, asiento, fecha, texto_cuerpo

    def ejecutar_ocr_unificado_lote(carpeta_pdf="pdf"):
        if not os.path.exists(carpeta_pdf):
            print(f"❌ La carpeta '{carpeta_pdf}' no existe.")
            return

        archivos = [f for f in os.listdir(carpeta_pdf) if f.lower().endswith(".pdf")]
        if not archivos:
            print(f"❌ No se encontraron PDFs en '{carpeta_pdf}'.")
            return

        archivo_salida = "reporte_ocr_unificado.txt"
        t0_global = time.time()
        total_paginas = 0

        print(f"🚀 Procesando OCR (Cabecera + Cuerpo) para {len(archivos)} documentos...")

        with open(archivo_salida, "w", encoding="utf-8") as f:
            f.write("=== REPORTE DE EXTRACCIÓN DE TEXTO (OCR) ===\n\n")

            for archivo in archivos:
                ruta_pdf = os.path.join(carpeta_pdf, archivo)
                doc = pymupdf.open(ruta_pdf)
                
                f.write(f"DOCUMENTO: {archivo} | Páginas: {len(doc)}\n" + "="*50 + "\n")

                for idx, pagina in enumerate(doc):
                    t0_pag = time.time()
                    texto_cabecera, asiento, fecha, texto_cuerpo = procesar_ocr_pagina(pagina)
                    t_pag = time.time() - t0_pag
                    total_paginas += 1

                    f.write(f"--- Página {idx + 1:02d} (Tiempo: {t_pag:.3f}s) ---\n")
                    f.write(f"Asiento / Código extraído: {asiento}\n")
                    f.write(f"Fecha detectada: {fecha}\n\n")
                    f.write("[TEXTO DE LA CABECERA]:\n")
                    f.write(f"{texto_cabecera if texto_cabecera else '(Sin texto detectado)'}\n\n")
                    f.write("[TEXTO DEL CUERPO]:\n")
                    f.write(f"{texto_cuerpo if texto_cuerpo else '(Sin texto detectado)'}\n")
                    f.write("-" * 40 + "\n\n")

        print(f"⚡ Procesamiento completado en {time.time() - t0_global:.2f}s")
        print(f"📂 Reporte de texto completo guardado en: {archivo_salida}")

    if __name__ == "__main__":
        ejecutar_ocr_unificado_lote("pdf")

        