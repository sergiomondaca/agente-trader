"""
Sincroniza TradingView con portfolio.json leyendo dos secciones:
  - POSICIONES -> portfolio["positions"]
  - WATCHLIST  -> portfolio["watchlist"]

Requiere Brave abierto con: --remote-debugging-port=9222

Uso:
    python tv_sync.py           # solo compara ambas secciones
    python tv_sync.py --update  # sincroniza portfolio.json con TradingView
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

import requests
import websockets

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CDP_URL       = "http://localhost:9222"
PORTFOLIO_PATH = Path(__file__).parent / "portfolio.json"

# Nombres exactos de los grupos en TradingView (sensible a mayúsculas)
TV_SECTIONS = ["POSICIONES", "WATCHLIST"]

_SECTIONS_JSON = json.dumps(TV_SECTIONS)
JS_READ_SECTIONS = """
(function() {
    const SECTIONS = """ + _SECTIONS_JSON + """;

    const text  = document.body.innerText;
    const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);

    // Detectar si una linea es encabezado de seccion conocida o desconocida
    function isSectionHeader(line) {
        // Conocida: está en nuestra lista
        if (SECTIONS.includes(line)) return true;
        // Desconocida: >6 chars en mayusculas sin numeros ni signos
        if (/^[A-Z ]{7,}$/.test(line)) return true;
        return false;
    }

    function isSymbol(line) {
        return /^[A-Z]{2,6}$/.test(line);
    }

    function isInitial(line) {
        return /^[A-Z]$/.test(line);
    }

    function isNumber(line) {
        // Precio o porcentaje (puede tener -, +, coma, punto, %)
        return /^[−+]?[\\d,.]+[%%]?$/.test(line) || /^[−+]\\d/.test(line);
    }

    // Encontrar la ultima aparicion de cada seccion (evita duplicados de header)
    const sectionStarts = {};
    for (let j = 0; j < lines.length; j++) {
        if (SECTIONS.includes(lines[j])) {
            sectionStarts[lines[j]] = j;
        }
    }

    // Determinar donde termina cada seccion (donde empieza la siguiente)
    const sortedStarts = Object.entries(sectionStarts)
        .sort((a, b) => a[1] - b[1]);

    function extractSection(startIdx) {
        const items = [];
        let i = startIdx + 1;
        let misses = 0;

        while (i < lines.length && misses < 6) {
            const line = lines[i];

            if (isSectionHeader(line)) break;   // nueva seccion: parar
            if (isInitial(line))  { i++; misses = 0; continue; }
            if (isNumber(line))   { i++; continue; }

            if (isSymbol(line)) {
                const symbol    = line;
                const price     = parseFloat(lines[i + 1]) || null;
                const change    = lines[i + 2] || '';
                const changePct = lines[i + 3] || '';
                items.push({ symbol, price, change, changePct });
                i += 4;
                misses = 0;
                continue;
            }

            misses++;
            i++;
        }
        return items;
    }

    const result = {};
    for (const [name, idx] of Object.entries(sectionStarts)) {
        result[name] = extractSection(idx);
    }

    const missing = SECTIONS.filter(s => !(s in result));
    return { sections: result, missing };
})()
"""


async def read_tv_sections() -> dict:
    """Lee las secciones POSICIONES y WATCHLIST de TradingView vía CDP."""
    try:
        targets = requests.get(f"{CDP_URL}/json/list", timeout=3).json()
    except Exception as e:
        print(f"[!] No se puede conectar al puerto 9222: {e}")
        print("    Abre Brave con: --remote-debugging-port=9222")
        sys.exit(1)

    target = next(
        (t for t in targets if "tradingview.com/chart" in t.get("url", "")), None
    )
    if not target:
        print("[!] TradingView chart no encontrado en el puerto 9222")
        sys.exit(1)

    async with websockets.connect(target["webSocketDebuggerUrl"]) as ws:
        await ws.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": JS_READ_SECTIONS, "returnByValue": True},
        }))
        resp = json.loads(await ws.recv())

    value = resp.get("result", {}).get("result", {}).get("value", {})

    if "missing" in value and value["missing"]:
        print(f"[!] Secciones no encontradas en TradingView: {', '.join(value['missing'])}")
        print("    Verifica que los grupos se llamen exactamente: " + ", ".join(TV_SECTIONS))

    return value.get("sections", {})


def load_portfolio() -> dict:
    try:
        return json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[!] portfolio.json no encontrado en {PORTFOLIO_PATH}")
        sys.exit(1)


def report_positions(tv: list[dict], portfolio: dict, update: bool) -> None:
    """Compara sección POSICIONES de TV con portfolio['positions']."""
    pf_map = {p["symbol"]: p for p in portfolio.get("positions", [])}
    tv_map  = {p["symbol"]: p for p in tv}

    only_tv = set(tv_map) - set(pf_map)
    only_pf = set(pf_map) - set(tv_map)
    in_both = set(tv_map) & set(pf_map)

    W = 68
    print(f"\n{'='*W}")
    print(f"  [POSICIONES]  TradingView <-> portfolio.json")
    print(f"{'='*W}")
    print(f"\n  {'SIMBOLO':<10} {'PRECIO':>10} {'CAMBIO%':>9}  {'ENTRADA':>10}  {'P&L':>8}  ESTADO")
    print(f"  {'-'*W}")

    for sym in sorted(tv_map):
        pos   = tv_map[sym]
        price = pos["price"]
        chg   = pos["changePct"]
        price_str = f"${price:>9,.2f}" if price else f"{'N/A':>10}"

        if sym in pf_map:
            entry = pf_map[sym]["precio_promedio"]
            pnl   = (price - entry) / entry * 100 if price else 0
            status = "OK"
            print(f"  {sym:<10} {price_str} {chg:>9}  ${entry:>9,.2f}  {pnl:>+7.1f}%  {status}")
        else:
            print(f"  {sym:<10} {price_str} {chg:>9}  {'---':>10}  {'---':>8}  (!) falta en portfolio.json")

    if only_pf:
        print(f"\n  En portfolio.json pero NO en POSICIONES de TradingView:")
        for sym in sorted(only_pf):
            p = pf_map[sym]
            print(f"    * {sym:<8}  entrada ${p['precio_promedio']:.2f} x {p['cantidad']} unid.")

    print(f"\n  TV: {len(tv_map)} | portfolio.json: {len(pf_map)} | Coinciden: {len(in_both)}")

    if update and only_tv:
        _sync_positions(only_tv, tv_map, portfolio)


def report_watchlist(tv: list[dict], portfolio: dict, update: bool) -> None:
    """Compara sección WATCHLIST de TV con portfolio['watchlist']."""
    wl_map = {w["symbol"]: w for w in portfolio.get("watchlist", [])}
    tv_map  = {p["symbol"]: p for p in tv}

    only_tv = set(tv_map) - set(wl_map)
    only_pf = set(wl_map) - set(tv_map)
    in_both = set(tv_map) & set(wl_map)

    W = 68
    print(f"\n{'='*W}")
    print(f"  [WATCHLIST]  TradingView <-> portfolio.json")
    print(f"{'='*W}")
    print(f"\n  {'SIMBOLO':<10} {'PRECIO':>10} {'CAMBIO%':>9}  ESTADO")
    print(f"  {'-'*W}")

    for sym in sorted(tv_map):
        pos      = tv_map[sym]
        price_str = f"${pos['price']:>9,.2f}" if pos["price"] else f"{'N/A':>10}"
        status   = "OK" if sym in wl_map else "(!) falta en portfolio.json"
        print(f"  {sym:<10} {price_str} {pos['changePct']:>9}  {status}")

    if only_pf:
        print(f"\n  En portfolio.json watchlist pero NO en TradingView WATCHLIST:")
        for sym in sorted(only_pf):
            print(f"    * {sym}")

    print(f"\n  TV: {len(tv_map)} | portfolio.json: {len(wl_map)} | Coinciden: {len(in_both)}")

    if update and only_tv:
        _sync_watchlist(only_tv, tv_map, portfolio)


def _sync_positions(symbols: set, tv_map: dict, portfolio: dict) -> None:
    added = []
    for sym in sorted(symbols):
        price = tv_map[sym]["price"]
        portfolio["positions"].append({
            "symbol":          sym,
            "exchange":        "NYSE",
            "screener":        "america",
            "nombre":          sym,
            "cantidad":        0,
            "precio_promedio": price or 0,
            "fecha_entrada":   datetime.now().strftime("%Y-%m-%d"),
            "notas":           "Importado desde TradingView — completar cantidad y precio",
        })
        added.append(sym)

    _save(portfolio)
    print(f"\n  [+] Agregados a positions: {', '.join(added)}")
    print("      Completa 'cantidad' y 'precio_promedio' en portfolio.json")


def _sync_watchlist(symbols: set, tv_map: dict, portfolio: dict) -> None:
    added = []
    existing = {w["symbol"] for w in portfolio.get("watchlist", [])}
    for sym in sorted(symbols):
        if sym not in existing:
            portfolio.setdefault("watchlist", []).append({
                "symbol":   sym,
                "exchange": "NYSE",
                "screener": "america",
                "nombre":   sym,
            })
            added.append(sym)

    _save(portfolio)
    print(f"\n  [+] Agregados a watchlist: {', '.join(added)}")


def _save(portfolio: dict) -> None:
    PORTFOLIO_PATH.write_text(
        json.dumps(portfolio, indent=2, ensure_ascii=False), encoding="utf-8"
    )


async def main():
    update = "--update" in sys.argv

    print("[*] Leyendo secciones desde TradingView...")
    sections = await read_tv_sections()

    portfolio = load_portfolio()

    posiciones = sections.get("POSICIONES", [])
    watchlist  = sections.get("WATCHLIST", [])

    if posiciones:
        report_positions(posiciones, portfolio, update)
    else:
        print("\n[!] No se encontraron simbolos en la seccion POSICIONES")

    if watchlist:
        report_watchlist(watchlist, portfolio, update)
    else:
        print("\n[!] No se encontraron simbolos en la seccion WATCHLIST")

    print(f"\n{'='*68}")
    print(f"  Uso: python tv_sync.py --update  para sincronizar portfolio.json")
    print(f"{'='*68}\n")


if __name__ == "__main__":
    asyncio.run(main())
