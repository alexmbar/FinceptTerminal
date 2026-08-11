#!/usr/bin/env python3
"""
Reporte PDF del analisis de CBFIs
=================================

Arma un documento con la comparativa de las FIBRAs, el detalle de cada una y
las notas de procedencia de los datos.

Las notas no son relleno: la mitad de las cifras son estimaciones derivadas
del balance y la otra mitad viene del reporte trimestral, y un PDF que se
guarda o se comparte pierde el contexto que la consola si muestra. Cada valor
va marcado con su origen y el documento cierra con sus limitaciones.

Uso:
    python analizar_cbfi.py --pdf
    python analizar_cbfi.py --pdf FUNO11 DANHOS13

Requiere: pip install reportlab
"""

from datetime import datetime
from pathlib import Path
from typing import Optional


# Paleta sobria: el color solo distingue el veredicto, no decora.
VERDE = "#1a7f37"
AMBAR = "#9a6700"
ROJO = "#b3261e"
GRIS = "#57606a"
GRIS_CLARO = "#f6f8fa"
BORDE = "#d0d7de"
TINTA = "#1f2328"


def _color_veredicto(veredicto: str) -> str:
    if veredicto.startswith("COMPRAR"):
        return VERDE
    if veredicto.startswith("VIGILAR"):
        return AMBAR
    if veredicto.startswith("EVITAR"):
        return ROJO
    return GRIS


def generar(fibras, ruta_salida: Optional[Path] = None, detalle: bool = True) -> Path:
    """Escribe el PDF y devuelve la ruta. `fibras` son objetos FIBRA ya analizados."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer, PageBreak)

    from analizar_cbfi import AnalizadorFIBRA, ARCHIVO_FUNDAMENTALES, directorio_datos

    if ruta_salida is None:
        sello = datetime.now().strftime("%Y-%m-%d")
        ruta_salida = directorio_datos() / f"analisis_cbfi_{sello}.pdf"

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
        title="Analisis de CBFIs (FIBRAs)", author="Analizador CBFI")

    elementos = []
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")

    elementos.append(Paragraph("Análisis de CBFIs — FIBRAs de la BMV", titulo))
    elementos.append(Paragraph(
        f"Generado el {ahora} · {len(fibras)} FIBRAs · "
        f"Precios de Yahoo Finance, fundamentales del reporte trimestral",
        subtitulo))

    # ---- Tabla comparativa -------------------------------------------------
    encabezado = ["Ticker", "Nombre", "Precio", "Yield", "Payout",
                  "P/NAV", "LTV", "Ocup.", "Veredicto"]
    filas = [encabezado]
    colores_fila = []

    def pct(v, dec=1):
        return f"{v * 100:.{dec}f}%" if v is not None else "—"

    for fibra in fibras:
        r = AnalizadorFIBRA(fibra).evaluar()
        filas.append([
            fibra.ticker,
            fibra.nombre,
            f"${fibra.precio_cbfi:,.2f}" if fibra.precio_cbfi else "—",
            pct(r["yield"]),
            pct(r["payout_affo"], 0),
            f"{r['p_nav']:.2f}x" if r["p_nav"] else "—",
            pct(fibra.ltv, 0),
            pct(fibra.ocupacion, 0),
            r["recomendacion"],
        ])
        colores_fila.append(_color_veredicto(r["recomendacion"]))

    tabla = Table(filas, repeatRows=1, hAlign="LEFT",
                  colWidths=[22*mm, 46*mm, 20*mm, 17*mm, 18*mm,
                             17*mm, 15*mm, 15*mm, 62*mm])

    estilo = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(TINTA)),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GRIS_CLARO)),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor(BORDE)),
        ("ALIGN", (2, 0), (7, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#fbfcfd")]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor(BORDE)),
    ]
    for i, color in enumerate(colores_fila, start=1):
        estilo.append(("TEXTCOLOR", (8, i), (8, i), colors.HexColor(color)))
        estilo.append(("FONTNAME", (0, i), (0, i), "Helvetica-Bold"))
    tabla.setStyle(TableStyle(estilo))

    elementos.append(tabla)
    elementos.append(Spacer(1, 8 * mm))

    # ---- Como leerla -------------------------------------------------------
    elementos.append(Paragraph("Cómo leer la tabla", seccion))
    for linea in [
        "<b>Yield alto con payout arriba de 100%</b> es una trampa: la FIBRA "
        "reparte más de lo que genera y el recorte ya viene en camino.",
        "<b>P/NAV menor a 1</b> significa que compras el inmueble con descuento "
        "sobre su valuación contable; arriba de 1 pagas premio.",
        "<b>LTV arriba de 40%</b> deja poco margen ante un alza de tasas. El "
        "límite regulatorio de la CNBV es 50%.",
        "<b>Ocupación abajo de 90%</b> obliga a revisar los vencimientos de "
        "contratos del portafolio.",
    ]:
        elementos.append(Paragraph(f"• {linea}", cuerpo))
        elementos.append(Spacer(1, 2))

    # ---- Detalle por FIBRA -------------------------------------------------
    if detalle:
        elementos.append(PageBreak())
        elementos.append(Paragraph("Detalle por FIBRA", seccion))

        for fibra in fibras:
            r = AnalizadorFIBRA(fibra).evaluar()
            m = fibra.mercado
            color = _color_veredicto(r["recomendacion"])

            elementos.append(Spacer(1, 4 * mm))
            elementos.append(Paragraph(
                f'<font color="{TINTA}"><b>{fibra.ticker}</b> — {fibra.nombre}</font>'
                f'<font color="{GRIS}" size="8"> · {fibra.sector}</font><br/>'
                f'<font color="{color}"><b>{r["recomendacion"]}</b></font>'
                f'<font color="{GRIS}" size="8"> · {r["cumplidos"]}/{r["total"]} criterios</font>',
                cuerpo))

            def marca(campo):
                origen = fibra.marca(campo)
                return f' <font size="6" color="{GRIS}">[{origen}]</font>' if origen else ""

            datos = [
                ["Precio", f"${fibra.precio_cbfi:,.2f}" if fibra.precio_cbfi else "—", "precio_cbfi"],
                ["Distribución 12m", f"${fibra.distribucion_anual:,.4f}" if fibra.distribucion_anual else "—", "distribucion_anual"],
                ["Distribution yield", pct(r["yield"], 2), None],
                ["Tasa exigida", pct(fibra.yield_exigido, 2), None],
                ["Payout", pct(r["payout_affo"], 1), None],
                ["P/NAV", f"{r['p_nav']:.2f}x" if r["p_nav"] else "—", "nav_por_cbfi"],
                ["LTV", pct(fibra.ltv, 1), "ltv"],
                ["Ocupación", pct(fibra.ocupacion, 1), "ocupacion"],
            ]
            filas_det = [[Paragraph(f'<font size="7.5" color="{GRIS}">{d[0]}</font>', cuerpo),
                          Paragraph(f'<font size="8">{d[1]}</font>'
                                    + (marca(d[2]) if d[2] else ""), cuerpo)]
                         for d in datos]

            t = Table(filas_det, colWidths=[38*mm, 42*mm], hAlign="LEFT")
            t.setStyle(TableStyle([
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))

            criterios_txt = "<br/>".join(
                f'<font color="{VERDE if ok else GRIS}">{"■" if ok else "□"}</font> '
                f'<font size="7.5">{c}</font>'
                for c, ok in r["criterios"].items()) or \
                f'<font size="7.5" color="{GRIS}">Sin criterios evaluables</font>'

            avisos_txt = "<br/>".join(
                f'<font size="6.5" color="{GRIS}">· {a}</font>'
                for a in dict.fromkeys(m.avisos)) if m.avisos else ""

            par = Table([[t, Paragraph(criterios_txt, cuerpo),
                          Paragraph(avisos_txt, nota)]],
                        colWidths=[82*mm, 78*mm, 72*mm], hAlign="LEFT")
            par.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
            ]))
            elementos.append(par)
            elementos.append(Spacer(1, 2 * mm))

    # ---- Procedencia y limitaciones ---------------------------------------
    elementos.append(PageBreak())
    elementos.append(Paragraph("Procedencia de los datos", seccion))

    tabla_fuentes = Table([
        ["Dato", "Origen", "Frecuencia"],
        ["Precio del CBFI", "Yahoo Finance, al ejecutar", "Continua"],
        ["Distribución 12 meses", "Yahoo Finance, dividendos pagados", "Por pago"],
        ["P/NAV", "Derivado: priceToBook de Yahoo", "Trimestral"],
        ["LTV", "Derivado del balance, o del reporte", "Trimestral"],
        ["FFO", "Derivado: flujo operativo por CBFI", "Trimestral"],
        ["AFFO", "Reporte trimestral (PDF)", "Trimestral"],
        ["Ocupación", "Reporte trimestral (PDF)", "Trimestral"],
    ], colWidths=[46*mm, 92*mm, 34*mm], hAlign="LEFT", repeatRows=1)
    tabla_fuentes.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GRIS_CLARO)),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor(BORDE)),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(tabla_fuentes)
    elementos.append(Spacer(1, 5 * mm))

    elementos.append(Paragraph("Limitaciones", seccion))
    for linea in [
        "Las marcas <b>[auto]</b> señalan estimaciones derivadas de estados "
        "financieros, no las cifras oficiales que publica la FIBRA. El LTV "
        "derivado se calcula sobre activos totales, mientras que la FIBRA lo "
        "reporta sobre el valor de sus propiedades, así que tiende a quedar "
        "por debajo del oficial. Las marcas <b>[manual]</b> vienen del reporte "
        "trimestral y son las cifras publicadas.",

        "Cuando no hay AFFO, el payout se mide contra FFO. Es una vara más "
        "laxa: el FFO no descuenta el capex de mantenimiento, así que un "
        "payout que aquí se ve holgado puede estar ajustado en realidad.",

        "Yahoo Finance dejó de actualizar los estados financieros de varias "
        "FIBRAs. Cuando el balance disponible tiene más de quince meses, los "
        "derivados se descartan y el veredicto lo dice explícitamente en vez "
        "de calificar con cifras vencidas.",

        "Un veredicto necesita al menos tres de los cinco criterios. Con menos "
        "datos aparece <b>DATOS INSUFICIENTES</b>: cumplir dos criterios de dos "
        "no es una conclusión, es un artefacto del hueco de información.",

        "Los precios pueden traer retraso y, en las FIBRAs de baja liquidez, "
        "la última cotización no siempre es ejecutable. <b>Confirma en GBM "
        "antes de operar.</b>",

        "Este documento es una herramienta de filtrado construida sobre datos "
        "públicos. No es asesoría de inversión ni sustituye la lectura del "
        "reporte trimestral y del prospecto de cada FIBRA.",
    ]:
        elementos.append(Paragraph(f"• {linea}", cuerpo))
        elementos.append(Spacer(1, 3))

    ruta_json = directorio_datos() / ARCHIVO_FUNDAMENTALES
    elementos.append(Spacer(1, 4 * mm))
    elementos.append(Paragraph(
        f"Fundamentales tomados de: {ruta_json}", nota))

    def pie(canvas, documento):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor(GRIS))
        canvas.drawString(16 * mm, 8 * mm, f"Análisis de CBFIs · {ahora}")
        canvas.drawRightString(landscape(letter)[0] - 16 * mm, 8 * mm,
                               f"Página {documento.page}")
        canvas.restoreState()

    doc.build(elementos, onFirstPage=pie, onLaterPages=pie)
    return ruta_salida
