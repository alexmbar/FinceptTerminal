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
        # Se lee el reporte entero. El resumen ejecutivo trae LTV y ocupacion
        # en las primeras paginas, pero la tabla con los CBFIs en circulacion
        # cae mucho despues (pagina 30+ en Fibra Mty) y sin ella no hay AFFO.
        # El ruido extra lo contienen los rangos de plausibilidad y el orden
        # de los patrones, que prueban primero los del resumen.
        return "\n".join((p.extract_text() or "") for p in lector.pages)
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


def _affo_por_cbfi(texto: str) -> Optional[tuple]:
    """
    AFFO anual por CBFI, armado con el AFFO total y los CBFIs en circulacion.

    Los reportes publican el AFFO en millones para todo el fideicomiso, no por
    certificado, asi que hay que dividirlo. La cifra por CBFI aparece en una
    tabla de indicadores cuyo layout no sobrevive a la extraccion de texto.

    Ojo con el resultado cuando la FIBRA acaba de emitir o adquirir: el AFFO es
    del trimestre y los CBFIs son los de hoy, asi que un trimestre que solo
    recogio parte de la operacion nueva se reparte entre todos los
    certificados y el AFFO por CBFI sale bajo.
    """
    total = None
    for patron in [
        # Resumen ejecutivo: "FFO y AFFO se situaron en Ps. X y Ps. Y millones"
        r"AFFO.{0,30}se situaron en Ps\.?\s*[\d,.]+\s*millones y Ps\.?\s*([\d,]+\.?\d*)",
        r"AFFO[^\d\n]{0,30}Ps\.?\s*([\d,]+\.?\d*)\s*millones",
    ]:
        m = re.search(patron, texto)
        if m:
            try:
                total = float(m.group(1).replace(",", "")) * 1e6
                break
            except ValueError:
                pass

    if total is None:
        # Tabla: "AFFO generado 834,471" viene en miles.
        m = re.search(r"AFFO\s+generado\s+([\d,]+)", texto)
        if m:
            try:
                total = float(m.group(1).replace(",", "")) * 1e3
            except ValueError:
                pass

    if total is None:
        return None

    # Estas tablas listan la serie de trimestres, asi que el segundo numero es
    # el trimestre anterior. Comparar ambos detecta la dilucion reciente que
    # invalida el calculo: si la FIBRA acaba de emitir o adquirir, el AFFO del
    # trimestre se reparte entre certificados que casi no contribuyeron a el.
    serie = re.search(
        r"CBFIs?\s+en\s+circulaci[oó]n\s*\(en\s+miles\)\s*(?:\(\d+\)\s*)?"
        r"([\d,]+\.?\d*)\s+([\d,]+\.?\d*)", texto)
    if serie:
        try:
            actual, previo = [float(g.replace(",", "")) for g in serie.groups()]
            if previo and actual / previo > 1.20:
                # Fibra Mty paso de 2.4 a 4.8 mil millones de CBFIs al comprar
                # Fibra Macquarie, y su AFFO por CBFI salia a la mitad de lo
                # que corresponde: el payout daba 144% y la mandaba a EVITAR.
                return None
        except ValueError:
            pass

    cbfis = None
    # El (?:\(\d+\)\s*)? salta la llamada a nota al pie que va entre la
    # etiqueta y la cifra: "CBFIs en circulacion (en miles) (4) 4,804,828.304".
    for patron, escala in [
        (r"CBFIs?\s+en\s+circulaci[oó]n\s*\(en\s+miles\)\s*(?:\(\d+\)\s*)?([\d,]+\.?\d*)", 1e3),
        (r"CBFIs?\s+en\s+circulaci[oó]n[^\d\n]{0,40}(?:\(\d+\)\s*)?([\d,]{9,})", 1.0),
    ]:
        m = re.search(patron, texto)
        if m:
            try:
                cbfis = float(m.group(1).replace(",", "")) * escala
                break
            except ValueError:
                pass

    if not cbfis:
        return None

    anual = (total / cbfis) * 4   # el reporte es trimestral
    if not (0.01 <= anual <= 20.0):
        return None

    contexto = (f"AFFO total {total/1e6:,.1f} millones / "
                f"{cbfis/1e6:,.0f} millones de CBFIs, anualizado")
    return anual, contexto


def extraer(texto: str, verbose: bool = False) -> dict:
    """Devuelve {campo: (valor, contexto)} de lo que se pudo validar."""
    hallazgos = {}

    compuesto = _affo_por_cbfi(texto)
    if compuesto:
        hallazgos["affo_por_cbfi_anual"] = compuesto

    for campo, config in METRICAS.items():
        if campo in hallazgos:
            continue
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


def url_guardada(ticker: str) -> Optional[str]:
    """URL del reporte registrada para este ticker en el JSON."""
    try:
        import analizar_cbfi as base
        ruta = base.directorio_datos() / base.ARCHIVO_FUNDAMENTALES
        if ruta.exists():
            entrada = json.loads(ruta.read_text(encoding="utf-8")) \
                          .get("fibras", {}).get(ticker, {})
            return entrada.get("_url_reporte")
    except Exception:
        pass
    return None


def procesar(ticker: str, verbose: bool = False, guardar: bool = True,
             origen: Optional[str] = None) -> dict:
    """
    Extrae los fundamentales del reporte de una FIBRA.

    `origen` puede ser la ruta de un PDF que ya bajaste o su URL. Sin el se
    intenta la URL registrada en el JSON y, en ultimo caso, el descubrimiento
    automatico, que solo acierta en las tres FIBRAs cuyo patron de URL esta
    verificado: las demas hospedan en sitios propios, varias con rutas que
    incluyen hashes y no hay forma de derivarlas.
    """
    origen = origen or url_guardada(ticker)

    if origen and not origen.lower().startswith("http"):
        ruta_pdf = Path(origen)
        if not ruta_pdf.exists():
            print(f"    no existe el archivo {ruta_pdf}")
            return {}
        print(f"    leyendo {ruta_pdf.name}")
        datos = ruta_pdf.read_bytes()
        if datos[:4] != b"%PDF":
            print(f"    {ruta_pdf.name} no es un PDF")
            return {}
        texto = texto_de_pdf(datos)
        if not texto:
            return {}
        return _procesar_texto(ticker, texto, verbose, guardar)

    url = origen or descubrir(ticker)
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

    return _procesar_texto(ticker, texto, verbose, guardar, url)


def _procesar_texto(ticker: str, texto: str, verbose: bool, guardar: bool,
                    url: Optional[str] = None) -> dict:
    hallazgos = extraer(texto, verbose=verbose)
    if not hallazgos:
        print(f"    PDF leido pero sin cifras reconocibles.")
        print(f"    Corre con --verbose para ver que se leyo.")
        return {}

    print(f"    extraido: {', '.join(hallazgos)}")

    if guardar:
        _guardar(ticker, hallazgos, url)
    return {campo: valor for campo, (valor, _) in hallazgos.items()}


def _guardar(ticker: str, hallazgos: dict, url: Optional[str] = None) -> None:
    """Escribe en el JSON, marcando la procedencia como 'pdf'."""
    import analizar_cbfi as base

    ruta = base.directorio_datos() / base.ARCHIVO_FUNDAMENTALES
    contenido = (json.loads(ruta.read_text(encoding="utf-8"))
                 if ruta.exists() else base.plantilla_json())
    entrada = contenido.setdefault("fibras", {}).setdefault(
        ticker, base.entrada_vacia(ticker))

    # La URL que si funciono queda registrada para el proximo trimestre: casi
    # siempre basta cambiarle el numero de trimestre.
    if url:
        entrada["_url_reporte"] = url

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
        objetivos = [args[0].upper()] + args[1:]
    else:
        print("\n  Uso:  extraer_reportes.py FMTY14 [--verbose]")
        print("        extraer_reportes.py --todas")
        print("        extraer_reportes.py --descubrir FUNO11\n")
        return

    # Segundo argumento: PDF ya descargado o URL directa. Es la unica via
    # para las FIBRAs cuyo hosting no sigue un patron derivable.
    origen = objetivos[1] if len(objetivos) == 2 and (
        objetivos[1].lower().startswith("http")
        or objetivos[1].lower().endswith(".pdf")) else None
    if origen:
        objetivos = objetivos[:1]

    logrados, fallidos = [], []
    for ticker in objetivos:
        resultado = procesar(ticker, verbose=verbose, origen=origen)
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
