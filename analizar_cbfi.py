#!/usr/bin/env python3
"""
Analizador de CBFIs (FIBRAs) — BMV / GBM México
===============================================

Un CBFI es el certificado de participacion en una FIBRA: cotiza como accion,
no como bono. No tiene cupon, vencimiento ni valor nominal a redimir, asi que
YTM y duration no aplican. Lo que se mide aqui:

    Distribution yield  cuanto reparte contra lo que cuesta
    Payout sobre AFFO   si esa distribucion es sostenible o se come el flujo
    P/NAV               si cotiza con premio o descuento sobre sus inmuebles
    P/FFO               multiplo sobre flujo operativo
    LTV                 apalancamiento (limite regulatorio CNBV: 50%)
    Ocupacion           salud del portafolio

DE DONDE SALEN LOS DATOS
------------------------
Precio y distribuciones cambian a diario, asi que se descargan de Yahoo
Finance al ejecutar. Los fundamentales (AFFO, NAV, LTV, ocupacion) solo
cambian cada trimestre y Yahoo no los publica para FIBRAs mexicanas: se leen
de fundamentales_fibras.json, que tu llenas con el reporte trimestral.

Sin conexion el programa sigue corriendo: avisa y usa solo el JSON.

USO
---
    python analizar_cbfi.py              analiza las FIBRAs del JSON
    python analizar_cbfi.py FUNO11       analiza solo esa
    python analizar_cbfi.py --catalogo   lista las 16 FIBRAs de la BMV
    python analizar_cbfi.py --sin-red    omite la descarga

Requiere: pip install yfinance
"""

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Catalogo de FIBRAs listadas en la BMV.
# Tickers y sectores verificados; sufijo .MX para Yahoo Finance.
# ---------------------------------------------------------------------------
CATALOGO = {
    "FUNO11":    ("Fibra Uno",       "Diversificada (comercial/industrial/oficinas)"),
    "FIBRAMQ12": ("Fibra Macquarie", "Industrial"),
    "FIBRAPL14": ("Fibra Prologis",  "Industrial"),
    "DANHOS13":  ("Fibra Danhos",    "Comercial / oficinas"),
    "FMTY14":    ("Fibra Monterrey", "Diversificada (distribuye mensual)"),
    "FSHOP13":   ("Fibra Shop",      "Centros comerciales"),
    "FIHO12":    ("Fibra Hotel",     "Hotelero"),
    "FINN13":    ("Fibra Inn",       "Hotelero"),
    "FHIPO14":   ("FHipo",           "Hipotecario"),
    "FNOVA17":   ("Fibra Nova",      "Industrial"),
    "FPLUS16":   ("Fibra Plus",      "Desarrollo"),
    "STORAGE18": ("Fibra Storage",   "Self-storage"),
    "EDUCA18":   ("Fibra Educa",     "Educativo"),
    "FCFE18":    ("Fibra CFE",       "Energia (FIBRA E)"),
    "FMX23":     ("Fibra FMX23",     "Sector sin confirmar"),
    "NEXT25":    ("Fibra NEXT25",    "Sector sin confirmar"),
}

ARCHIVO_FUNDAMENTALES = "fundamentales_fibras.json"


def directorio_datos() -> Path:
    """
    Carpeta donde vive el JSON.

    Compilado con PyInstaller --onefile, __file__ apunta a un temporal que se
    borra al salir; el JSON tiene que quedar junto al .exe para que el usuario
    lo pueda editar.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Descarga de mercado
# ---------------------------------------------------------------------------

@dataclass
class DatosMercado:
    """Lo que se pudo bajar y derivar de Yahoo para un ticker."""

    # Mercado
    precio: Optional[float] = None
    distribucion_12m: Optional[float] = None   # suma pagada en 12 meses
    n_pagos_12m: int = 0
    ultimo_pago: Optional[float] = None
    fecha_ultimo_pago: Optional[str] = None

    # Derivados del balance. Son ESTIMACIONES a partir de estados
    # financieros IFRS, no las cifras oficiales que publica la FIBRA en su
    # reporte trimestral. Sirven para filtrar; para decidir, contrasta.
    nav_por_cbfi: Optional[float] = None
    p_nav: Optional[float] = None
    ltv: Optional[float] = None
    ffo_por_cbfi_anual: Optional[float] = None
    fecha_balance: Optional[str] = None

    error: Optional[str] = None
    avisos: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.precio is not None


def descargar(ticker: str) -> DatosMercado:
    """
    Baja precio y distribuciones de los ultimos 12 meses desde Yahoo Finance.

    Nunca lanza excepcion: cualquier fallo (sin red, ticker inexistente, Yahoo
    caido) vuelve como .error para que el analisis siga con el JSON.
    """
    try:
        import logging
        # yfinance escribe sus fallos directo a stderr y ensucia el reporte;
        # aqui los errores ya se manejan y se muestran en su propia linea.
        logging.getLogger("yfinance").setLevel(logging.CRITICAL)
        import yfinance as yf  # import perezoso: tarda ~2s en cargar
    except ImportError:
        return DatosMercado(error="yfinance no instalado (pip install yfinance)")

    simbolo = ticker if ticker.endswith(".MX") else ticker + ".MX"

    try:
        tk = yf.Ticker(simbolo)

        precio = None
        try:
            precio = tk.fast_info.get("lastPrice")
        except Exception:
            pass
        if not precio:
            # fast_info falla en algunos tickers de la BMV; el historial de
            # cierres es mas lento pero mas confiable.
            hist = tk.history(period="5d")
            if not hist.empty:
                precio = float(hist["Close"].dropna().iloc[-1])
        if not precio:
            return DatosMercado(error="sin precio (¿ticker deslistado?)")

        datos = DatosMercado(precio=float(precio))

        try:
            dividendos = tk.dividends
            if dividendos is not None and len(dividendos):
                corte = datetime.now(timezone.utc) - timedelta(days=365)
                indice = dividendos.index
                if indice.tz is None:
                    corte = corte.replace(tzinfo=None)
                ultimos = dividendos[indice >= corte]
                if len(ultimos):
                    datos.distribucion_12m = float(ultimos.sum())
                    datos.n_pagos_12m = int(len(ultimos))
                datos.ultimo_pago = float(dividendos.iloc[-1])
                datos.fecha_ultimo_pago = str(dividendos.index[-1].date())
        except Exception as e:
            datos.error = f"precio ok, distribuciones no: {type(e).__name__}"

        _derivar_fundamentales(tk, datos)
        return datos

    except Exception as e:
        return DatosMercado(error=describir_fallo(e))


def _numero(valor) -> Optional[float]:
    """Normaliza lo que devuelve yfinance: None, NaN, strings y numpy scalars."""
    if valor is None:
        return None
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return None
    if f != f or f == 0:   # NaN, o cero que en estos campos significa "no dato"
        return None
    return f


def _fila_balance(df, *alias) -> Optional[float]:
    """
    Toma el valor mas reciente de la primera fila que exista.

    Los nombres del balance de yfinance varian entre emisoras y versiones
    ('Total Debt', 'Total Liabilities Net Minority Interest', ...), por eso se
    intenta una lista de alias en vez de un nombre fijo.
    """
    if df is None or getattr(df, "empty", True):
        return None
    for nombre in alias:
        if nombre in df.index:
            serie = df.loc[nombre].dropna()
            if len(serie):
                return _numero(serie.iloc[0])
    return None


def _derivar_fundamentales(tk, datos: DatosMercado) -> None:
    """
    Estima NAV/CBFI, P/NAV, LTV y FFO desde los estados financieros.

    Por que el valor contable sirve como NAV: las FIBRAs reportan bajo IFRS y
    valuan sus propiedades con el modelo de valor razonable de la IAS 40, o
    sea que las remiden a valor de mercado cada periodo. El capital contable
    ya trae ese valuo dentro. En una empresa industrial esto no aplicaria.
    """
    try:
        info = tk.info or {}
    except Exception:
        info = {}

    # P/NAV: Yahoo ya publica priceToBook, que bajo IAS 40 es justo lo que
    # interesa. Es la via mas directa y la menos propensa a errores de armado.
    datos.p_nav = _numero(info.get("priceToBook"))
    datos.nav_por_cbfi = _numero(info.get("bookValue"))

    if datos.nav_por_cbfi and not datos.p_nav and datos.precio:
        datos.p_nav = datos.precio / datos.nav_por_cbfi

    try:
        balance = tk.quarterly_balance_sheet
        if balance is None or getattr(balance, "empty", True):
            balance = tk.balance_sheet
    except Exception:
        balance = None

    if balance is not None and not getattr(balance, "empty", True):
        try:
            datos.fecha_balance = str(balance.columns[0].date())
        except Exception:
            pass

        activos = _fila_balance(balance, "Total Assets")
        deuda = _fila_balance(balance, "Total Debt",
                              "Long Term Debt And Capital Lease Obligation",
                              "Long Term Debt")
        capital = _fila_balance(balance, "Stockholders Equity",
                                "Total Equity Gross Minority Interest")

        # LTV contra activos totales. La FIBRA lo reporta contra el valor de
        # sus propiedades, que es un poco menor, asi que esta estimacion tira
        # bajo: un LTV limpio aqui puede estar apretado en el reporte oficial.
        if deuda and activos:
            datos.ltv = deuda / activos
            datos.avisos.append("LTV estimado sobre activos totales")

        if not datos.nav_por_cbfi and capital:
            acciones = _numero(info.get("sharesOutstanding"))
            if acciones:
                datos.nav_por_cbfi = capital / acciones
                if datos.precio:
                    datos.p_nav = datos.precio / datos.nav_por_cbfi

    # FFO: se usa el flujo operativo por CBFI como proxy. El FFO formal parte
    # de la utilidad neta y le resta la revaluacion de inmuebles, que es el
    # renglon que mas distorsiona a una FIBRA; el flujo operativo ya viene
    # limpio de esa partida virtual.
    try:
        flujo = tk.quarterly_cashflow
        # El trimestral se anualiza x4; el anual se toma tal cual. La bandera
        # se fija aqui: comparar despues con `is tk.quarterly_cashflow` volveria
        # a invocar la propiedad y daria un objeto distinto.
        factor = 4
        if flujo is None or getattr(flujo, "empty", True):
            flujo = tk.cashflow
            factor = 1

        operativo = _fila_balance(flujo, "Operating Cash Flow",
                                  "Total Cash From Operating Activities")
        acciones = _numero(info.get("sharesOutstanding"))
        if operativo and acciones:
            datos.ffo_por_cbfi_anual = (operativo * factor) / acciones
            datos.avisos.append("FFO aproximado con flujo operativo")
    except Exception:
        pass


# Senales de que el problema es la red y no el ticker. yfinance envuelve el
# fallo de conexion en excepciones variadas (TypeError incluido), asi que se
# clasifica por el texto y no por el tipo.
_SENALES_DE_RED = ("connect", "tunnel", "connection", "max retries", "timed out",
                   "timeout", "failed to perform", "nonetype", "getaddrinfo",
                   "ssl", "proxy", "resolve")


def describir_fallo(e: Exception) -> str:
    """Traduce la excepcion a algo que le sirva a quien ejecuta el programa."""
    texto = str(e).lower()
    if any(s in texto for s in _SENALES_DE_RED):
        return "sin conexion a Yahoo Finance (revisa internet/firewall)"
    return f"{type(e).__name__}: {str(e)[:60]}"


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

@dataclass
class FIBRA:
    ticker: str

    # De mercado (se descargan, o se ponen a mano con --sin-red)
    precio_cbfi: Optional[float] = None
    distribucion_anual: Optional[float] = None

    # Tu costo de oportunidad: CETES/TIIE a 1 año + spread por el riesgo del
    # portafolio. Manda sobre toda la evaluacion.
    yield_exigido: float = 0.10

    # Del reporte trimestral (JSON). Sin dato, el criterio se omite.
    affo_por_cbfi_anual: Optional[float] = None
    ffo_por_cbfi_anual: Optional[float] = None
    nav_por_cbfi: Optional[float] = None
    ltv: Optional[float] = None
    ocupacion: Optional[float] = None

    mercado: DatosMercado = field(default_factory=DatosMercado)

    # campo -> "auto" (derivado de Yahoo) o "manual" (del JSON).
    procedencia: dict = field(default_factory=dict)

    def completar_con(self, m: DatosMercado) -> None:
        """
        Rellena con lo descargado SOLO lo que no venga del JSON.

        El dato del reporte trimestral manda sobre la estimacion: es la cifra
        oficial de la FIBRA, no una derivacion del balance.
        """
        auto = {
            "precio_cbfi": m.precio,
            "distribucion_anual": m.distribucion_12m,
            "nav_por_cbfi": m.nav_por_cbfi,
            "ltv": m.ltv,
            "ffo_por_cbfi_anual": m.ffo_por_cbfi_anual,
        }
        for campo, valor in auto.items():
            if getattr(self, campo) is None and valor is not None:
                setattr(self, campo, valor)
                self.procedencia[campo] = "auto"

    def marca(self, campo: str) -> str:
        if getattr(self, campo) is None:
            return ""
        return "auto" if self.procedencia.get(campo) == "auto" else "manual"

    @property
    def nombre(self) -> str:
        return CATALOGO.get(self.ticker, (self.ticker, ""))[0]

    @property
    def sector(self) -> str:
        return CATALOGO.get(self.ticker, ("", "sin catalogar"))[1]


class AnalizadorFIBRA:
    def __init__(self, fibra: FIBRA):
        self.f = fibra

    def distribution_yield(self) -> Optional[float]:
        if not self.f.precio_cbfi or not self.f.distribucion_anual:
            return None
        return self.f.distribucion_anual / self.f.precio_cbfi

    def base_payout(self):
        """
        Contra que se mide el payout: AFFO si lo tienes, si no FFO.

        AFFO es no-GAAP y cada FIBRA lo define distinto, asi que no hay forma
        de derivarlo del balance. FFO sirve de sustituto, pero es mas laxo:
        no descuenta el capex de mantenimiento, asi que un payout calculado
        sobre FFO sale mas bajo que el real.
        """
        if self.f.affo_por_cbfi_anual:
            return self.f.affo_por_cbfi_anual, "AFFO"
        if self.f.ffo_por_cbfi_anual:
            return self.f.ffo_por_cbfi_anual, "FFO"
        return None, None

    def payout_affo(self) -> Optional[float]:
        """
        Que porcion del flujo distribuible se esta repartiendo.

        Arriba de 100% reparte mas de lo que genera: lo cubre con deuda, venta
        de activos o reembolso de capital. Un yield alto con payout > 100% no
        es rendimiento, es liquidacion lenta.
        """
        base, _ = self.base_payout()
        if not base or not self.f.distribucion_anual:
            return None
        return self.f.distribucion_anual / base

    def p_ffo(self) -> Optional[float]:
        if not self.f.ffo_por_cbfi_anual or not self.f.precio_cbfi:
            return None
        return self.f.precio_cbfi / self.f.ffo_por_cbfi_anual

    def p_nav(self) -> Optional[float]:
        """< 1.0 = compras el ladrillo con descuento. > 1.0 = pagas premio."""
        if self.f.nav_por_cbfi and self.f.precio_cbfi:
            return self.f.precio_cbfi / self.f.nav_por_cbfi
        # Yahoo puede dar priceToBook sin dar bookValue.
        return self.f.mercado.p_nav

    def evaluar(self) -> dict:
        criterios = {}

        y = self.distribution_yield()
        if y is not None:
            criterios["Yield supera tu tasa exigida"] = y >= self.f.yield_exigido

        payout = self.payout_affo()
        _, base_nombre = self.base_payout()
        if payout is not None:
            criterios[f"Distribucion sostenible (payout <= 100% {base_nombre})"] = payout <= 1.0

        pnav = self.p_nav()
        if pnav is not None:
            criterios["Cotiza con descuento sobre NAV"] = pnav < 1.0

        if self.f.ltv is not None:
            criterios["Apalancamiento sano (LTV < 40%)"] = self.f.ltv < 0.40

        if self.f.ocupacion is not None:
            criterios["Ocupacion solida (> 90%)"] = self.f.ocupacion > 0.90

        cumplidos = sum(criterios.values())
        total = len(criterios)

        if total == 0:
            recomendacion = "SIN DATOS"
        else:
            proporcion = cumplidos / total
            if proporcion >= 0.75:
                recomendacion = "COMPRAR"
            elif proporcion >= 0.50:
                recomendacion = "VIGILAR"
            else:
                recomendacion = "EVITAR"

            # Un payout insostenible invalida cualquier otra virtud: el yield
            # que atrae hoy es justo el que se va a recortar.
            if payout is not None and payout > 1.10:
                recomendacion = "EVITAR (payout insostenible)"

        return {
            "yield": y, "payout_affo": payout, "p_ffo": self.p_ffo(),
            "p_nav": pnav, "criterios": criterios, "cumplidos": cumplidos,
            "total": total, "recomendacion": recomendacion,
        }

    def mostrar(self):
        r = self.evaluar()
        f = self.f
        m = f.mercado

        print("\n" + "=" * 72)
        print(f"  {f.ticker} — {f.nombre}")
        print(f"  {f.sector}")
        print("=" * 72)

        def linea(etiqueta, valor, nota="", campo=None):
            origen = f"[{f.marca(campo)}]" if campo and f.marca(campo) else ""
            print(f"  {etiqueta:<26}{valor:>12}  {origen:<9}{nota}".rstrip())

        print("\nMERCADO", end="")
        if m.ok:
            sello = m.fecha_ultimo_pago or "en vivo"
            print(f"   (Yahoo Finance, ultimo pago {sello})")
        elif m.error:
            print(f"   (descarga fallo: {m.error} — usando JSON)")
        else:
            print("   (datos del JSON)")

        linea("Precio por CBFI",
              f"${f.precio_cbfi:,.2f}" if f.precio_cbfi else "sin dato",
              campo="precio_cbfi")
        if f.distribucion_anual:
            nota = f"{m.n_pagos_12m} pagos en 12m" if m.n_pagos_12m else ""
            linea("Distribucion 12 meses", f"${f.distribucion_anual:,.4f}", nota,
                  campo="distribucion_anual")
        else:
            linea("Distribucion 12 meses", "sin dato")
        linea("Distribution yield", f"{r['yield']*100:.2f}%" if r["yield"] else "sin dato")
        linea("Tu tasa exigida", f"{f.yield_exigido*100:.2f}%")

        etiqueta_balance = f" — balance al {m.fecha_balance}" if m.fecha_balance else ""
        print(f"\nVALUACION Y SOSTENIBILIDAD{etiqueta_balance}")

        _, base_nombre = AnalizadorFIBRA(f).base_payout()
        if r["payout_affo"] is not None:
            nota = "sostenible" if r["payout_affo"] <= 1.0 else "REPARTE DE MAS"
            linea(f"Payout sobre {base_nombre}", f"{r['payout_affo']*100:.1f}%", f"({nota})")
        else:
            linea("Payout sobre AFFO/FFO", "sin dato")

        linea("P/FFO", f"{r['p_ffo']:.2f}x" if r["p_ffo"] else "sin dato",
              campo="ffo_por_cbfi_anual")

        if r["p_nav"] is not None:
            brecha = (r["p_nav"] - 1) * 100
            nota = f"descuento {abs(brecha):.1f}%" if brecha < 0 else f"premio {brecha:.1f}%"
            linea("P/NAV", f"{r['p_nav']:.2f}x", f"({nota})", campo="nav_por_cbfi")
        else:
            linea("P/NAV", "sin dato")

        linea("LTV (apalancamiento)",
              f"{f.ltv*100:.1f}%" if f.ltv is not None else "sin dato",
              "(limite CNBV: 50%)" if f.ltv is not None else "", campo="ltv")
        linea("Ocupacion",
              f"{f.ocupacion*100:.1f}%" if f.ocupacion is not None else "sin dato (solo en el reporte)",
              campo="ocupacion")

        if m.avisos:
            print("\n  Sobre los estimados [auto]:")
            for aviso in dict.fromkeys(m.avisos):
                print(f"    - {aviso}")

        print("\nCRITERIOS")
        if not r["criterios"]:
            print("  (ninguno evaluable: faltan datos)")
        for criterio, cumplido in r["criterios"].items():
            print(f"  [{'X' if cumplido else ' '}] {criterio}")
        omitidos = 5 - r["total"]
        if omitidos > 0:
            print(f"\n  ({omitidos} criterio(s) omitido(s) por falta de datos)")

        print(f"\n  >>> {r['recomendacion']}  ({r['cumplidos']}/{r['total']} criterios)")
        print("=" * 72)


# ---------------------------------------------------------------------------
# Persistencia de fundamentales
# ---------------------------------------------------------------------------

CAMPOS_JSON = ["yield_exigido", "affo_por_cbfi_anual", "ffo_por_cbfi_anual",
               "nav_por_cbfi", "ltv", "ocupacion", "precio_cbfi",
               "distribucion_anual"]


def plantilla_json() -> dict:
    return {
        "_ayuda": {
            "de_donde": "Reporte trimestral de cada FIBRA (relacion con inversionistas).",
            "yield_exigido": "Tu tasa exigida: CETES/TIIE 1 año + spread. 0.10 = 10%",
            "affo_por_cbfi_anual": "AFFO anual por CBFI, en pesos.",
            "nav_por_cbfi": "Valor de los inmuebles por CBFI, en pesos.",
            "ltv": "Apalancamiento. 0.259 = 25.9%",
            "ocupacion": "0.96 = 96%",
            "precio_cbfi": "Solo si corres --sin-red; normalmente se descarga.",
            "nota": "Deja en null lo que no tengas: el criterio se omite.",
        },
        "fibras": {
            "FUNO11": {"yield_exigido": 0.10, "affo_por_cbfi_anual": None,
                       "ffo_por_cbfi_anual": None, "nav_por_cbfi": None,
                       "ltv": None, "ocupacion": None},
            "FMTY14": {"yield_exigido": 0.10, "affo_por_cbfi_anual": None,
                       "ffo_por_cbfi_anual": None, "nav_por_cbfi": None,
                       "ltv": None, "ocupacion": None},
        },
    }


def cargar_fundamentales() -> dict:
    ruta = directorio_datos() / ARCHIVO_FUNDAMENTALES
    if not ruta.exists():
        ruta.write_text(json.dumps(plantilla_json(), indent=2, ensure_ascii=False),
                        encoding="utf-8")
        print(f"\n  Se creo {ruta.name} con una plantilla.")
        print("  Llenalo con el reporte trimestral para activar los criterios")
        print("  de sostenibilidad, valuacion y riesgo.\n")
        return plantilla_json()["fibras"]

    try:
        return json.loads(ruta.read_text(encoding="utf-8")).get("fibras", {})
    except json.JSONDecodeError as e:
        print(f"\n  {ruta.name} tiene un error de sintaxis JSON: {e}")
        print("  Se ignora; corrigelo o borralo para regenerarlo.\n")
        return {}


# ---------------------------------------------------------------------------
# Presentacion
# ---------------------------------------------------------------------------

def listar_catalogo():
    print("\nFIBRAS LISTADAS EN LA BMV\n")
    print(f"{'Ticker':<12}{'Yahoo':<15}{'Nombre':<20}{'Sector'}")
    print("-" * 78)
    for ticker, (nombre, sector) in CATALOGO.items():
        print(f"{ticker:<12}{ticker + '.MX':<15}{nombre:<20}{sector}")
    print()


def tabla_comparativa(fibras):
    print("\n\nCOMPARATIVA\n")
    print(f"{'Ticker':<11}{'Precio':>9}{'Yield':>8}{'Payout':>9}"
          f"{'P/NAV':>8}{'LTV':>7}{'Ocup':>7}  {'Veredicto'}")
    print("-" * 78)

    def fmt(v, suf="", ancho=7, dec=1, escala=1):
        if v is None:
            return f"{'--':>{ancho}}"
        return f"{v * escala:>{ancho - len(suf)}.{dec}f}{suf}"

    for fibra in fibras:
        r = AnalizadorFIBRA(fibra).evaluar()
        print(f"{fibra.ticker:<11}"
              f"{fmt(fibra.precio_cbfi, '', 9, 2)}"
              f"{fmt(r['yield'], '%', 8, 1, 100)}"
              f"{fmt(r['payout_affo'], '%', 9, 0, 100)}"
              f"{fmt(r['p_nav'], 'x', 8, 2)}"
              f"{fmt(fibra.ltv, '%', 7, 0, 100)}"
              f"{fmt(fibra.ocupacion, '%', 7, 0, 100)}"
              f"  {r['recomendacion']}")


def main():
    args = [a for a in sys.argv[1:]]
    sin_red = "--sin-red" in args
    args = [a for a in args if not a.startswith("--")]

    print("\n" + "=" * 72)
    print("  ANALIZADOR DE CBFIs (FIBRAs) — BMV / GBM")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 72)

    if "--catalogo" in sys.argv[1:]:
        listar_catalogo()
        return

    fundamentales = cargar_fundamentales()

    tickers = [t.upper() for t in args] or list(fundamentales.keys())
    if not tickers:
        print("\n  No hay FIBRAs que analizar. Agrega alguna al JSON o pasala")
        print("  como argumento:  python analizar_cbfi.py FUNO11\n")
        return

    desconocidos = [t for t in tickers if t not in CATALOGO]
    if desconocidos:
        print(f"\n  Aviso: no estan en el catalogo de la BMV: {', '.join(desconocidos)}")

    fibras = []
    for ticker in tickers:
        datos = fundamentales.get(ticker, {})
        fibra = FIBRA(ticker=ticker,
                      **{k: datos.get(k) for k in CAMPOS_JSON if datos.get(k) is not None})

        if not sin_red:
            print(f"  Descargando {ticker}...", end="\r")
            mercado = descargar(ticker)
            fibra.mercado = mercado
            if mercado.ok:
                fibra.completar_con(mercado)
            print(" " * 40, end="\r")

        fibras.append(fibra)

    for fibra in fibras:
        AnalizadorFIBRA(fibra).mostrar()

    if len(fibras) > 1:
        tabla_comparativa(fibras)

    print("\n" + "=" * 72)
    print("COMO LEER ESTO")
    print("=" * 72)
    print("  Yield alto + payout > 100%  ->  trampa: el recorte ya viene")
    print("  P/NAV < 1                   ->  compras ladrillo con descuento")
    print("  LTV > 40%                   ->  poco margen ante alza de tasas")
    print("  Ocupacion < 90%             ->  revisa vencimientos de contratos")
    print()
    print(f"  Precio y distribuciones: Yahoo Finance, pueden traer retraso.")
    print(f"  Confirma en GBM antes de operar.")
    print(f"  Fundamentales: {ARCHIVO_FUNDAMENTALES} (llenalo del reporte trimestral)")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()
