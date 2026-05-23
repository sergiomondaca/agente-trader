"""
Genera reporte_portfolio.html con diseño tipo Power BI.
Obtiene precios actuales desde TradingView (tradingview-ta).

Uso:
    python reporte.py           # genera el HTML
    python reporte.py --open    # genera y abre en el navegador
"""

import json
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from tradingview_ta import TA_Handler, Interval

PORTFOLIO_PATH = Path(__file__).parent / "portfolio.json"
OUTPUT_PATH    = Path(__file__).parent / "reporte_portfolio.html"


# ── Obtener precio actual desde TradingView ──────────────────
def get_price(symbol: str, exchange: str, screener: str = "america") -> float | None:
    try:
        h = TA_Handler(
            symbol=symbol,
            exchange=exchange,
            screener=screener,
            interval=Interval.INTERVAL_1_DAY,
        )
        return h.get_analysis().indicators.get("close")
    except Exception:
        return None


# ── Calcular datos del portfolio ─────────────────────────────
def build_rows(positions: list) -> list:
    rows = []
    for p in positions:
        symbol   = p.get("symbol", "")
        exchange = p.get("exchange", "NYSE")
        screener = p.get("screener", "america")
        nombre   = p.get("nombre", symbol)
        cantidad = p.get("cantidad", 0)
        entrada  = p.get("precio_promedio", 0)
        fecha    = p.get("fecha_entrada", "—")

        print(f"  Consultando {symbol}...", end=" ", flush=True)
        precio_actual = get_price(symbol, exchange, screener)
        print(f"${precio_actual:.2f}" if precio_actual else "N/A")

        if precio_actual and entrada and cantidad:
            invertido   = round(entrada * cantidad, 2)
            valor_actual = round(precio_actual * cantidad, 2)
            pnl_usd     = round(valor_actual - invertido, 2)
            pnl_pct     = round((precio_actual - entrada) / entrada * 100, 2)
        else:
            invertido    = round(entrada * cantidad, 2) if entrada and cantidad else 0
            valor_actual = None
            pnl_usd      = None
            pnl_pct      = None

        rows.append({
            "symbol":        symbol,
            "nombre":        nombre,
            "cantidad":      cantidad,
            "entrada":       entrada,
            "precio_actual": precio_actual,
            "invertido":     invertido,
            "valor_actual":  valor_actual,
            "pnl_usd":       pnl_usd,
            "pnl_pct":       pnl_pct,
            "fecha":         fecha,
        })

    return rows


# ── HTML ─────────────────────────────────────────────────────
def fmt_usd(v):
    if v is None: return "—"
    sign = "+" if v > 0 else ""
    return f"{sign}${v:,.2f}"

def fmt_pct(v):
    if v is None: return "—"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.2f}%"

def pnl_class(v):
    if v is None: return "neutral"
    return "positive" if v >= 0 else "negative"

def generate_html(rows: list) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    # KPIs globales (solo filas con datos completos)
    valid = [r for r in rows if r["valor_actual"] is not None]
    total_invertido  = sum(r["invertido"]    for r in valid)
    total_valor      = sum(r["valor_actual"] for r in valid)
    total_pnl_usd    = total_valor - total_invertido
    total_pnl_pct    = (total_pnl_usd / total_invertido * 100) if total_invertido else 0
    en_ganancia      = sum(1 for r in valid if (r["pnl_pct"] or 0) >= 0)
    en_perdida       = len(valid) - en_ganancia

    kpi_class = "kpi-positive" if total_pnl_usd >= 0 else "kpi-negative"
    arrow     = "▲" if total_pnl_usd >= 0 else "▼"

    # Tabla rows HTML
    rows_html = ""
    for r in sorted(rows, key=lambda x: (x["pnl_pct"] or -9999), reverse=True):
        pc = pnl_class(r["pnl_pct"])
        pnl_badge = (
            f'<span class="badge {pc}">{fmt_pct(r["pnl_pct"])}</span>'
        )
        precio_str  = f"${r['precio_actual']:,.2f}" if r["precio_actual"] else '<span class="muted">N/A</span>'
        valor_str   = f"${r['valor_actual']:,.2f}" if r["valor_actual"] else '<span class="muted">—</span>'
        pnl_usd_str = f'<span class="{pc}">{fmt_usd(r["pnl_usd"])}</span>' if r["pnl_usd"] is not None else '<span class="muted">—</span>'

        rows_html += f"""
        <tr>
          <td><span class="symbol-chip">{r['symbol']}</span></td>
          <td class="nombre-col">{r['nombre']}</td>
          <td class="num">{r['cantidad']:g}</td>
          <td class="num">${r['entrada']:,.2f}</td>
          <td class="num">{precio_str}</td>
          <td class="num">${r['invertido']:,.2f}</td>
          <td class="num">{valor_str}</td>
          <td class="num">{pnl_usd_str}</td>
          <td class="num">{pnl_badge}</td>
          <td class="fecha">{r['fecha']}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Portfolio Report</title>
<style>
  /* ── Variables ── */
  :root {{
    --bg:        #0E1117;
    --bg2:       #161B27;
    --bg3:       #1E2535;
    --border:    #2A3347;
    --text:      #E2E8F0;
    --muted:     #64748B;
    --primary:   #4A9EFF;
    --positive:  #22C55E;
    --negative:  #EF4444;
    --warning:   #F59E0B;
    --font:      'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: var(--font);
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 32px 40px;
    -webkit-font-smoothing: antialiased;
  }}

  /* ── Header ── */
  .report-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-bottom: 36px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
  }}

  .report-title {{
    font-size: 1.6rem;
    font-weight: 700;
    color: var(--text);
    letter-spacing: -0.02em;
  }}

  .report-title span {{
    color: var(--primary);
  }}

  .report-meta {{
    font-size: 0.82rem;
    color: var(--muted);
    text-align: right;
    line-height: 1.8;
  }}

  /* ── KPI Cards ── */
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 16px;
    margin-bottom: 32px;
  }}

  .kpi-card {{
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 22px;
    position: relative;
    overflow: hidden;
  }}

  .kpi-card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: var(--primary);
    border-radius: 12px 12px 0 0;
  }}

  .kpi-card.kpi-positive::before {{ background: var(--positive); }}
  .kpi-card.kpi-negative::before {{ background: var(--negative); }}
  .kpi-card.kpi-warning::before  {{ background: var(--warning); }}

  .kpi-label {{
    font-size: 0.75rem;
    color: var(--muted);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-bottom: 10px;
  }}

  .kpi-value {{
    font-size: 1.55rem;
    font-weight: 800;
    color: var(--text);
    letter-spacing: -0.02em;
    line-height: 1;
  }}

  .kpi-value.kpi-positive {{ color: var(--positive); }}
  .kpi-value.kpi-negative {{ color: var(--negative); }}

  .kpi-sub {{
    font-size: 0.78rem;
    color: var(--muted);
    margin-top: 6px;
  }}

  /* ── Table wrapper ── */
  .table-wrap {{
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 14px;
    overflow: hidden;
  }}

  .table-toolbar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 18px 24px;
    border-bottom: 1px solid var(--border);
  }}

  .table-toolbar-title {{
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--text);
  }}

  .table-toolbar-sub {{
    font-size: 0.8rem;
    color: var(--muted);
    margin-top: 2px;
  }}

  .legend {{
    display: flex;
    gap: 16px;
    font-size: 0.78rem;
    color: var(--muted);
  }}

  .legend-dot {{
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-right: 5px;
  }}

  /* ── Table ── */
  .portfolio-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
  }}

  .portfolio-table thead th {{
    background: var(--bg3);
    color: var(--muted);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    padding: 14px 18px;
    text-align: left;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }}

  .portfolio-table thead th.num {{ text-align: right; }}

  .portfolio-table tbody tr {{
    border-bottom: 1px solid var(--border);
    transition: background 0.15s;
  }}

  .portfolio-table tbody tr:last-child {{ border-bottom: none; }}

  .portfolio-table tbody tr:hover {{
    background: rgba(74, 158, 255, 0.04);
  }}

  .portfolio-table td {{
    padding: 14px 18px;
    color: var(--text);
    vertical-align: middle;
  }}

  .portfolio-table td.num   {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .portfolio-table td.fecha {{ color: var(--muted); font-size: 0.8rem; }}

  /* ── Symbol chip ── */
  .symbol-chip {{
    display: inline-block;
    background: rgba(74,158,255,0.12);
    color: var(--primary);
    font-weight: 700;
    font-size: 0.8rem;
    padding: 3px 10px;
    border-radius: 6px;
    letter-spacing: 0.04em;
  }}

  /* ── Nombre ── */
  .nombre-col {{ color: #94A3B8; font-size: 0.83rem; max-width: 200px; }}

  /* ── Badge P&L ── */
  .badge {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: 99px;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.03em;
  }}

  .badge.positive {{ background: rgba(34,197,94,0.15); color: var(--positive); }}
  .badge.negative {{ background: rgba(239,68,68,0.15);  color: var(--negative); }}
  .badge.neutral  {{ background: rgba(100,116,139,0.15); color: var(--muted); }}

  /* ── P&L inline color ── */
  .positive {{ color: var(--positive); font-weight: 600; }}
  .negative {{ color: var(--negative); font-weight: 600; }}
  .muted    {{ color: var(--muted); }}

  /* ── Footer ── */
  .report-footer {{
    margin-top: 24px;
    text-align: center;
    font-size: 0.75rem;
    color: #374151;
  }}

  /* ── Responsive ── */
  @media (max-width: 1200px) {{ body {{ padding: 20px; }} }}
  @media (max-width: 900px) {{
    .kpi-grid {{ grid-template-columns: repeat(3, 1fr); }}
    .nombre-col {{ display: none; }}
  }}
  @media (max-width: 600px) {{
    .kpi-grid {{ grid-template-columns: 1fr 1fr; }}
  }}

  /* ── Print ── */
  @media print {{
    body {{ background: #fff; color: #000; padding: 16px; }}
    .kpi-card, .table-wrap {{ border: 1px solid #ddd; }}
    .portfolio-table tbody tr:hover {{ background: transparent; }}
  }}
</style>
</head>
<body>

<!-- Header -->
<div class="report-header">
  <div>
    <div class="report-title">📊 Portfolio <span>Report</span></div>
    <div style="color:var(--muted); font-size:0.85rem; margin-top:4px;">Resumen de posiciones activas</div>
  </div>
  <div class="report-meta">
    <div>Actualizado: <strong>{now}</strong></div>
    <div>Posiciones: <strong>{len(rows)}</strong> activos</div>
    <div>Precios: TradingView (tiempo real)</div>
  </div>
</div>

<!-- KPI Cards -->
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">Total invertido</div>
    <div class="kpi-value">${total_invertido:,.0f}</div>
    <div class="kpi-sub">Capital desplegado</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Valor actual</div>
    <div class="kpi-value">${total_valor:,.0f}</div>
    <div class="kpi-sub">{len(valid)} posiciones con precio</div>
  </div>
  <div class="kpi-card {kpi_class}">
    <div class="kpi-label">P&amp;L Total (USD)</div>
    <div class="kpi-value {kpi_class}">{arrow} ${abs(total_pnl_usd):,.0f}</div>
    <div class="kpi-sub">{'Ganancia' if total_pnl_usd >= 0 else 'Pérdida'} no realizada</div>
  </div>
  <div class="kpi-card {kpi_class}">
    <div class="kpi-label">Retorno Total</div>
    <div class="kpi-value {kpi_class}">{arrow} {abs(total_pnl_pct):.1f}%</div>
    <div class="kpi-sub">Sobre capital invertido</div>
  </div>
  <div class="kpi-card kpi-warning">
    <div class="kpi-label">Posiciones</div>
    <div class="kpi-value">{len(valid)}</div>
    <div class="kpi-sub" style="color:var(--positive)">▲ {en_ganancia} ganadoras &nbsp;
      <span style="color:var(--negative)">▼ {en_perdida} perdedoras</span>
    </div>
  </div>
</div>

<!-- Tabla -->
<div class="table-wrap">
  <div class="table-toolbar">
    <div>
      <div class="table-toolbar-title">Posiciones activas</div>
      <div class="table-toolbar-sub">Ordenadas por P&amp;L % descendente</div>
    </div>
    <div class="legend">
      <span><span class="legend-dot" style="background:var(--positive)"></span>Ganancia</span>
      <span><span class="legend-dot" style="background:var(--negative)"></span>Pérdida</span>
    </div>
  </div>

  <table class="portfolio-table">
    <thead>
      <tr>
        <th>Símbolo</th>
        <th>Nombre</th>
        <th class="num">Cantidad</th>
        <th class="num">Precio entrada</th>
        <th class="num">Precio actual</th>
        <th class="num">Invertido</th>
        <th class="num">Valor actual</th>
        <th class="num">P&amp;L USD</th>
        <th class="num">P&amp;L %</th>
        <th>Entrada</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</div>

<div class="report-footer">
  Generado con Agente Trader · {now} · Datos: TradingView
</div>

</body>
</html>"""


# ── Main ─────────────────────────────────────────────────────
def main():
    pf = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
    positions = [p for p in pf.get("positions", []) if p.get("cantidad", 0) > 0]

    print(f"\n[*] Consultando precios para {len(positions)} posiciones...\n")
    rows = build_rows(positions)

    html = generate_html(rows)
    OUTPUT_PATH.write_text(html, encoding="utf-8")

    print(f"\n[+] Reporte generado: {OUTPUT_PATH}")

    if "--open" in sys.argv:
        webbrowser.open(OUTPUT_PATH.as_uri())
        print("[+] Abriendo en el navegador...")


if __name__ == "__main__":
    main()
