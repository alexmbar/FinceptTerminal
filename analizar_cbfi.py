#!/usr/bin/env python3
"""
Analizador de CBFIs (FIBRAs) — BMV / GBM México
===============================================

Un CBFI es el certificado de participacion en una FIBRA: cotiza como accion,
no como bono. No tiene cupon, ni vencimiento, ni valor nominal a redimir, asi
que YTM y duration no aplican. Lo que se mide aqui es lo que si define a un
vehiculo inmobiliario:

    - Distribution yield  : cuanto reparte contra lo que cuesta
    - Payout sobre AFFO   : si esa distribucion es sostenible o se come el flujo
    - P/NAV               : si cotiza con premio o descuento sobre sus inmuebles
    - P/FFO               : multiplo sobre flujo operativo
    - LTV                 : apalancamiento (limite regulatorio CNBV: 50%)
    - Ocupacion           : salud del portafolio

De donde salen los datos:
    - precio_cbfi          -> pantalla de GBM
    - distribucion_periodo -> aviso de distribucion en BMV / relacion con
                              inversionistas de la FIBRA
    - ffo / affo / nav     -> reporte trimestral de la FIBRA
    - ltv / ocupacion      -> mismo reporte trimestral

Uso:
    python analizar_cbfi.py
"""

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Catalogo de FIBRAs listadas en la BMV.
#
# Tickers y sectores verificados. Los datos financieros NO vienen precargados
# a proposito: cambian cada trimestre y ponerlos aqui invitaria a operar con
# cifras viejas. Sufijo .MX para Yahoo Finance (FUNO11.MX, DANHOS13.MX, ...).
# ---------------------------------------------------------------------------
CATALOGO = {
    "FUNO11":    ("Fibra Uno",        "Diversificada (comercial/industrial/oficinas)"),
    "FIBRAMQ12": ("Fibra Macquarie",  "Industrial"),
    "FIBRAPL14": ("Fibra Prologis",   "Industrial"),
    "DANHOS13":  ("Fibra Danhos",     "Comercial / oficinas"),
    "FMTY14":    ("Fibra Monterrey",  "Diversificada (distribuye mensual)"),
    "FSHOP13":   ("Fibra Shop",       "Centros comerciales"),
    "FIHO12":    ("Fibra Hotel",      "Hotelero"),
    "FINN13":    ("Fibra Inn",        "Hotelero"),
    "FHIPO14":   ("FHipo",            "Hipotecario"),
    "FNOVA17":   ("Fibra Nova",       "Industrial"),
    "FPLUS16":   ("Fibra Plus",       "Desarrollo"),
    "STORAGE18": ("Fibra Storage",    "Self-storage"),
    "EDUCA18":   ("Fibra Educa",      "Educativo"),
    "FCFE18":    ("Fibra CFE",        "Energia (FIBRA E)"),
    "FMX23":     ("Fibra FMX23",      "Sector sin confirmar"),
    "NEXT25":    ("Fibra NEXT25",     "Sector sin confirmar"),
}


@dataclass
class FIBRA:
    """Una FIBRA con los datos de su ultimo reporte trimestral."""

    ticker: str
    precio_cbfi: float           # MXN por CBFI (pantalla de GBM)
    distribucion_periodo: float  # MXN por CBFI del ultimo periodo
    periodos_por_anio: int       # 4 = trimestral, 12 = mensual

    # Tasa que exiges para asumir riesgo inmobiliario mexicano.
    # Referencia: CETES/TIIE a 1 año + spread. Es tu costo de oportunidad y
    # manda sobre toda la evaluacion: subelo si el portafolio es mas riesgoso.
    yield_exigido: float = 0.10

    # Opcionales: si no los tienes, el criterio correspondiente se omite en
    # vez de inventarse un valor.
    affo_por_cbfi_anual: Optional[float] = None  # flujo distribuible real
    ffo_por_cbfi_anual: Optional[float] = None
    nav_por_cbfi: Optional[float] = None         # valor de inmuebles por CBFI
    ltv: Optional[float] = None                  # 0.259 = 25.9%
    ocupacion: Optional[float] = None            # 0.96 = 96%

    @property
    def nombre(self) -> str:
        return CATALOGO.get(self.ticker, (self.ticker, ""))[0]

    @property
    def sector(self) -> str:
        return CATALOGO.get(self.ticker, ("", "sin catalogar"))[1]


class AnalizadorFIBRA:
    """Metricas de valuacion de un CBFI."""

    def __init__(self, fibra: FIBRA):
        self.f = fibra

    # --- Metricas base ----------------------------------------------------

    def distribucion_anual(self) -> float:
        """Distribucion anualizada por CBFI."""
        return self.f.distribucion_periodo * self.f.periodos_por_anio

    def distribution_yield(self) -> float:
        """Lo que te reparte al año contra lo que cuesta hoy."""
        return self.distribucion_anual() / self.f.precio_cbfi

    def payout_affo(self) -> Optional[float]:
        """
        Que porcion del flujo distribuible se esta repartiendo.

        Arriba de 100% significa que reparte mas de lo que genera: lo cubre
        con deuda, venta de activos o reembolso de capital. Un yield alto con
        payout > 100% no es rendimiento, es liquidacion lenta.
        """
        if not self.f.affo_por_cbfi_anual:
            return None
        return self.distribucion_anual() / self.f.affo_por_cbfi_anual

    def p_ffo(self) -> Optional[float]:
        """Multiplo precio / flujo operativo. Analogo al P/E de una accion."""
        if not self.f.ffo_por_cbfi_anual:
            return None
        return self.f.precio_cbfi / self.f.ffo_por_cbfi_anual

    def p_nav(self) -> Optional[float]:
        """
        Precio contra valor de los inmuebles por CBFI.

        < 1.0 = cotiza con descuento sobre el ladrillo.
        > 1.0 = pagas premio sobre el valuo.
        """
        if not self.f.nav_por_cbfi:
            return None
        return self.f.precio_cbfi / self.f.nav_por_cbfi

    # --- Evaluacion -------------------------------------------------------

    def evaluar(self) -> dict:
        """
        Corre los criterios que aplican con los datos disponibles.

        Los criterios sin dato se omiten en lugar de contarse como fallo, para
        que un reporte incompleto no se vea como una FIBRA mala.
        """
        criterios = {}

        criterios["Yield supera tu tasa exigida"] = (
            self.distribution_yield() >= self.f.yield_exigido
        )

        payout = self.payout_affo()
        if payout is not None:
            criterios["Distribucion sostenible (payout <= 100% AFFO)"] = payout <= 1.0

        pnav = self.p_nav()
        if pnav is not None:
            criterios["Cotiza con descuento sobre NAV"] = pnav < 1.0

        if self.f.ltv is not None:
            # CNBV topa el apalancamiento en 50%. Debajo de 40% es comodo.
            criterios["Apalancamiento sano (LTV < 40%)"] = self.f.ltv < 0.40

        if self.f.ocupacion is not None:
            criterios["Ocupacion solida (> 90%)"] = self.f.ocupacion > 0.90

        cumplidos = sum(criterios.values())
        total = len(criterios)
        proporcion = cumplidos / total if total else 0

        if proporcion >= 0.75:
            recomendacion = "COMPRAR"
        elif proporcion >= 0.50:
            recomendacion = "VIGILAR"
        else:
            recomendacion = "EVITAR"

        # Un payout insostenible invalida cualquier otra virtud: el yield que
        # atrae hoy es justo el que se va a recortar.
        if payout is not None and payout > 1.10:
            recomendacion = "EVITAR (payout insostenible)"

        return {
            "yield": self.distribution_yield(),
            "distribucion_anual": self.distribucion_anual(),
            "payout_affo": payout,
            "p_ffo": self.p_ffo(),
            "p_nav": pnav,
            "criterios": criterios,
            "cumplidos": cumplidos,
            "total": total,
            "recomendacion": recomendacion,
        }

    # --- Presentacion -----------------------------------------------------

    def mostrar(self):
        r = self.evaluar()
        f = self.f

        print("\n" + "=" * 72)
        print(f"  {f.ticker} — {f.nombre}")
        print(f"  {f.sector}")
        print("=" * 72)

        frecuencia = {4: "trimestral", 12: "mensual"}.get(
            f.periodos_por_anio, f"{f.periodos_por_anio}x al año"
        )

        print("\nPRECIO Y DISTRIBUCION")
        print(f"  Precio por CBFI          ${f.precio_cbfi:>10,.2f}")
        print(f"  Distribucion {frecuencia:<12} ${f.distribucion_periodo:>10,.4f}")
        print(f"  Distribucion anualizada  ${r['distribucion_anual']:>10,.4f}")
        print(f"  Distribution yield       {r['yield']*100:>10.2f}%")
        print(f"  Tu tasa exigida          {f.yield_exigido*100:>10.2f}%")

        print("\nVALUACION Y SOSTENIBILIDAD")
        if r["payout_affo"] is not None:
            nota = "sostenible" if r["payout_affo"] <= 1.0 else "REPARTE DE MAS"
            print(f"  Payout sobre AFFO        {r['payout_affo']*100:>10.1f}%   ({nota})")
        else:
            print(f"  Payout sobre AFFO        {'sin dato':>10}")

        if r["p_ffo"] is not None:
            print(f"  P/FFO                    {r['p_ffo']:>10.2f}x")
        else:
            print(f"  P/FFO                    {'sin dato':>10}")

        if r["p_nav"] is not None:
            brecha = (r["p_nav"] - 1) * 100
            nota = f"descuento {abs(brecha):.1f}%" if brecha < 0 else f"premio {brecha:.1f}%"
            print(f"  P/NAV                    {r['p_nav']:>10.2f}x   ({nota})")
        else:
            print(f"  P/NAV                    {'sin dato':>10}")

        print("\nPORTAFOLIO")
        if f.ltv is not None:
            print(f"  LTV (apalancamiento)     {f.ltv*100:>10.1f}%   (limite CNBV: 50%)")
        else:
            print(f"  LTV (apalancamiento)     {'sin dato':>10}")
        if f.ocupacion is not None:
            print(f"  Ocupacion                {f.ocupacion*100:>10.1f}%")
        else:
            print(f"  Ocupacion                {'sin dato':>10}")

        print("\nCRITERIOS")
        for criterio, cumplido in r["criterios"].items():
            print(f"  [{'X' if cumplido else ' '}] {criterio}")

        omitidos = 5 - r["total"]
        if omitidos > 0:
            print(f"\n  ({omitidos} criterio(s) omitido(s) por falta de datos)")

        print(f"\n  >>> {r['recomendacion']}  ({r['cumplidos']}/{r['total']} criterios)")
        print("=" * 72)


def tabla_comparativa(fibras):
    print("\n\nCOMPARATIVA\n")
    print(
        f"{'Ticker':<11}{'Precio':>9}{'Yield':>8}{'Payout':>9}"
        f"{'P/NAV':>8}{'LTV':>7}{'Ocup':>7}  {'Veredicto'}"
    )
    print("-" * 78)

    def fmt(valor, sufijo="", ancho=7, dec=1, escala=1):
        if valor is None:
            return f"{'--':>{ancho}}"
        return f"{valor*escala:>{ancho-len(sufijo)}.{dec}f}{sufijo}"

    for fibra in fibras:
        r = AnalizadorFIBRA(fibra).evaluar()
        print(
            f"{fibra.ticker:<11}"
            f"{fibra.precio_cbfi:>9,.2f}"
            f"{fmt(r['yield'], '%', 8, 1, 100)}"
            f"{fmt(r['payout_affo'], '%', 9, 0, 100)}"
            f"{fmt(r['p_nav'], 'x', 8, 2)}"
            f"{fmt(fibra.ltv, '%', 7, 0, 100)}"
            f"{fmt(fibra.ocupacion, '%', 7, 0, 100)}"
            f"  {r['recomendacion']}"
        )


def listar_catalogo():
    print("\nFIBRAS LISTADAS EN LA BMV\n")
    print(f"{'Ticker':<12}{'Yahoo':<15}{'Nombre':<20}{'Sector'}")
    print("-" * 78)
    for ticker, (nombre, sector) in CATALOGO.items():
        print(f"{ticker:<12}{ticker + '.MX':<15}{nombre:<20}{sector}")


def main():
    print("\n" + "=" * 72)
    print("  ANALIZADOR DE CBFIs (FIBRAs) — BMV / GBM")
    print("=" * 72)

    listar_catalogo()

    # -----------------------------------------------------------------------
    # EJEMPLOS CON DATOS INVENTADOS.
    #
    # Sirven para ver como responde el modelo, NO para decidir una compra.
    # Sustituye cada campo por el reporte trimestral de la FIBRA y el precio
    # de GBM antes de usar esto para algo real.
    # -----------------------------------------------------------------------
    print("\n\n" + "!" * 72)
    print("  Lo que sigue usa DATOS INVENTADOS de demostracion.")
    print("  Reemplazalos con el reporte trimestral y el precio de GBM.")
    print("!" * 72)

    ejemplos = [
        FIBRA(
            ticker="FUNO11",
            precio_cbfi=27.00,
            distribucion_periodo=0.67,
            periodos_por_anio=4,
            yield_exigido=0.10,
            affo_por_cbfi_anual=2.90,
            ffo_por_cbfi_anual=3.40,
            nav_por_cbfi=38.00,
            ltv=0.42,
            ocupacion=0.94,
        ),
        FIBRA(
            ticker="FMTY14",
            precio_cbfi=12.50,
            distribucion_periodo=0.085,
            periodos_por_anio=12,   # esta distribuye mensual
            yield_exigido=0.10,
            affo_por_cbfi_anual=1.15,
            ffo_por_cbfi_anual=1.30,
            nav_por_cbfi=14.20,
            ltv=0.259,
            ocupacion=0.965,
        ),
        FIBRA(
            ticker="FSHOP13",
            precio_cbfi=8.20,
            distribucion_periodo=0.32,
            periodos_por_anio=4,
            yield_exigido=0.11,     # retail puro: exiges mas
            affo_por_cbfi_anual=1.05,
            nav_por_cbfi=11.50,
            ltv=0.38,
            ocupacion=0.89,
        ),
    ]

    for fibra in ejemplos:
        AnalizadorFIBRA(fibra).mostrar()

    tabla_comparativa(ejemplos)

    print("\n" + "=" * 72)
    print("COMO LEER ESTO")
    print("=" * 72)
    print("  Yield alto + payout > 100%  ->  trampa: el recorte ya viene")
    print("  P/NAV < 1                   ->  compras ladrillo con descuento")
    print("  LTV > 40%                   ->  poco margen ante alza de tasas")
    print("  Ocupacion < 90%             ->  revisa vencimientos de contratos")
    print()
    print("  El veredicto depende de yield_exigido. Ajustalo a CETES/TIIE")
    print("  del momento mas un spread por el riesgo del portafolio.")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()
