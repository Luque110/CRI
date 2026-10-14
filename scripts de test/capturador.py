import os
import cv2
import pymupdf
import numpy as np
import json

def capturar_coordenadas():
    carpeta = "pdf"
    
    # 1. Buscar el primer PDF en la carpeta
    if not os.path.exists(carpeta):
        os.makedirs(carpeta)
    archivos = [f for f in os.listdir(carpeta) if f.lower().endswith('.pdf')]
    
    if not archivos:
        print(f"Error: Coloca un documento de prueba en la carpeta '{carpeta}/'")
        return

    ruta_pdf = os.path.join(carpeta, archivos[0])
    
    # 2. Renderizar la primera página a imagen
    doc = pymupdf.open(ruta_pdf)
    pagina = doc[0]
    pix = pagina.get_pixmap(dpi=150)
    
    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR if pix.n == 4 else cv2.COLOR_RGB2BGR)

    # Escalar para que quepa en tu monitor (máx 800px de alto)
    alto, ancho = img_cv.shape[:2]
    escala = 800 / alto if alto > 800 else 1
    img_mostrar = cv2.resize(img_cv, (0, 0), fx=escala, fy=escala)

    print("\n--- INSTRUCCIONES ---")
    print("1. Dibuja un recuadro enmarcando SOLO el área de texto útil.")
    print("2. Presiona ENTER para confirmar.")
    
    # 3. Interfaz de usuario para dibujar
    bbox = cv2.selectROI("Capturador de Coordenadas", img_mostrar, fromCenter=False, showCrosshair=True)
    cv2.destroyAllWindows()

    x, y, w, h = bbox
    if w == 0 or h == 0:
        print("\n[!] Recorte cancelado por el usuario.")
        return

    # 4. Calcular proporciones relativas (funciona para cualquier resolución futura)
    coordenadas = {
        "x1": round(x / (ancho * escala), 4),
        "y1": round(y / (alto * escala), 4),
        "x2": round((x + w) / (ancho * escala), 4),
        "y2": round((y + h) / (alto * escala), 4)
    }

    # Guardar en archivo y mostrar en consola
    with open("coordenadas_nuevo.json", "w") as f:
        json.dump(coordenadas, f, indent=4)

    print("\n✅ ÉXITO - COPIA Y PEGA ESTO EN EL CHAT:")
    print("-" * 30)
    print(json.dumps(coordenadas, indent=4))
    print("-" * 30)

if __name__ == "__main__":
    capturar_coordenadas()