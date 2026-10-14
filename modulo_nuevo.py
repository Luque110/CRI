import re
import cv2
import numpy as np
import pytesseract

# --- CONFIGURACIÓN TESSERACT ---
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Coordenadas de recorte
CAB_Y1, CAB_Y2 = 0.30, 0.38
CAB_X1, CAB_X2 = 0.20, 0.70
CUE_X1, CUE_Y1 = 0.1706, 0.3592
CUE_X2, CUE_Y2 = 0.8330, 0.8305

def procesar_partida_nueva(pagina, config_tess='--psm 6'):
    # Aumentamos a 300 DPI para que el texto sea más nítido
    pix = pagina.get_pixmap(dpi=300)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, 3))
    gris = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    alto, ancho = gris.shape

    # Recortes
    crop_cabecera = gris[int(alto * CAB_Y1):int(alto * CAB_Y2), int(ancho * CAB_X1):int(ancho * CAB_X2)]
    crop_cuerpo = gris[int(alto * CUE_Y1):int(alto * CUE_Y2), int(ancho * CUE_X1):int(ancho * CUE_X2)]

    # Binarización (Filtro para dejar el fondo blanco puro y letras negras puro)
    _, crop_cabecera = cv2.threshold(crop_cabecera, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, crop_cuerpo = cv2.threshold(crop_cuerpo, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Extracción de texto
    texto_cabecera = pytesseract.image_to_string(crop_cabecera, lang='spa', config=config_tess).strip()
    texto_cuerpo = pytesseract.image_to_string(crop_cuerpo, lang='spa', config=config_tess).strip()

    # Detección de código de asiento
    match_codigo = re.search(r'\b([A-Z]\d{5,6})\b', re.sub(r'\s+', '', texto_cabecera))
    asiento = match_codigo.group(1) if match_codigo else "No detectado"

    return {
        "asiento": asiento,
        "texto_cabecera": texto_cabecera,
        "texto_cuerpo": texto_cuerpo
    }