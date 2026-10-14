import os
import json
import cv2
import pymupdf
import pytesseract
import numpy as np
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

COLUMNAS = {
    "C_DOMINIO":    {"x1": 0.030, "y1": 0.16, "x2": 0.310, "y2": 0.88},
    "D_GRAVAMENES": {"x1": 0.340, "y1": 0.16, "x2": 0.610, "y2": 0.88},
    "E_CANCELACION":{"x1": 0.640, "y1": 0.16, "x2": 0.910, "y2": 0.88}
}

def preprocesar_imagen(img_pil):
    img_np = np.array(img_pil)
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    blur = cv2.bilateralFilter(gray, 9, 75, 75)
    binarizada = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )
    return Image.fromarray(binarizada)

def extraer_texto_columnas(ruta_pdf, pagina_num=0):
    doc = pymupdf.open(ruta_pdf)
    pagina = doc[pagina_num]
    
    pix = pagina.get_pixmap(dpi=300)
    img_completa = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    ancho, alto = img_completa.size
    
    textos = {}
    for nombre_col, coords in COLUMNAS.items():
        caja = (
            int(ancho * coords["x1"]), int(alto * coords["y1"]),
            int(ancho * coords["x2"]), int(alto * coords["y2"])
        )
        img_crop = img_completa.crop(caja)
        img_limpia = preprocesar_imagen(img_crop)
        
        texto = pytesseract.image_to_string(img_limpia, lang='spa', config='--psm 6').strip()
        textos[nombre_col] = texto
        
    return textos

if __name__ == "__main__":
    carpeta = "pdf"
    archivos = [f for f in os.listdir(carpeta) if f.lower().endswith('.pdf')]
    
    if archivos:
        ruta = os.path.join(carpeta, archivos[0])
        print(f"Extrayendo texto crudo de: {archivos[0]}...")
        
        resultado = extraer_texto_columnas(ruta, pagina_num=0)
        
        with open("resultado_crudo_antiguo.json", "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=4)
            
        print("\n[OK] Extracción completada. Guardado en 'resultado_crudo_antiguo.json':\n")
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    else:
        print("No hay archivos PDF en la carpeta 'pdf/'.")
