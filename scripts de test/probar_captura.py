import os
import cv2
import pymupdf
import pytesseract
import numpy as np
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Márgenes horizontales ajustados al interior de la grilla (evita líneas negras)
COLUMNAS = {
    "C_DOMINIO":    {"x1": 0.030, "y1": 0.16, "x2": 0.310, "y2": 0.88},
    "D_GRAVAMENES": {"x1": 0.340, "y1": 0.16, "x2": 0.610, "y2": 0.88},
    "E_CANCELACION":{"x1": 0.640, "y1": 0.16, "x2": 0.910, "y2": 0.88}
}

def preprocesar_imagen(img_pil):
    """Limpia ruido, elimina sellos/marcas de agua y resalta el texto negro."""
    img_np = np.array(img_pil)
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    
    # 1. Filtro Bilateral para suavizar ruido sin perder bordes de letras
    blur = cv2.bilateralFilter(gray, 9, 75, 75)
    
    # 2. Binarización Adaptativa (Elimina sombras de fondo y sellos de color)
    binarizada = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )
    return Image.fromarray(binarizada)

def diagnosticar_captura(ruta_pdf, pagina_num=0):
    os.makedirs("debug_crops", exist_ok=True)
    doc = pymupdf.open(ruta_pdf)
    pagina = doc[pagina_num]
    
    # Renderizado a alta resolución (300 DPI) para máquina de escribir
    pix = pagina.get_pixmap(dpi=300)
    img_completa = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    ancho, alto = img_completa.size
    
    print("\n--- GENERANDO IMÁGENES DE DIAGNÓSTICO EN 'debug_crops/' ---")
    
    for nombre_col, coords in COLUMNAS.items():
        caja = (
            int(ancho * coords["x1"]), int(alto * coords["y1"]),
            int(ancho * coords["x2"]), int(alto * coords["y2"])
        )
        img_crop = img_completa.crop(caja)
        img_limpia = preprocesar_imagen(img_crop)
        
        # Guardar imagen procesada para revisión manual
        ruta_guardado = os.path.join("debug_crops", f"{nombre_col}.png")
        img_limpia.save(ruta_guardado)
        print(f"✅ Imagen de prueba guardada: {ruta_guardado}")
        
        # Extracción OCR pura (Configuración para bloques uniformes de texto)
        texto_raw = pytesseract.image_to_string(img_limpia, lang='spa', config='--psm 6').strip()
        
        print(f"\n======== CAPTURA CRUDA: {nombre_col} ========")
        print(texto_raw if texto_raw else "[Sin texto detectado]")
        print("=" * 45)

if __name__ == "__main__":
    carpeta = "pdf"
    archivos = [f for f in os.listdir(carpeta) if f.lower().endswith('.pdf')]
    if archivos:
        diagnosticar_captura(os.path.join(carpeta, archivos[0]))
    else:
        print("No hay archivos en la carpeta 'pdf/'.")



        