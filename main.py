from datetime import datetime
import glob
import json
import os
import re
import unicodedata
import pymupdf as fitz  # Utiliza la nueva API de PyMuPDF
import requests
from modulo_antiguo import procesar_partida_antigua
from modulo_nuevo import procesar_partida_nueva


MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "setiembre": 9,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def corregir_encoding(texto):
  """Corrige caracteres corruptos (Mojibake) provenientes del OCR."""
  if not texto:
    return ""
  try:
    texto = texto.encode("latin1").decode("utf-8")
  except Exception:
    pass
  return unicodedata.normalize("NFKC", texto)


def limpiar_respuesta_json(texto):
  """Limpia la respuesta del LLM y extrae únicamente el bloque JSON válido."""
  if not texto:
    return None

  texto_limpio = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL)
  texto_limpio = re.sub(
      r"```(?:json)?\s*(.*?)\s*```", r"\1", texto_limpio, flags=re.DOTALL
  )

  match_json = re.search(
      r"(\[\s*\{.*\}\s*\]|\{.*\})", texto_limpio, flags=re.DOTALL
  )
  if match_json:
    try:
      return json.loads(match_json.group(1).strip())
    except json.JSONDecodeError:
      pass

  try:
    return json.loads(texto_limpio.strip())
  except json.JSONDecodeError as e:
    print(f"❌ Error al decodificar JSON: {e}")
    return None


def parsear_fecha_espanol(fecha_str):
  """Convierte fechas textuales o numéricas a objetos datetime para ordenamiento."""
  if not fecha_str or not isinstance(fecha_str, str):
    return datetime.min
  text = fecha_str.lower().strip()

  m_texto = re.search(r"(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})", text)
  if m_texto:
    try:
      return datetime(
          int(m_texto.group(3)),
          MESES.get(m_texto.group(2), 1),
          int(m_texto.group(1)),
      )
    except ValueError:
      pass

  m_num = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", text)
  if m_num:
    try:
      return datetime(
          int(m_num.group(3)), int(m_num.group(2)), int(m_num.group(1))
      )
    except ValueError:
      pass

  return datetime.min


def extraer_numero_asiento(asiento_str):
  """Extrae el correlativo numérico de un código de asiento (ej. C00010 -> 10)."""
  if not asiento_str:
    return 999999
  match = re.search(r"\d+", str(asiento_str))
  return int(match.group(0)) if match else 999999


# ==============================================================================
# FASE 1: PROMPT DE EXTRACCIÓN Y SEGMENTACIÓN
# ==============================================================================
def extraer_asientos_y_fechas(texto_completo_expediente):
  prompt = f"""
    Eres un extractor especializado de partidas registrales de SUNARP. Tu ÚNICA función es segmentar el texto transcrito en asientos individuales.

    REGLAS DE EXTRACCIÓN:
    1. Identifica el código del asiento (ej. A00001, B00001, C00001, D00001).
    2. Extrae ÚNICAMENTE la fecha de cierre/firma del registrador ubicada al FINAL del texto de cada asiento. IGNORA las fechas de presentación o ingreso del título.
    3. Copia el contenido completo de cada asiento tal como aparece. No resumas.

    ESTRUCTURA JSON REQUERIDA (Responde EXCLUSIVAMENTE con este JSON sin texto ni explicaciones adicionales):
    {{
      "asientos": [
        {{
          "asiento": "Código del asiento",
          "acto_registral": "Tipo de acto",
          "fecha_cierre_raw": "Fecha final de cierre",
          "contenido_asiento": "Texto completo del asiento"
        }}
      ]
    }}

    TEXTO TRANSCRITO:
    {texto_completo_expediente}
    """

  payload = {
      "model": MODELO,
      "messages": [{"role": "user", "content": prompt}],
      "temperature": 0.0,
  }

  try:
    res = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=HEADERS,
        data=json.dumps(payload),
        timeout=120,
    )
    if res.status_code == 200:
      raw_content = res.json()["choices"][0]["message"].get("content", "")
      datos = limpiar_respuesta_json(raw_content)
      if datos and isinstance(datos, dict):
        return datos.get("asientos", [])

    print(f"❌ Error HTTP {res.status_code}: {res.text}")
    return []
  except Exception as e:
    print(f"⚠️ Excepción al extraer asientos: {e}")
    return []


# ==============================================================================
# ORDENAMIENTO DETERMINISTA EN PYTHON (CRITERIO 1: FECHA, CRITERIO 2: NÚMERO)
# ==============================================================================
def ordenar_asientos_por_fecha(lista_asientos):
  for item in lista_asientos:
    dt = parsear_fecha_espanol(item.get("fecha_cierre_raw", ""))
    num_asiento = extraer_numero_asiento(item.get("asiento", ""))

    item["fecha_iso_normalizada"] = (
        dt.strftime("%Y-%m-%d") if dt != datetime.min else "9999-12-31"
    )
    item["_dt_sort"] = dt
    item["_num_sort"] = num_asiento

  # Ordenamiento multicriterio
  lista_ordenada = sorted(
      lista_asientos, key=lambda x: (x["_dt_sort"], x["_num_sort"])
  )

  for item in lista_ordenada:
    del item["_dt_sort"]
    del item["_num_sort"]
  return lista_ordenada


# ==============================================================================
# FASE 2: ANÁLISIS DE TRACTO SUCESIVO Y CARGAS
# ==============================================================================
def analizar_logica_cronologica(asientos_ordenados):
  if not asientos_ordenados:
    return {
        "reporte_historico_acumulativo": [],
        "reporte_titulares_actuales_depurado": [],
        "reporte_cargas_y_gravamenes": [],
    }

  prompt = f"""
    Eres un registrador público experto. Recibes una lista de asientos ORDENADOS CRONOLÓGICAMENTE por Python. Respeta estrictamente esa secuencia temporal.

    REGLAS DE EVALUACIÓN:
    1. REPORTE HISTÓRICO ACUMULATIVO:
       - Registra a toda persona natural o jurídica que haya adquirido titularidad en cualquier momento del historial.
       - Si son cónyuges o copropietarios, asígnales un número de orden individual.

    2. REPORTE DE TITULARES VIGENTES (TRACTO SUCESIVO):
       - Recorre los asientos en el orden exacto del arreglo.
       - Realiza las operaciones matemáticas de suma y resta de porcentajes de propiedad (cuotas ideales) respetando los decimales exactos.
       - Si un titular vende/transfiere el 100% de su cuota, ELIMÍNALO definitivamente del reporte final.
       - Mantén en la lista final solo a quienes posean una cuota vigente > 0%.

    3. REPORTE DE CARGAS Y GRAVÁMENES:
       - Extrae únicamente las cargas/hipotecas/embargos del rubro D que continúen vigentes y no hayan sido canceladas en un asiento posterior.

    ASIENTOS CRONOLÓGICAMENTE ORDENADOS:
    {json.dumps(asientos_ordenados, ensure_ascii=False, indent=2)}

    ESTRUCTURA JSON REQUERIDA (Responde SOLO con este objeto JSON):
    {{
      "reporte_historico_acumulativo": [
        {{"numero_orden": "1", "titular": "Nombre", "documento": "DNI/RUC"}}
      ],
      "reporte_titulares_actuales_depurado": [
        {{"titular_vigente": "Nombre o Sociedad Conyugal", "cuota_actual": "%", "asiento_origen": "C000XX"}}
      ],
      "reporte_cargas_y_gravamenes": [
        {{"asiento_carga": "D000XX", "observaciones": "Detalle de la carga"}}
      ]
    }}
    """

  payload = {
      "model": MODELO,
      "messages": [{"role": "user", "content": prompt}],
      "temperature": 0.0,
  }

  try:
    res = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=HEADERS,
        data=json.dumps(payload),
        timeout=120,
    )
    if res.status_code == 200:
      raw_content = res.json()["choices"][0]["message"].get("content", "")
      datos = limpiar_respuesta_json(raw_content)
      if datos and isinstance(datos, dict):
        return datos

    return {
        "reporte_historico_acumulativo": [],
        "reporte_titulares_actuales_depurado": [],
        "reporte_cargas_y_gravamenes": [],
    }
  except Exception as e:
    print(f"⚠️ Excepción al analizar cronología: {e}")
    return {
        "reporte_historico_acumulativo": [],
        "reporte_titulares_actuales_depurado": [],
        "reporte_cargas_y_gravamenes": [],
    }


# ==============================================================================
# PIPELINE PRINCIPAL
# ==============================================================================
def procesar_expediente_holistico(ruta_pdf):
  doc = fitz.open(ruta_pdf)
  texto_acumulado = ""

  print(f"📄 Procesando PDF: {ruta_pdf} ({len(doc)} pág)...")

  for num_pag in range(len(doc)):
    pagina = doc[num_pag]

    datos_ocr = procesar_partida_nueva(pagina)
    cabecera = corregir_encoding(datos_ocr.get("texto_cabecera", "").strip())
    cuerpo = corregir_encoding(datos_ocr.get("texto_cuerpo", "").strip())

    texto_pagina = f"{cabecera}\n{cuerpo}".strip()

    if len(texto_pagina) > 30:
      texto_acumulado += f"\n--- PÁGINA {num_pag + 1} ---\n{texto_pagina}"
    else:
      datos_antiguos = procesar_partida_antigua(pagina)
      texto_acumulado += (
          f"\n--- PÁGINA {num_pag + 1} ---\n"
          + corregir_encoding(
              json.dumps(datos_antiguos, ensure_ascii=False)
          )
      )

  doc.close()

  # Paso 1: Extracción bruta
  asientos_raw = extraer_asientos_y_fechas(texto_acumulado)

  # Paso 2: Ordenamiento determinista en Python (Fecha -> Correlativo)
  asientos_ordenados = ordenar_asientos_por_fecha(asientos_raw)

  # Paso 3: Análisis legal de tracto sucesivo
  reporte = analizar_logica_cronologica(asientos_ordenados)

  return asientos_ordenados, reporte


if __name__ == "__main__":
  archivos = glob.glob(os.path.join(CARPETA_PDF, "*.pdf"))
  if archivos:
    asientos_total, hist_total, act_total, car_total = [], [], [], []

    for archivo in archivos:
      asientos, reporte = procesar_expediente_holistico(archivo)
      asientos_total.extend(asientos)
      hist_total.extend(reporte.get("reporte_historico_acumulativo", []))
      act_total.extend(reporte.get("reporte_titulares_actuales_depurado", []))
      car_total.extend(reporte.get("reporte_cargas_y_gravamenes", []))

    # Guardado de archivos
    with open("1_asientos_fechas.json", "w", encoding="utf-8") as f:
      json.dump(asientos_total, f, indent=4, ensure_ascii=False)
    with open("2_historial_acumulativo.json", "w", encoding="utf-8") as f:
      json.dump(hist_total, f, indent=4, ensure_ascii=False)
    with open("3_titulares_reales_vigentes.json", "w", encoding="utf-8") as f:
      json.dump(act_total, f, indent=4, ensure_ascii=False)
    with open("4_cargas_vigentes.json", "w", encoding="utf-8") as f:
      json.dump(car_total, f, indent=4, ensure_ascii=False)

    print("\n✅ Los 4 archivos JSON han sido creados con éxito.")
  else:
    print(f"⚠️ No se encontraron archivos PDF en '{CARPETA_PDF}'.")