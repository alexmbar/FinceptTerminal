#!/usr/bin/env python3
"""
Dashboard HTML de tu cartera de GBM
====================================

Toma una Cartera ya leida (cartera_gbm.leer_cartera) y escribe un .html
autocontenido -- sin dependencias externas, sin conexion a internet -- con
un vistazo visual de la posicion: valor total, plusvalia/minusvalia,
composicion, distribucion por emisora y detalle en tablas. Pensado para
abrirse en el navegador desde dashboard_gui.py, pero funciona igual con
doble clic.

No incluye historico (movimientos, tendencia mes a mes, dividendos
cobrados): el Excel de "Detalle de Portafolio" de GBM es una foto de un
solo momento, no una serie de tiempo -- inventar esas series seria mostrar
datos que no existen.

Requiere: nada además de la libreria estandar (los datos ya vienen de
cartera_gbm, que si necesita openpyxl).
"""

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Optional

from cartera_gbm import Cartera, PosicionCartera

# Paleta del proyecto (misma que reporte_pdf.py) para texto/estado, mas un
# orden categorico validado (skill de dataviz) para distinguir emisoras. Se
# deja fuera el rojo de esa lista: en este tablero el rojo ya significa
# "minusvalia" y no queremos que una emisora tome ese mismo tono por
# coincidencia de orden.
CATEGORICO_CLARO = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7"]
CATEGORICO_OSCURO = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9"]
# Texto legible sobre cada slot (blanco si el fondo es oscuro/saturado,
# tinta si es claro) -- "un label dentro de un relleno de color se resuelve
# por la luminancia del relleno", no siempre blanco.
CATEGORICO_TEXTO = ["#ffffff", "#ffffff", "#1f2328", "#1f2328", "#1f2328", "#ffffff", "#ffffff"]
GRIS_NEUTRO_CLARO = "#9aa1ab"
GRIS_NEUTRO_OSCURO = "#5b6270"
TINTA = "#1f2328"

MAX_CATEGORIAS = 7  # techo de la escalera de series del skill; el resto -> "Otros"


def _money(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def _pct(v: Optional[float], dec: int = 1) -> str:
    return f"{v * 100:.{dec}f}%" if v is not None else "—"


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _iniciales(nombre: str) -> str:
    letras = "".join(ch for ch in nombre if ch.isalpha())
    return (letras[:2] or nombre[:2] or "??").upper()


def _asignar_colores(cartera: Cartera) -> dict:
    """Un color fijo por emisora (mismo orden que su peso en la cartera),
    reutilizado en las barras, el donut y la tabla para que la misma
    emisora se identifique igual en todo el tablero."""
    ordenadas = sorted(cartera.posiciones, key=lambda p: p.valor_mercado or 0, reverse=True)
    colores = {}
    for i, p in enumerate(ordenadas):
        if i < len(CATEGORICO_CLARO):
            colores[p.nombre_gbm] = (CATEGORICO_CLARO[i], CATEGORICO_OSCURO[i], CATEGORICO_TEXTO[i])
        else:
            colores[p.nombre_gbm] = (GRIS_NEUTRO_CLARO, GRIS_NEUTRO_OSCURO, TINTA)
    colores["Efectivo"] = (GRIS_NEUTRO_CLARO, GRIS_NEUTRO_OSCURO, TINTA)
    colores["Otros"] = (GRIS_NEUTRO_CLARO, GRIS_NEUTRO_OSCURO, TINTA)
    return colores


def _avatar(nombre: str, colores: dict) -> str:
    light, dark, texto = colores.get(nombre, (GRIS_NEUTRO_CLARO, GRIS_NEUTRO_OSCURO, TINTA))
    return (f'<span class="avatar" style="--av-light:{light}; --av-dark:{dark}; color:{texto};">'
            f'{escape(_iniciales(nombre))}</span>')


def _mejor_peor(cartera: Cartera):
    """(mejor, peor) como (PosicionCartera, retorno_pct) por rendimiento
    sobre costo -- no por monto, para no premiar siempre a la posicion mas
    grande. None si no hay al menos dos posiciones con costo conocido."""
    candidatos = []
    for p in cartera.posiciones:
        costo_total = (p.costo_promedio or 0) * (p.titulos or 0)
        if costo_total and p.plusvalia_minusvalia is not None:
            candidatos.append((p, p.plusvalia_minusvalia / costo_total))
    if len(candidatos) < 2:
        return None, None
    candidatos.sort(key=lambda t: t[1])
    return candidatos[-1], candidatos[0]


def _donut_composicion(cartera: Cartera) -> str:
    invertido = cartera.valor_posiciones
    efectivo_positivo = max(cartera.valor_efectivo, 0.0)
    total = invertido + efectivo_positivo
    if total <= 0:
        return '<p class="donut-vacio">Sin datos suficientes para la composición.</p>'

    pct_inv = invertido / total
    ang = pct_inv * 360
    c1_l, c2_l = CATEGORICO_CLARO[0], GRIS_NEUTRO_CLARO
    c1_d, c2_d = CATEGORICO_OSCURO[0], GRIS_NEUTRO_OSCURO
    grad_light = f"conic-gradient({c1_l} 0deg {ang:.1f}deg, {c2_l} {ang:.1f}deg 360deg)"
    grad_dark = f"conic-gradient({c1_d} 0deg {ang:.1f}deg, {c2_d} {ang:.1f}deg 360deg)"

    nota_efectivo_negativo = ""
    if cartera.valor_efectivo < 0:
        nota_efectivo_negativo = (f'<p class="donut-nota">Incluye {_money(cartera.valor_efectivo)} '
                                   f'en cuentas de efectivo en uso (crédito/margen), no mostrado en el anillo.</p>')

    return f"""
    <div class="donut" style="--grad-light:{grad_light}; --grad-dark:{grad_dark};">
      <div class="donut-centro">
        <div class="donut-centro-valor">{_pct(pct_inv, 0)}</div>
        <div class="donut-centro-label">invertido</div>
      </div>
    </div>
    <div class="donut-legend">
      <div class="legend-row"><span class="dot" style="--dot-light:{c1_l}; --dot-dark:{c1_d};"></span>
        Invertido <span class="legend-value">{_money(invertido)}</span></div>
      <div class="legend-row"><span class="dot" style="--dot-light:{c2_l}; --dot-dark:{c2_d};"></span>
        Efectivo <span class="legend-value">{_money(efectivo_positivo)}</span></div>
    </div>
    {nota_efectivo_negativo}"""


def _barras_distribucion(cartera: Cartera, colores: dict) -> str:
    items = [(p.nombre_gbm, p.valor_mercado or 0.0) for p in cartera.posiciones]
    if cartera.valor_efectivo:
        items.append(("Efectivo", cartera.valor_efectivo))
    items = [it for it in items if it[1] > 0]
    items.sort(key=lambda it: it[1], reverse=True)

    if len(items) > MAX_CATEGORIAS + 1:
        principales = items[:MAX_CATEGORIAS]
        resto = sum(v for _, v in items[MAX_CATEGORIAS:])
        items = principales + [("Otros", resto)]

    valor_total = cartera.valor_total or 1.0
    maximo = max((v for _, v in items), default=1.0) or 1.0

    filas = []
    for nombre, valor in items:
        color_light, color_dark, _texto = colores.get(nombre, (GRIS_NEUTRO_CLARO, GRIS_NEUTRO_OSCURO, TINTA))
        ancho = _clamp01(valor / maximo) * 100
        pct_cartera = valor / valor_total
        filas.append(f"""
        <div class="bar-row">
          <div class="bar-label">{_avatar(nombre, colores)}<span class="label-text">{escape(nombre)}</span></div>
          <div class="bar-track">
            <div class="bar-fill" style="width:{ancho:.2f}%; --fill-light:{color_light}; --fill-dark:{color_dark};"></div>
          </div>
          <div class="bar-value">{_money(valor)} <span class="bar-pct">({_pct(pct_cartera, 1)})</span></div>
        </div>""")
    return "".join(filas)


def _barras_pm(cartera: Cartera, colores: dict) -> str:
    posiciones = [p for p in cartera.posiciones if p.plusvalia_minusvalia is not None]
    posiciones.sort(key=lambda p: abs(p.plusvalia_minusvalia or 0), reverse=True)
    maximo = max((abs(p.plusvalia_minusvalia or 0) for p in posiciones), default=1.0) or 1.0

    filas = []
    for p in posiciones:
        pm = p.plusvalia_minusvalia or 0.0
        ancho = _clamp01(abs(pm) / maximo) * 50  # cada lado ocupa hasta el 50% del track
        lado = "pos" if pm >= 0 else "neg"
        filas.append(f"""
        <div class="pm-row">
          <div class="pm-label">{_avatar(p.nombre_gbm, colores)}<span class="label-text">{escape(p.nombre_gbm)}</span></div>
          <div class="pm-track">
            <div class="pm-mid"></div>
            <div class="pm-fill pm-{lado}" style="width:{ancho:.2f}%;"></div>
          </div>
          <div class="pm-value pm-text-{lado}">{_money(pm)}</div>
        </div>""")
    return "".join(filas)


def _tabla_posiciones(cartera: Cartera, colores: dict) -> str:
    filas = []
    for p in sorted(cartera.posiciones, key=lambda p: p.valor_mercado or 0, reverse=True):
        pm = p.plusvalia_minusvalia
        clase_pm = "cell-good" if (pm or 0) >= 0 else "cell-bad"
        filas.append(f"""
        <tr>
          <td class="cell-nombre">{_avatar(p.nombre_gbm, colores)}<span class="label-text">{escape(p.nombre_gbm)}</span></td>
          <td class="num">{p.titulos:g}</td>
          <td class="num">{_money(p.costo_promedio)}</td>
          <td class="num">{_money(p.precio_mercado)}</td>
          <td class="num">{_money(p.valor_mercado)}</td>
          <td class="num {clase_pm}">{_money(pm)}</td>
          <td class="num">{_pct(p.pct_cartera, 2)}</td>
        </tr>""")
    return "".join(filas)


def _tabla_efectivo(cartera: Cartera) -> str:
    filas = []
    for e in cartera.efectivo:
        filas.append(f"""
        <tr>
          <td>{escape(e.cuenta)}</td>
          <td class="num">{_money(e.valor_mercado)}</td>
          <td class="num">{_pct(e.pct_cartera, 2)}</td>
        </tr>""")
    valor_total = cartera.valor_total
    pct_total_efectivo = (cartera.valor_efectivo / valor_total) if valor_total else None
    filas.append(f"""
        <tr class="fila-total">
          <td>Total efectivo</td>
          <td class="num">{_money(cartera.valor_efectivo)}</td>
          <td class="num">{_pct(pct_total_efectivo, 2)}</td>
        </tr>""")
    return "".join(filas)


def _tile_posicion(icono: str, etiqueta: str, par) -> str:
    if par is None or par[0] is None:
        return ""
    p: PosicionCartera = par[0]
    retorno = par[1]
    clase = "good" if retorno >= 0 else "bad"
    return f"""
    <div class="tile">
      <div class="tile-icon">{icono}</div>
      <div class="tile-body">
        <div class="tile-label">{escape(etiqueta)}</div>
        <div class="tile-name">{escape(p.nombre_gbm)}</div>
        <div class="tile-sub {clase}">{_money(p.plusvalia_minusvalia)} ({_pct(retorno, 1)})</div>
      </div>
    </div>"""


def generar(cartera: Cartera, ruta_salida: Optional[Path] = None) -> Path:
    """Escribe el dashboard .html y devuelve la ruta."""
    if ruta_salida is None:
        sello = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        base = cartera.ruta.parent if cartera.ruta else Path.cwd()
        ruta_salida = base / f"dashboard_cartera_{sello}.html"
    ruta_salida = Path(ruta_salida)

    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    valor_total = cartera.valor_total
    plusvalia_total = cartera.plusvalia_total
    pct_efectivo = (cartera.valor_efectivo / valor_total) if valor_total else None
    n_posiciones = len(cartera.posiciones)
    pm_es_positiva = plusvalia_total >= 0
    fuente = cartera.ruta.name if cartera.ruta else "—"
    colores = _asignar_colores(cartera)
    mejor, peor = _mejor_peor(cartera)

    narrativa = (f"Tu cartera vale {_money(valor_total)} y sube {_money(abs(plusvalia_total))} "
                 f"desde el costo promedio de tus posiciones."
                 if pm_es_positiva else
                 f"Tu cartera vale {_money(valor_total)} y baja {_money(abs(plusvalia_total))} "
                 f"desde el costo promedio de tus posiciones.")

    tiles_posicion = _tile_posicion("🏆", "Mejor posición", mejor) + _tile_posicion("📉", "Peor posición", peor)

    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mi cartera — GBM</title>
<style>
  :root {{
    color-scheme: light;
    --surface-1: #ffffff;
    --surface-2: #f6f8fa;
    --page: #eef0f3;
    --text-primary: #1f2328;
    --text-secondary: #57606a;
    --text-muted: #8c94a0;
    --border: #e4e7eb;
    --good: #1a7f37;
    --bad: #b3261e;
    --shadow: 0 1px 2px rgba(16,24,40,0.04), 0 2px 6px rgba(16,24,40,0.05);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      color-scheme: dark;
      --surface-1: #1c1f26;
      --surface-2: #22262e;
      --page: #14161a;
      --text-primary: #f2f3f5;
      --text-secondary: #b7bec9;
      --text-muted: #7d8590;
      --border: #2c3038;
      --good: #3fb950;
      --bad: #f2555a;
      --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 2px 6px rgba(0,0,0,0.25);
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --surface-1: #1c1f26;
    --surface-2: #22262e;
    --page: #14161a;
    --text-primary: #f2f3f5;
    --text-secondary: #b7bec9;
    --text-muted: #7d8590;
    --border: #2c3038;
    --good: #3fb950;
    --bad: #f2555a;
    --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 2px 6px rgba(0,0,0,0.25);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--page);
    color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 32px 24px 64px;
  }}
  .wrap {{ max-width: 1080px; margin: 0 auto; }}
  header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 24px;
  }}
  .brand {{ display: flex; align-items: center; gap: 10px; }}
  .brand-mark {{
    width: 34px; height: 34px; border-radius: 9px;
    background: linear-gradient(135deg, #2a78d6, #1baf7a);
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; flex-shrink: 0;
  }}
  h1 {{ font-size: 20px; margin: 0 0 2px; }}
  .subtitulo {{ color: var(--text-secondary); font-size: 12.5px; margin: 0; }}
  .theme-toggle {{
    border: 1px solid var(--border);
    background: var(--surface-1);
    color: var(--text-secondary);
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 12px;
    cursor: pointer;
    flex-shrink: 0;
  }}
  .theme-toggle:hover {{ color: var(--text-primary); }}

  .hero-grid {{
    display: flex;
    gap: 16px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }}
  .hero-card {{
    flex: 2 1 320px;
    background: var(--surface-1);
    border: 1px solid var(--border);
    box-shadow: var(--shadow);
    border-radius: 14px;
    padding: 22px 24px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 8px;
  }}
  .hero-label {{ font-size: 12.5px; color: var(--text-secondary); }}
  .hero-value {{ font-size: 40px; font-weight: 650; line-height: 1.1; }}
  .hero-narrativa {{ font-size: 13px; color: var(--text-secondary); max-width: 46ch; }}
  .chip-delta {{
    display: inline-flex; align-items: center; gap: 4px;
    padding: 4px 10px; border-radius: 999px;
    font-size: 12.5px; font-weight: 600; width: fit-content;
  }}
  .chip-delta.good {{ background: rgba(26,127,55,0.12); color: var(--good); }}
  .chip-delta.bad {{ background: rgba(179,38,30,0.12); color: var(--bad); }}

  .donut-card {{
    flex: 1 1 220px;
    background: var(--surface-1);
    border: 1px solid var(--border);
    box-shadow: var(--shadow);
    border-radius: 14px;
    padding: 20px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 14px;
  }}
  .donut-card h2 {{ align-self: flex-start; font-size: 13px; margin: 0; color: var(--text-primary); }}
  .donut {{
    width: 128px; height: 128px; border-radius: 50%;
    background: var(--grad-light);
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) .donut {{ background: var(--grad-dark); }}
  }}
  :root[data-theme="dark"] .donut {{ background: var(--grad-dark); }}
  .donut-centro {{
    width: 84px; height: 84px; border-radius: 50%;
    background: var(--surface-1);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
  }}
  .donut-centro-valor {{ font-size: 18px; font-weight: 700; }}
  .donut-centro-label {{ font-size: 10.5px; color: var(--text-muted); }}
  .donut-legend {{ width: 100%; font-size: 12.5px; }}
  .legend-row {{ display: flex; align-items: center; gap: 8px; padding: 3px 0; color: var(--text-secondary); }}
  .legend-value {{ margin-left: auto; font-variant-numeric: tabular-nums; color: var(--text-primary); }}
  .dot {{
    width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0;
    background: var(--dot-light);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) .dot {{ background: var(--dot-dark); }}
  }}
  :root[data-theme="dark"] .dot {{ background: var(--dot-dark); }}
  .donut-nota, .donut-vacio {{ font-size: 11px; color: var(--text-muted); margin: 0; text-align: center; }}

  .kpis {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
    margin-bottom: 20px;
  }}
  .tile {{
    background: var(--surface-1);
    border: 1px solid var(--border);
    box-shadow: var(--shadow);
    border-radius: 12px;
    padding: 14px 16px;
    display: flex;
    gap: 12px;
    align-items: flex-start;
  }}
  .tile-icon {{
    width: 34px; height: 34px; border-radius: 9px;
    background: var(--surface-2);
    display: flex; align-items: center; justify-content: center;
    font-size: 15px; flex-shrink: 0;
  }}
  .tile-label {{ font-size: 11.5px; color: var(--text-secondary); margin-bottom: 3px; }}
  .tile-value {{ font-size: 21px; font-weight: 600; }}
  .tile-value.good {{ color: var(--good); }}
  .tile-value.bad {{ color: var(--bad); }}
  .tile-name {{ font-size: 14.5px; font-weight: 700; }}
  .tile-sub {{ font-size: 12px; font-variant-numeric: tabular-nums; }}
  .tile-sub.good {{ color: var(--good); }}
  .tile-sub.bad {{ color: var(--bad); }}

  .card {{
    background: var(--surface-1);
    border: 1px solid var(--border);
    box-shadow: var(--shadow);
    border-radius: 14px;
    padding: 20px 22px;
    margin-bottom: 20px;
  }}
  .card h2 {{ font-size: 14px; margin: 0 0 16px; color: var(--text-primary); }}

  .bar-row, .pm-row {{
    display: grid;
    grid-template-columns: 150px 1fr 150px;
    align-items: center;
    gap: 12px;
    padding: 6px 0;
  }}
  .bar-label, .pm-label, .cell-nombre {{
    display: flex; align-items: center; gap: 8px;
  }}
  .label-text {{
    font-size: 12.5px;
    color: var(--text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  .cell-nombre .label-text {{ font-size: 13px; font-weight: 600; color: var(--text-primary); }}
  .avatar {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 22px; height: 22px; border-radius: 50%;
    font-size: 9px; font-weight: 700; flex-shrink: 0;
    background: var(--av-light);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) .avatar {{ background: var(--av-dark); }}
  }}
  :root[data-theme="dark"] .avatar {{ background: var(--av-dark); }}

  .bar-track {{
    background: var(--surface-2);
    border-radius: 4px;
    height: 16px;
    overflow: hidden;
  }}
  .bar-fill {{
    height: 100%;
    border-radius: 4px;
    background: var(--fill-light);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) .bar-fill {{ background: var(--fill-dark); }}
  }}
  :root[data-theme="dark"] .bar-fill {{ background: var(--fill-dark); }}
  .bar-value {{ font-size: 12.5px; text-align: right; font-variant-numeric: tabular-nums; }}
  .bar-pct {{ color: var(--text-muted); }}

  .pm-track {{
    position: relative;
    height: 16px;
    background: var(--surface-2);
    border-radius: 4px;
    overflow: hidden;
  }}
  .pm-mid {{
    position: absolute;
    left: 50%;
    top: 0;
    bottom: 0;
    width: 1px;
    background: var(--border);
  }}
  .pm-fill {{ position: absolute; top: 0; bottom: 0; border-radius: 4px; }}
  .pm-fill.pm-pos {{ left: 50%; background: var(--good); }}
  .pm-fill.pm-neg {{ right: 50%; background: var(--bad); }}
  .pm-value {{ font-size: 12.5px; text-align: right; font-variant-numeric: tabular-nums; }}
  .pm-text-pos {{ color: var(--good); }}
  .pm-text-neg {{ color: var(--bad); }}

  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; }}
  th {{ color: var(--text-secondary); font-weight: 600; font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.02em; }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .cell-good {{ color: var(--good); }}
  .cell-bad {{ color: var(--bad); }}
  .fila-total td {{ font-weight: 600; border-bottom: none; }}

  footer {{ color: var(--text-muted); font-size: 11.5px; margin-top: 24px; line-height: 1.6; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">
      <div class="brand-mark">💼</div>
      <div>
        <h1>Mi cartera — GBM</h1>
        <p class="subtitulo">Generado el {ahora} · Fuente: {escape(fuente)}</p>
      </div>
    </div>
    <button class="theme-toggle" onclick="toggleTheme()">Cambiar tema</button>
  </header>

  <div class="hero-grid">
    <div class="hero-card">
      <div class="hero-label">Valor total</div>
      <div class="hero-value">{_money(valor_total)}</div>
      <div class="chip-delta {'good' if pm_es_positiva else 'bad'}">
        {'▲' if pm_es_positiva else '▼'} {_money(plusvalia_total)}
      </div>
      <div class="hero-narrativa">{narrativa}</div>
    </div>
    <div class="donut-card">
      <h2>Composición</h2>
      {_donut_composicion(cartera)}
    </div>
  </div>

  <div class="kpis">
    <div class="tile">
      <div class="tile-icon">💵</div>
      <div class="tile-body">
        <div class="tile-label">Efectivo</div>
        <div class="tile-value">{_pct(pct_efectivo, 1)}</div>
      </div>
    </div>
    <div class="tile">
      <div class="tile-icon">📊</div>
      <div class="tile-body">
        <div class="tile-label">Posiciones</div>
        <div class="tile-value">{n_posiciones}</div>
      </div>
    </div>
    {tiles_posicion}
  </div>

  <div class="card">
    <h2>Distribución de la cartera</h2>
    {_barras_distribucion(cartera, colores)}
  </div>

  <div class="card">
    <h2>Plusvalía / minusvalía por posición</h2>
    {_barras_pm(cartera, colores)}
  </div>

  <div class="card">
    <h2>Detalle de posiciones</h2>
    <table>
      <thead>
        <tr>
          <th>Emisora</th>
          <th class="num">Títulos</th>
          <th class="num">Costo prom</th>
          <th class="num">Precio mdo</th>
          <th class="num">Valor mdo</th>
          <th class="num">P/M</th>
          <th class="num">% Cartera</th>
        </tr>
      </thead>
      <tbody>
        {_tabla_posiciones(cartera, colores)}
      </tbody>
    </table>
  </div>

  <div class="card">
    <h2>Efectivo y liquidez</h2>
    <table>
      <thead>
        <tr><th>Cuenta</th><th class="num">Valor</th><th class="num">% Cartera</th></tr>
      </thead>
      <tbody>
        {_tabla_efectivo(cartera)}
      </tbody>
    </table>
  </div>

  <footer>
    "P/M" es la plusvalía o minusvalía que reporta GBM para la posición completa (precio de mercado menos costo
    promedio, por el número de títulos). No incluye distribuciones ya cobradas. "Mejor/peor posición" se calcula
    como P/M sobre el costo de esa posición, no sobre su tamaño en la cartera.<br>
    Este tablero es un resumen de tu posición actual, no una recomendación de compra o venta.
  </footer>
</div>
<script>
  function toggleTheme() {{
    const root = document.documentElement;
    const actual = root.getAttribute('data-theme');
    root.setAttribute('data-theme', actual === 'dark' ? 'light' : 'dark');
  }}
</script>
</body>
</html>
"""
    ruta_salida.write_text(html, encoding="utf-8")
    return ruta_salida
