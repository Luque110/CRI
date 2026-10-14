# modulo_clasificador.py
import pymupdf

def clasificar_pagina(pagina):
    """
    Evalúa la página y decide la ruta de extracción.
    Retorna: "NUEVO", "ANTIGUO" o "IGNORAR"
    """
    rect = pagina.rect
    es_horizontal = rect.width > rect.height
    
    # Si es apaisado, seguro es la ficha de 3 columnas
    if es_horizontal:
        return "ANTIGUO"

    texto_nativo = pagina.get_text("text").upper()
    
    # Si tiene texto digital útil
    if len(texto_nativo) > 150:
        if "ZONA REGISTRAL" in texto_nativo or "PARTIDA" in texto_nativo:
            return "NUEVO"
        if "FICHA N" in texto_nativo or "TOMO" in texto_nativo:
            return "ANTIGUO"
            
    # Si es vertical pero es una pura imagen escaneada sin texto nativo
    return "ANTIGUO"