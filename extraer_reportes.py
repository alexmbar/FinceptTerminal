#!/usr/bin/env python3
"""
Extractor de LTV, ocupacion y AFFO desde los reportes trimestrales de FIBRAs
===========================================================================

LTV, ocupacion y AFFO no estan en ninguna fuente estructurada: solo en el
reporte trimestral que cada FIBRA publica en PDF. Este modulo lo descarga y
saca las cifras con expresiones regulares.

ADVERTENCIA SOBRE LA FIABILIDAD
-------------------------------
Cada FIBRA maqueta su reporte distinto y puede cambiarlo de un trimestre a
otro. Esto va a fallar para varias, y cuando falle lo hara en silencio si no
se revisa. Por eso:

  - Todo valor extraido se valida contra un rango plausible antes de guardarse.
  - Se guarda de que linea del PDF salio cada cifra (--verbose la muestra).
  - Lo extraido se marca 'pdf' en el JSON, para distinguirlo de lo que
    capturaste a mano.

Contrasta contra el reporte antes de decidir con estos numeros.

Uso:
    python extraer_reportes.py FMTY14              descarga y extrae
    python extraer_reportes.py FMTY14 --verbose    muestra el contexto
    python extraer_reportes.py --descubrir FUNO11  busca la URL del reporte
    python extraer_reportes.py --todas             intenta con las 16

Requiere: pip install pypdf
"""

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from typing import Optional


# ---------------------------------------------------------------------------
# Donde vive el reporte de cada FIBRA.
#
# VERIFICADAS: el patron de URL se confirmo contra documentos reales.
# CANDIDATAS: el slug es una conjetura razonable y hay que probarlo con
# --descubrir, que consulta la URL de verdad en lugar de darla por buena.
# ---------------------------------------------------------------------------
INVESTORCLOUD = "http://cdn.investorcloud.net/{slug}/InformacionFinanciera/ReportesTrimestrales/{archivo}"

SLUGS_VERIFICADOS = {
    "FMTY14": "fibramty",
    "FPLUS16": "fibraplus",
}

SLUGS_CANDIDATOS = {
    "FUNO11":    ["funo", "fibrauno"],
    "DANHOS13":  ["danhos", "fibradanhos"],
    "FSHOP13":   ["fibrashop", "fshop"],
    "FIHO12":    ["fibrahotel", "fiho"],
    "FINN13":    ["fibrainn", "finn"],
    "FHIPO14":   ["fhipo", "fibrahipotecaria"],
    "STORAGE18": ["fibrastorage", "storage"],
    "EDUCA18":   ["fibraeduca", "educa"],
    "FIBRAMQ12": ["fibramacquarie", "fibramq"],
    "FIBRAPL14": ["fibraprologis", "fibrapl"],
    "FCFE18":    ["fibracfe", "fcfe"],
    "FNOVA17":   ["fibranova", "fnova"],
    "FMX23":     ["fibrafmx", "fmx"],
    "NEXT25":    ["fibranext", "next"],
}

# Fibra Nova publica en S3 con otra estructura.
URLS_DIRECTAS = {
    "FNOVA17": "https://fibranova.s3.amazonaws.com/fnova/InformacionFinanciera/ReportesTrimestrales/{archivo}",
}


def trimestres_recientes(cuantos: int = 4):
    """Del mas reciente hacia atras: el ultimo publicado suele ser el previo."""
    hoy = date.today()
    trimestre = (hoy.month - 1) // 3 + 1
    anio = hoy.year
    for _ in range(cuantos):
        trimestre -= 1
        if trimestre == 0:
            trimestre, anio = 4, anio - 1
        yield anio, trimestre


def nombres_archivo(anio: int, trimestre: int):
    """Variantes de nombre observadas entre emisoras."""
    yy = str(anio)[2:]
    base = f"{anio}-{trimestre}T{yy}"
    return [f"{base}.pdf", f"Reportes/{base}-Reporte.pdf",
            f"{base}-Reporte.pdf", f"{base}-es.pdf"]


def urls_candidatas(ticker: str):
    """Todas las URLs que vale la pena probar para un ticker."""
    for anio, trimestre in trimestres_recientes():
        for archivo in nombres_archivo(anio, trimestre):
            if ticker in URLS_DIRECTAS:
                yield URLS_DIRECTAS[ticker].format(archivo=archivo)
            slugs = ([SLUGS_VERIFICADOS[ticker]] if ticker in SLUGS_VERIFICADOS
                     else SLUGS_CANDIDATOS.get(ticker, []))
            for slug in slugs:
                yield INVESTORCLOUD.format(slug=slug, archivo=archivo)


def bajar(url: str, timeout: int = 30) -> Optional[bytes]:
    """Devuelve el PDF, o None si no existe o no es un PDF."""
    try:
        peticion = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (analizador-cbfi)"})
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            contenido = respuesta.read()
        # Un 404 disfrazado de pagina HTML no empieza con %PDF.
        return contenido if contenido[:4] == b"%PDF" else None
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None


def texto_de_pdf(datos: bytes) -> Optional[str]:
    try:
        import io
        from pypdf import PdfReader
    except ImportError:
        print("  Falta pypdf:  pip install pypdf")
        return None
    try:
        lector = PdfReader(io.BytesIO(datos))
        # Las metricas resumidas van en las primeras paginas; leer el reporte
        # completo multiplica el ruido sin agregar señal.
        paginas = lector.pages[:12]
        return "\n".join((p.extract_text() or "") for p in paginas)
    except Exception as e:
        print(f"  No se pudo leer el PDF: {type(e).__name__}")
        return None


# ---------------------------------------------------------------------------
# Extraccion
#
# Cada metrica trae varios patrones ordenados de mas especifico a mas laxo, y
# un rango plausible. El rango es lo que evita que un patron laxo se lleve un
# numero cualquiera de la pagina: sin el, "Ocupacion" podria capturar el
# porcentaje de la tabla de al lado.
# ---------------------------------------------------------------------------
# Hasta 4 decimales: el AFFO por CBFI se publica con esa precision y truncarlo
# a dos introduce varios puntos porcentuales de error al anualizarlo.
# El lookahead final evita morder un separador de miles y quedarse con el
# primer grupo ("1,250,000" no debe leerse como 1.25).
NUM = r"(\d{1,3}(?:[.,]\d{1,4})?)(?![\d]|[.,]\d{3})"

METRICAS = {
    "ltv": {
        "patrones": [
            rf"LTV[^\d\n]{{0,40}}{NUM}\s*%",
            rf"[Ll]oan\s*to\s*[Vv]alue[^\d\n]{{0,40}}{NUM}\s*%",
            rf"[Nn]ivel\s+de\s+endeudamiento[^\d\n]{{0,40}}{NUM}\s*%",
            rf"[Rr]az[oó]n\s+de\s+apalancamiento[^\d\n]{{0,40}}{NUM}\s*%",
        ],
        "rango": (5.0, 70.0),
        "escala": 0.01,
    },
    "ocupacion": {
        "patrones": [
            rf"[Tt]asa\s+de\s+ocupaci[oó]n[^\d\n]{{0,40}}{NUM}\s*%",
            rf"[Oo]cupaci[oó]n\s+(?:total|del\s+portafolio)[^\d\n]{{0,40}}{NUM}\s*%",
            rf"[Oo]cupaci[oó]n[^\d\n]{{0,30}}{NUM}\s*%",
        ],
        "rango": (50.0, 100.0),
        "escala": 0.01,
    },
    "affo_por_cbfi_anual": {
        "patrones": [
            rf"AFFO\s+por\s+CBFI[^\d\n]{{0,40}}{NUM}",
            rf"AFFO\s*/\s*CBFI[^\d\n]{{0,40}}{NUM}",
            rf"FFO\s+[Aa]justado\s+por\s+CBFI[^\d\n]{{0,40}}{NUM}",
        ],
        # Por CBFI y trimestral: decimos de centavos a unos pocos pesos.
        "rango": (0.01, 20.0),
        "escala": 1.0,
        "trimestral": True,
    },
}


def extraer(texto: str, verbose: bool = False) -> dict:
    """Devuelve {campo: (valor, contexto)} de lo que se pudo validar."""
    hallazgos = {}

    for campo, config in METRICAS.items():
        for patron in config["patrones"]:
            for coincidencia in re.finditer(patron, texto):
                crudo = coincidencia.group(1).replace(",", ".")
                try:
                    valor = float(crudo)
                except ValueError:
                    continue

                bajo, alto = config["rango"]
                if not (bajo <= valor <= alto):
                    continue   # fuera de rango: el patron agarro otro numero

                final = valor * config["escala"]
                if config.get("trimestral"):
                    # El reporte da la cifra del trimestre; el analizador
                    # trabaja con AFFO anual por CBFI.
                    final *= 4

                inicio = max(0, coincidencia.start() - 60)
                contexto = " ".join(
                    texto[inicio:coincidencia.end() + 20].split())
                hallazgos[campo] = (final, contexto)
                break
            if campo in hallazgos:
                break

    if verbose:
        for campo, (valor, contexto) in hallazgos.items():
            print(f"    {campo} = {valor}")
            print(f"      <- ...{contexto}...")

    return hallazgos


# ---------------------------------------------------------------------------

def descubrir(ticker: str) -> Optional[str]:
    """Prueba las URLs candidatas y devuelve la primera que entregue un PDF."""
    print(f"\n  Buscando el reporte de {ticker}...")
    for url in urls_candidatas(ticker):
        print(f"    probando {url.split('/')[-1]} en {url.split('/')[3]}...",
              end="\r")
        if bajar(url, timeout=15):
            print(" " * 78, end="\r")
            print(f"    ENCONTRADO: {url}")
            return url
    print(" " * 78, end="\r")
    print(f"    Sin resultado. Baja el PDF a mano del sitio de la FIBRA")
    print(f"    o del indice de AMEFIBRA: https://amefibra.com/reportes-fibras/")
    return None


def procesar(ticker: str, verbose: bool = False, guardar: bool = True) -> dict:
    """Descarga el reporte de una FIBRA y guarda lo que logre extraer."""
    url = descubrir(ticker)
    if not url:
        return {}

    print(f"    descargando...", end="\r")
    datos = bajar(url, timeout=60)
    if not datos:
        print("    la descarga fallo en el segundo intento")
        return {}

    texto = texto_de_pdf(datos)
    if not texto:
        return {}

    hallazgos = extraer(texto, verbose=verbose)
    if not hallazgos:
        print(f"    PDF leido pero sin cifras reconocibles.")
        print(f"    Corre con --verbose para ver que se ley[o.")
        return {}

    print(f"    extraido: {', '.join(hallazgos)}")

    if guardar:
        _guardar(ticker, hallazgos)
    return {campo: valor for campo, (valor, _) in hallazgos.items()}


def _guardar(ticker: str, hallazgos: dict) -> None:
    """Escribe en el JSON, marcando la procedencia como 'pdf'."""
    import analizar_cbfi as base

    ruta = base.directorio_datos() / base.ARCHIVO_FUNDAMENTALES
    contenido = (json.loads(ruta.read_text(encoding="utf-8"))
                 if ruta.exists() else base.plantilla_json())
    entrada = contenido.setdefault("fibras", {}).setdefault(
        ticker, base.entrada_vacia(ticker))

    for campo, (valor, _) in hallazgos.items():
        entrada[campo] = round(valor, 4)
    entrada["_fuente"] = "pdf"

    ruta.write_text(json.dumps(contenido, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    print(f"    guardado en {ruta.name}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    verbose = "--verbose" in sys.argv
    todas = "--todas" in sys.argv

    print("\n" + "=" * 72)
    print("  EXTRACTOR DE REPORTES TRIMESTRALES DE FIBRAs")
    print("=" * 72)
    print("\n  Los reportes cambian de maqueta entre FIBRAs y entre trimestres.")
    print("  Esto va a fallar para varias. Contrasta lo extraido contra el PDF")
    print("  antes de decidir con estos numeros.")

    if "--descubrir" in sys.argv:
        for ticker in args:
            descubrir(ticker.upper())
        return

    if todas:
        import analizar_cbfi as base
        objetivos = list(base.CATALOGO)
    elif args:
        objetivos = [t.upper() for t in args]
    else:
        print("\n  Uso:  extraer_reportes.py FMTY14 [--verbose]")
        print("        extraer_reportes.py --todas")
        print("        extraer_reportes.py --descubrir FUNO11\n")
        return

    logrados, fallidos = [], []
    for ticker in objetivos:
        resultado = procesar(ticker, verbose=verbose)
        (logrados if resultado else fallidos).append(ticker)

    print("\n" + "=" * 72)
    print(f"  Con datos ({len(logrados)}): {', '.join(logrados) or '--'}")
    print(f"  Sin datos ({len(fallidos)}): {', '.join(fallidos) or '--'}")
    if fallidos:
        print("\n  Para las que fallaron, captura a mano:")
        print("    analizar_cbfi.py --set TICKER ocupacion=94 ltv=30 affo=2.9")
        print("  Reportes: https://amefibra.com/reportes-fibras/")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()
