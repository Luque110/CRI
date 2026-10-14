import os
import time
import cv2
import numpy as np
import pymupdf
import pytesseract
import re

# Configuración de Tesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Carpetas de debug (solo usadas por NUEVO)
DIR_ASIENTOS = "debug_recortes"
DIR_CONTENIDO = "debug_recortes_contenido"

def preparar_entorno(carpeta_pdf):
    if not os.path.exists(carpeta_pdf):
        print(f"❌ La carpeta '{carpeta_pdf}' no existe.")
        return False
    os.makedirs(DIR_ASIENTOS, exist_ok=True)
    os.makedirs(DIR_CONTENIDO, exist_ok=True)
    return True

def obtener_imagen_orientada(pagina, dpi=150):
    """Renderiza, detecta rotación vía OSD y devuelve la imagen orientada correctamente."""
    pix = pagina.get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, 3))
    gris = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    try:
        osd = pytesseract.image_to_osd(gris)
        rotacion = int(re.search(r'Rotate: (\d+)', osd).group(1))
    except Exception:
        rotacion = 0

    if rotacion == 180:
        img = cv2.rotate(img, cv2.ROTATE_180)
        gris = cv2.rotate(gris, cv2.ROTATE_180)
    elif rotacion == 90:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        gris = cv2.rotate(gris, cv2.ROTATE_90_CLOCKWISE)
    elif rotacion == 270:
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        gris = cv2.rotate(gris, cv2.ROTATE_90_COUNTERCLOCKWISE)

    return img, gris, rotacion

def clasificar_documento(doc):
    """Clasifica basándose en la página 1. Aplica auto-rotación para evitar falsos negativos."""
    pag1 = doc[0]
    
    # 1. Chequeo por texto nativo
    texto_nativo = pag1.get_text().upper()
    if len(texto_nativo.strip()) > 50 and ("RUBRO" in texto_nativo or "PARTIDA" in texto_nativo):
        return "NUEVO"

    # 2. Chequeo visual con auto-rotación a 100 DPI para velocidad
    _, gris_orientado, _ = obtener_imagen_orientada(pag1, dpi=100)
    texto_eval = pytesseract.image_to_string(gris_orientado, lang='spa', config='--psm 6').upper()

    if "RUBRO" in texto_eval or "PARTIDA ELECTRONICA" in texto_eval:
        return "NUEVO"

    patrones_antiguos = ["REGISTRO DE LA PROPIEDAD", "PREDIO URBANO", "FICHA N", "TITULO DE DOMINIO", "GRAVAMENES", "CONTINUACION"]
    if any(patron in texto_eval for patron in patrones_antiguos):
        return "ANTIGUO"

    return "DESCONOCIDO"

# ==========================================
# MÓDULOS DE EXTRACCIÓN (TUS LÓGICAS EXACTAS)
# ==========================================

def procesar_nuevo(img, num_pag, nombre_base, f, t0):
    alto, ancho, _ = img.shape

    # --- 1. CABECERA / ASIENTO ---
    crop_asiento = img[int(alto * 0.30):int(alto * 0.38), int(ancho * 0.20):int(ancho * 0.70)]
    cv2.imwrite(os.path.join(DIR_ASIENTOS, f"{nombre_base}_Pag{num_pag:02d}.png"), cv2.cvtColor(crop_asiento, cv2.COLOR_RGB2BGR))

    crop_asiento_esc = cv2.resize(crop_asiento, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gris_asiento = cv2.cvtColor(crop_asiento_esc, cv2.COLOR_RGB2GRAY)
    _, bin_asiento = cv2.threshold(gris_asiento, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    texto_cabecera = pytesseract.image_to_string(bin_asiento, lang='spa', config='--psm 6').strip()
    match_rubro = re.search(r"RUBRO\s*:.*?\n\s*([A-Za-z0-9\s]+)", texto_cabecera, re.IGNORECASE)
    
    if match_rubro:
        asiento_limpio = re.sub(r"\s+", "", match_rubro.group(1).strip()).upper()
        match_codigo = re.search(r"([A-Z]\d+)", asiento_limpio)
        asiento_final = match_codigo.group(1) if match_codigo else asiento_limpio
    else:
        match_directo = re.search(r"\b([A-Z]\d{5})\b", re.sub(r"\s+", "", texto_cabecera), re.IGNORECASE)
        asiento_final = match_directo.group(1).upper() if match_directo else "Asiento no detectado"

    # --- 2. CUERPO / FECHA ---
    crop_cuerpo = img[int(alto * 0.36):int(alto * 0.88), int(ancho * 0.10):int(ancho * 0.90)]
    cv2.imwrite(os.path.join(DIR_CONTENIDO, f"{nombre_base}_p{num_pag:02d}_contenido.png"), cv2.cvtColor(crop_cuerpo, cv2.COLOR_RGB2BGR))

    crop_cuerpo_esc = cv2.resize(crop_cuerpo, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    gris_cuerpo = cv2.cvtColor(crop_cuerpo_esc, cv2.COLOR_RGB2GRAY)
    _, bin_cuerpo = cv2.threshold(gris_cuerpo, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    texto_cuerpo = pytesseract.image_to_string(bin_cuerpo, lang='spa', config='--psm 6')

    palabras_parada = ["REGISTRADOR PUBLICO", "ZONA REGISTRAL", "FIRMA DIGITAL", "FIRMA ELECTRONICA"]
    lineas_cuerpo = []
    for linea in texto_cuerpo.splitlines():
        if any(stop in linea.upper() for stop in palabras_parada):
            break
        lineas_cuerpo.append(linea)
    texto_limpio = "\n".join(lineas_cuerpo).strip()
    
    patron_fecha = r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b|\b\d{1,2}\s+de\s+[a-zA-ZáéíóúÁÉÍÓÚ]+\s+de\s+\d{4}\b"
    coincidencias_fecha = re.findall(patron_fecha, texto_limpio)
    fecha_final = re.sub(r"\s+", " ", coincidencias_fecha[-1]).strip() if coincidencias_fecha else "Fecha no encontrada"

    t_proceso = time.time() - t0

    # --- 3. REPORTE NUEVO ---
    f.write(f"--- Página {num_pag:02d} ---\n")
    f.write(f"Asiento: {asiento_final}\n")
    f.write(f"Fecha de presentación: {fecha_final}\n")
    f.write(f"(Tiempo de procesado: {t_proceso:.3f}s)\n")
    f.write("-" * 40 + "\n\n")

    return t_proceso

def procesar_antiguo(gris, rotacion, num_pag, f):
    alto, ancho = gris.shape
    col_c = gris[int(alto * 0.18):int(alto * 0.90), int(ancho * 0.05):int(ancho * 0.35)]
    col_d = gris[int(alto * 0.18):int(alto * 0.90), int(ancho * 0.35):int(ancho * 0.65)]

    _, bin_c = cv2.threshold(col_c, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, bin_d = cv2.threshold(col_d, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    texto_c = pytesseract.image_to_string(bin_c, lang='spa', config='--psm 6').strip()
    texto_d = pytesseract.image_to_string(bin_d, lang='spa', config='--psm 6').strip()

    f.write(f"--- PÁGINA {num_pag:02d} (Rotación corregida: {rotacion}°) ---\n")
    f.write("--- COLUMNA C (TÍTULO DE DOMINIO) ---\n")
    f.write(f"{texto_c}\n\n")
    f.write("--- COLUMNA D (GRAVÁMENES Y CARGAS) ---\n")
    f.write(f"{texto_d}\n")
    f.write("-" * 40 + "\n\n")

def procesar_desconocido(gris, num_pag, f):
    _, binaria = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    texto_completo = pytesseract.image_to_string(binaria, lang='spa', config='--psm 6').strip()

    f.write(f"--- PÁGINA {num_pag:02d} ---\n")
    f.write(f"{texto_completo}\n")
    f.write("-" * 40 + "\n\n")

# ==========================================
# ORQUESTADOR PRINCIPAL
# ==========================================

def procesar_lote_maestro(carpeta_pdf="pdf"):
    if not preparar_entorno(carpeta_pdf):
        return

    archivos = [f for f in os.listdir(carpeta_pdf) if f.lower().endswith(".pdf")]
    if not archivos:
        print(f"❌ No hay PDFs en '{carpeta_pdf}'.")
        return

    archivo_txt = "reporte_maestro_unificado.txt"
    total_paginas_procesadas = 0
    tiempo_total = 0.0

    print(f"🚀 Iniciando procesamiento de {len(archivos)} documentos...")

    with open(archivo_txt, "w", encoding="utf-8") as f:
        f.write("=== REPORTE MAESTRO UNIFICADO ===\n\n")

    for archivo in archivos:
        nombre_base = os.path.splitext(archivo)[0]
        ruta_pdf = os.path.join(carpeta_pdf, archivo)
        doc = pymupdf.open(ruta_pdf)
        
        categoria = clasificar_documento(doc)
        print(f"📄 {archivo} ➔ Categoría: [{categoria}]")

        with open(archivo_txt, "a", encoding="utf-8") as f:
            f.write(f"DOCUMENTO: {archivo} | FORMATO: {categoria}\n" + "="*50 + "\n")

            for idx, pagina in enumerate(doc):
                total_paginas_procesadas += 1
                num_pag = idx + 1
                
                # Renderiza y endereza cada página independiente de su categoría
                img, gris, rotacion = obtener_imagen_orientada(pagina, dpi=150)
                t0 = time.time()

                if categoria == "NUEVO":
                    t_proceso = procesar_nuevo(img, num_pag, nombre_base, f, t0)
                    tiempo_total += t_proceso
                elif categoria == "ANTIGUO":
                    procesar_antiguo(gris, rotacion, num_pag, f)
                else: # DESCONOCIDO
                    procesar_desconocido(gris, num_pag, f)

    promedio_pag = tiempo_total / total_paginas_procesadas if total_paginas_procesadas > 0 else 0
    print("\n⚡ PROCESAMIENTO COMPLETADO")
    print(f"📁 Reporte maestro guardado en: {archivo_txt}")
    print(f"🖼️ Imágenes debug (Formato NUEVO) en: /{DIR_ASIENTOS} y /{DIR_CONTENIDO}")
    print(f"📊 Promedio de tiempo por página (Módulo NUEVO): {promedio_pag:.3f} s")

if __name__ == "__main__":
    procesar_lote_maestro("pdf")