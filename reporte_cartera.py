#!/usr/bin/env python3
"""
Reporte PDF de tu cartera de GBM
=================================

Toma el Excel que exporta la app de GBM (cartera_gbm.leer_cartera) y lo
combina con el analisis de FIBRAs de analizar_cbfi.py para armar un PDF
centrado en TU posicion: cuanto tienes de cada emisora, cuanta plusvalia o
minusvalia llevas, que tan concentrada esta la cartera, y que dice el
analisis sobre seguir sosteniendo cada una.

No reemplaza analisis_cbfi_YYYY-MM-DD.pdf (la comparativa de las FIBRAs del
catalogo): ese es sobre que comprar, este es sobre lo que ya compraste.

Uso:
    python analizar_cbfi.py --cartera "Detalle Portafolio.xlsx"

Requiere: pip install reportlab openpyxl
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from reporte_pdf import VERDE, ROJO, GRIS, GRIS_CLARO, BORDE, TINTA, _color_veredicto

# Una posicion que pesa mas de esto en la cartera se marca como concentrada,
# sin importar el veredicto: hasta una FIBRA sana es un riesgo si es medio
# portafolio.
UMBRAL_CONCENTRACION = 0.25


def _money(v) -> str:
    if v is None:
        return "—"
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def _pct(v, dec=1) -> str:
    return f"{v * 100:.{dec}f}%" if v is not None else "—"


def generar(cartera, fibras, ruta_salida: Optional[Path] = None) -> Path:
    """Escribe el PDF de cartera y devuelve la ruta. `fibras` son FIBRA ya analizadas."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer)

    from analizar_cbfi import AnalizadorFIBRA, directorio_datos

    if ruta_salida is None:
        sello = datetime.now().strftime("%Y-%m-%d")
        ruta_salida = directorio_datos() / f"cartera_gbm_{sello}.pdf"

    fibras_por_ticker = {f.ticker: f for f in fibras}

    hojas = getSampleStyleSheet()
    titulo = ParagraphStyle("titulo", parent=hojas["Title"], fontSize=18,
                            textColor=colors.HexColor(TINTA), spaceAfter=2,
                            alignment=TA_LEFT)
    subtitulo = ParagraphStyle("subtitulo", parent=hojas["Normal"], fontSize=9,
                               textColor=colors.HexColor(GRIS), spaceAfter=14)
    seccion = ParagraphStyle("seccion", parent=hojas["Heading2"], fontSize=12,
                             textColor=colors.HexColor(TINTA),
                             spaceBefore=14, spaceAfter=6)
    cuerpo = ParagraphStyle("cuerpo", parent=hojas["Normal"], fontSize=8.5,
                            textColor=colors.HexColor(TINTA), leading=12)
    nota = ParagraphStyle("nota", parent=hojas["Normal"], fontSize=7.5,
                          textColor=colors.HexColor(GRIS), leading=10.5)

    doc = SimpleDocTemplate(
        str(ruta_salida), pagesize=landscape(letter),
        leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm,
        title="Cartera GBM", author="Analizador CBFI")

    elementos = []
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")

    valor_total = cartera.valor_total
    plusvalia_total = cartera.plusvalia_total

    elementos.append(Paragraph("Mi cartera — GBM", titulo))
    elementos.append(Paragraph(
        f"Generado el {ahora} · {len(cartera.posiciones)} emisoras · "
        f"Valor total {_money(valor_total)} · "
        f"P/M acumulada {_money(plusvalia_total)} · "
        f"Fuente: {cartera.ruta.name if cartera.ruta else '—'}",
        subtitulo))

    # ---- Tabla de posiciones -----------------------------------------------
    elementos.append(Paragraph("Posiciones", seccion))

    encabezado = ["Emisora", "Titulos", "Costo prom", "Precio mdo",
                  "Valor mdo", "P/M", "% Cartera", "Veredicto"]
    filas = [encabezado]
    colores_veredicto = []

    for pos in cartera.posiciones:
        fibra = fibras_por_ticker.get(pos.ticker)
        veredicto = (AnalizadorFIBRA(fibra).evaluar()["recomendacion"]
                    if fibra is not None else "FUERA DE CATALOGO")
        filas.append([
            pos.nombre_gbm,
            f"{pos.titulos:g}",
            _money(pos.costo_promedio),
            _money(pos.precio_mercado),
            _money(pos.valor_mercado),
            _money(pos.plusvalia_minusvalia),
            _pct(pos.pct_cartera, 2),
            veredicto,
        ])
        colores_veredicto.append(_color_veredicto(veredicto))

    tabla = Table(filas, repeatRows=1, hAlign="LEFT",
                  colWidths=[42*mm, 18*mm, 22*mm, 22*mm, 24*mm, 22*mm, 20*mm, 62*mm])
    estilo = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(TINTA)),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GRIS_CLARO)),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor(BORDE)),
        ("ALIGN", (1, 0), (6, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#fbfcfd")]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor(BORDE)),
    ]
    for i, pos in enumerate(cartera.posiciones, start=1):
        estilo.append(("TEXTCOLOR", (7, i), (7, i), colors.HexColor(colores_veredicto[i - 1])))
        estilo.append(("FONTNAME", (0, i), (0, i), "Helvetica-Bold"))
        if pos.plusvalia_minusvalia is not None:
            color_pm = VERDE if pos.plusvalia_minusvalia >= 0 else ROJO
            estilo.append(("TEXTCOLOR", (5, i), (5, i), colors.HexColor(color_pm)))
    tabla.setStyle(TableStyle(estilo))
    elementos.append(tabla)
    elementos.append(Spacer(1, 6 * mm))

    # ---- Alertas de rebalanceo ----------------------------------------------
    elementos.append(Paragraph("Alertas de rebalanceo", seccion))
    alertas = []
    for pos in cartera.posiciones:
        if pos.pct_cartera is not None and pos.pct_cartera >= UMBRAL_CONCENTRACION:
            alertas.append(
                f"<b>{pos.nombre_gbm}</b> concentra {_pct(pos.pct_cartera, 1)} de la "
                f"cartera (umbral {_pct(UMBRAL_CONCENTRACION, 0)}) — revisa el tamaño "
                f"de la posición aunque el veredicto sea favorable.")
        fibra = fibras_por_ticker.get(pos.ticker)
        if fibra is not None and pos.titulos:
            veredicto = AnalizadorFIBRA(fibra).evaluar()["recomendacion"]
            if veredicto.startswith("EVITAR"):
                alertas.append(
                    f"<b>{pos.nombre_gbm}</b> tiene veredicto {veredicto} y sigues "
                    f"sosteniendo {pos.titulos:g} títulos "
                    f"({_pct(pos.pct_cartera, 1)} de la cartera).")

    if alertas:
        for a in alertas:
            elementos.append(Paragraph(f"• {a}", cuerpo))
            elementos.append(Spacer(1, 2))
    else:
        elementos.append(Paragraph(
            "Sin alertas: ninguna posición supera el umbral de concentración "
            f"({_pct(UMBRAL_CONCENTRACION, 0)}) ni tiene veredicto EVITAR.", cuerpo))
    elementos.append(Spacer(1, 6 * mm))

    # ---- Efectivo / liquidez -------------------------------------------------
    elementos.append(Paragraph("Efectivo y liquidez", seccion))
    filas_ef = [["Cuenta", "Valor", "% Cartera"]]
    for e in cartera.efectivo:
        filas_ef.append([e.cuenta, _money(e.valor_mercado), _pct(e.pct_cartera, 2)])
    pct_total_efectivo = (cartera.valor_efectivo / valor_total) if valor_total else None
    filas_ef.append(["Total efectivo", _money(cartera.valor_efectivo),
                     _pct(pct_total_efectivo, 2)])

    tabla_ef = Table(filas_ef, colWidths=[60*mm, 30*mm, 25*mm], hAlign="LEFT", repeatRows=1)
    tabla_ef.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GRIS_CLARO)),
        ("ALIGN", (1, 0), (2, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor(BORDE)),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    elementos.append(tabla_ef)
    elementos.append(Spacer(1, 6 * mm))

    # ---- Notas ---------------------------------------------------------------
    elementos.append(Paragraph("Notas", seccion))
    for linea in [
        "El veredicto de cada emisora viene del mismo análisis de "
        "analizar_cbfi.py (yield, payout, P/NAV, LTV, ocupación) — revisa el "
        "PDF comparativo (<i>analisis_cbfi_*.pdf</i>) para el detalle y las "
        "notas de procedencia de cada cifra.",

        "\"P/M\" es la plusvalía o minusvalía que reporta GBM para la posición "
        "completa (precio de mercado menos costo promedio, por el número de "
        "títulos). No incluye distribuciones ya cobradas.",

        "Este reporte es un resumen de tu posición actual, no una "
        "recomendación de compra o venta. Confirma cualquier movimiento en GBM.",
    ]:
        elementos.append(Paragraph(f"• {linea}", nota))
        elementos.append(Spacer(1, 2))

    elementos.append(Spacer(1, 4 * mm))
    elementos.append(Paragraph(
        f"Cartera tomada de: {cartera.ruta}" if cartera.ruta else "", nota))

    def pie(canvas, documento):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor(GRIS))
        canvas.drawString(16 * mm, 8 * mm, f"Cartera GBM · {ahora}")
        canvas.drawRightString(landscape(letter)[0] - 16 * mm, 8 * mm,
                               f"Página {documento.page}")
        canvas.restoreState()

    doc.build(elementos, onFirstPage=pie, onLaterPages=pie)
    return ruta_salida
