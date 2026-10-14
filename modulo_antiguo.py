import json
import base64
import requests
from io import BytesIO
from PIL import Image


def procesar_partida_antigua(pagina):
    pix = pagina.get_pixmap(dpi=150)
    img_pil = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    
    buffered = BytesIO()
    img_pil.save(buffered, format="JPEG")
    base64_img = base64.b64encode(buffered.getvalue()).decode('utf-8')

    prompt = """
    Analiza esta imagen de SUNARP (Ficha antigua de 3 columnas o escaneo no estructurado).
    Extrae los asientos de dominio, cargas o gravámenes.
    Devuelve ÚNICAMENTE un arreglo JSON válido:
    [{"asiento": "", "tipo": "", "monto": "", "titulares": "", "fecha": ""}]
    """

    payload = {
        "model": "minimax/minimax-m3:free",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                ]
            }
        ],
        "reasoning": {"enabled": True}
    }

    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    
    try:
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=120)
        texto = res.json()['choices'][0]['message'].get("content", "")
        
        if "```json" in texto: texto = texto.split("```json")[1].split("```")[0].strip()
        elif "```" in texto: texto = texto.split("```")[1].split("```")[0].strip()
            
        return json.loads(texto)
    except Exception as e:
        print(f"⚠️ Error en IA Antiguo: {e}")
        return []