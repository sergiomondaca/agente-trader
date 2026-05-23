"""
Agente Experto en Trading - 40 años de experiencia
Integración TradingView + Claude Opus 4.6 con adaptive thinking
"""

import anthropic
import json
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from system_prompt import SYSTEM_PROMPT
from tools import (
    get_technical_analysis,
    get_price_data,
    get_multi_timeframe_analysis,
    calculate_fibonacci_levels,
    calculate_support_resistance,
    analyze_volume,
    get_market_overview,
    analyze_portfolio,
    analyze_watchlist,
    screen_stocks,
    get_fundamental_analysis,
    get_historial,
    switch_tv_chart,
    draw_tv_line,
    update_portfolio_position,
)

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ─────────────────────────────────────────────────────────────
# Definición de herramientas para Claude
# ─────────────────────────────────────────────────────────────
TOOLS = [
    {
        "name": "get_technical_analysis",
        "description": (
            "Obtiene análisis técnico completo desde TradingView: osciladores (RSI, MACD, Estocástico), "
            "medias móviles (EMA 9/20/50/200), Bollinger Bands, ADX, pivots y recomendación general "
            "(STRONG_BUY / BUY / NEUTRAL / SELL / STRONG_SELL). "
            "Úsalo para evaluar la condición técnica actual de un activo en un timeframe específico."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Símbolo del activo. Acciones: 'AAPL', 'MSFT'. Crypto: 'BTCUSDT'. Forex: 'EURUSD'. Índices: 'SPY', 'QQQ'."
                },
                "exchange": {
                    "type": "string",
                    "description": "Bolsa o exchange. Acciones USA: 'NASDAQ', 'NYSE', 'AMEX'. Crypto: 'BINANCE'. Forex: 'FX_IDC'. Índices: 'AMEX'."
                },
                "screener": {
                    "type": "string",
                    "description": "Tipo de mercado: 'america' (acciones USA), 'crypto', 'forex', 'cfd' (commodities/índices CFD)."
                },
                "interval": {
                    "type": "string",
                    "description": "Timeframe: '1m', '5m', '15m', '30m', '1h', '2h', '4h', '1d', '1W', '1M'. Por defecto '1d'.",
                    "default": "1d"
                }
            },
            "required": ["symbol", "exchange", "screener"]
        }
    },
    {
        "name": "get_price_data",
        "description": (
            "Obtiene datos históricos OHLCV (apertura, máximo, mínimo, cierre, volumen) desde TradingView. "
            "Incluye estadísticas de las últimas 5 velas, análisis de volumen vs media, y tendencia de SMAs. "
            "Útil para identificar patrones de velas, contexto del precio reciente y comportamiento del volumen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":   {"type": "string", "description": "Símbolo del activo (ej: 'AAPL', 'BTCUSDT')."},
                "exchange": {"type": "string", "description": "Exchange (ej: 'NASDAQ', 'BINANCE')."},
                "interval": {"type": "string", "description": "Timeframe: '1m','5m','15m','30m','1h','4h','1D','1W'.", "default": "1D"},
                "n_bars":   {"type": "integer", "description": "Número de velas a obtener (1-500). Default 100.", "default": 100}
            },
            "required": ["symbol", "exchange"]
        }
    },
    {
        "name": "get_multi_timeframe_analysis",
        "description": (
            "Analiza el activo simultáneamente en 4 timeframes: Semanal (1W), Diario (1D), 4H y 1H. "
            "Calcula la confluencia entre timeframes y estima la probabilidad del setup. "
            "Si 3 o 4 timeframes están alineados en la misma dirección, la probabilidad supera el 65%. "
            "Usa esto para validar la dirección antes de buscar entrada."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":   {"type": "string", "description": "Símbolo del activo."},
                "exchange": {"type": "string", "description": "Exchange."},
                "screener": {"type": "string", "description": "Tipo de mercado: 'america', 'crypto', 'forex', 'cfd'."}
            },
            "required": ["symbol", "exchange", "screener"]
        }
    },
    {
        "name": "calculate_fibonacci_levels",
        "description": (
            "Calcula niveles de retroceso (23.6%, 38.2%, 50%, 61.8%, 78.6%) y extensión (127.2%, 141.4%, 161.8%, 200%) "
            "de Fibonacci usando el swing alto y bajo del período analizado. "
            "El nivel 61.8% (Golden Ratio) es el retroceso más poderoso para entradas de alta probabilidad. "
            "Úsalo para identificar zonas óptimas de entrada y objetivos de precio."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":   {"type": "string", "description": "Símbolo del activo."},
                "exchange": {"type": "string", "description": "Exchange."},
                "interval": {"type": "string", "description": "Timeframe para calcular el swing. Default '1D'.", "default": "1D"},
                "n_bars":   {"type": "integer", "description": "Velas para buscar el swing. Default 100.", "default": 100}
            },
            "required": ["symbol", "exchange"]
        }
    },
    {
        "name": "calculate_support_resistance",
        "description": (
            "Identifica niveles clave de soporte y resistencia usando: "
            "pivot points clásicos (P, R1, R2, R3, S1, S2, S3), "
            "niveles psicológicos (precios redondos), y "
            "máximos/mínimos del período. "
            "Úsalo para definir zonas donde el precio es más probable que reaccione, "
            "y para colocar stop-loss y objetivos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":   {"type": "string", "description": "Símbolo del activo."},
                "exchange": {"type": "string", "description": "Exchange."},
                "interval": {"type": "string", "description": "Timeframe. Default '1D'.", "default": "1D"},
                "n_bars":   {"type": "integer", "description": "Velas a analizar. Default 100.", "default": 100}
            },
            "required": ["symbol", "exchange"]
        }
    },
    {
        "name": "analyze_volume",
        "description": (
            "Analiza patrones de volumen: OBV (On Balance Volume), tendencia del volumen vs su media de 20 períodos, "
            "y divergencias precio-volumen. "
            "Una divergencia bajista (precio sube, OBV baja) señala distribución (posible techo). "
            "Una divergencia alcista (precio baja, OBV sube) señala acumulación (posible suelo). "
            "El volumen SIEMPRE debe confirmar el movimiento de precio antes de operar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":   {"type": "string", "description": "Símbolo del activo."},
                "exchange": {"type": "string", "description": "Exchange."},
                "interval": {"type": "string", "description": "Timeframe. Default '1D'.", "default": "1D"}
            },
            "required": ["symbol", "exchange"]
        }
    },
    {
        "name": "get_market_overview",
        "description": (
            "Obtiene el panorama general del mercado seleccionado analizando los principales activos. "
            "- 'stocks': SPY, QQQ, DIA, IWM, VIX "
            "- 'crypto': BTC, ETH, BNB, SOL, XRP "
            "- 'forex': EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CHF "
            "- 'commodities': Oro, Plata, Petróleo WTI, Brent, Gas Natural "
            "Úsalo para evaluar el sentimiento del mercado antes de operar un activo específico. "
            "No nades contra la corriente del mercado general."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "description": "Mercado a analizar: 'stocks', 'crypto', 'forex', 'commodities'.",
                    "enum": ["stocks", "crypto", "forex", "commodities"]
                }
            },
            "required": ["market"]
        }
    },
    {
        "name": "analyze_portfolio",
        "description": (
            "Analiza todas las posiciones del portfolio personal (portfolio.json). "
            "Calcula P&L en tiempo real (precio de entrada vs precio actual), rentabilidad % por posición, "
            "P&L total del portfolio, y señal técnica actual de cada activo. "
            "Usa esto cuando el usuario pregunte por su portfolio, sus posiciones abiertas, "
            "sus ganancias/pérdidas, o qué activos tiene en cartera."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "analyze_watchlist",
        "description": (
            "Analiza todos los activos de la watchlist personal (portfolio.json → 'watchlist'). "
            "Puntúa cada activo por oportunidad (0-100) basándose en señal técnica, RSI, "
            "compresión de Bollinger y fuerza de tendencia. "
            "Identifica los mejores setups del momento entre los activos que el usuario sigue. "
            "Usa esto cuando el usuario pregunte qué activos de su lista tienen mejor setup ahora."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_historial",
        "description": (
            "Lee el historial de consultas anteriores guardadas localmente. "
            "Úsalo cuando el usuario pregunte por consultas pasadas, análisis previos, "
            "o quiera saber qué se analizó en una fecha específica. "
            "Si se indica una fecha (formato YYYY-MM-DD), devuelve solo ese día. "
            "Si no se indica fecha, devuelve los últimos 7 días."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha": {
                    "type": "string",
                    "description": "Fecha en formato YYYY-MM-DD (ej: '2026-04-18'). Opcional — si se omite devuelve los últimos 7 días."
                },
                "ultimas_n": {
                    "type": "integer",
                    "description": "Número de consultas a mostrar por día. Default: 10.",
                    "default": 10
                }
            },
            "required": []
        }
    },
    {
        "name": "get_fundamental_analysis",
        "description": (
            "Obtiene análisis fundamental completo de una acción desde Yahoo Finance. "
            "Incluye: valoración (P/E, P/B, P/S, EV/EBITDA, PEG), rentabilidad (ROE, ROA, márgenes), "
            "salud financiera (deuda, cash, free cash flow, current ratio), crecimiento (revenue, EPS), "
            "dividendos y consenso de analistas con precio objetivo y upside potencial. "
            "Úsalo cuando el usuario quiera saber si una acción está cara o barata, "
            "analizar los fundamentales, ver el precio objetivo de los analistas, "
            "o combinar análisis técnico + fundamental para una tesis completa."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Símbolo de la acción (ej: 'AAPL', 'NVDA', 'PLTR'). Solo funciona con acciones, no con crypto ni forex."
                },
                "exchange": {
                    "type": "string",
                    "description": "Exchange: 'NASDAQ', 'NYSE', 'AMEX'."
                }
            },
            "required": ["symbol", "exchange"]
        }
    },
    {
        "name": "switch_tv_chart",
        "description": (
            "Cambia el símbolo del gráfico activo en TradingView. "
            "Requiere que Brave esté abierto con --remote-debugging-port=9222."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Símbolo a mostrar (ej: AAPL, PLTR, OKLO)."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "draw_tv_line",
        "description": (
            "Dibuja una línea horizontal en el gráfico de TradingView. "
            "Útil para marcar entradas, stops, soportes y resistencias. "
            "Cambia automáticamente al símbolo antes de dibujar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Símbolo donde dibujar la línea."},
                "price":  {"type": "number",  "description": "Precio de la línea horizontal."},
                "label":  {"type": "string",  "description": "Etiqueta de la línea (ej: 'Stop Loss $45.00', 'Entrada $120'). Opcional."},
                "color":  {"type": "string",  "description": "Color hex. Naranja #FF9800 (entrada), Rojo #F44336 (stop), Verde #4CAF50 (objetivo). Default: #FF9800."},
            },
            "required": ["symbol", "price"],
        },
    },
    {
        "name": "update_portfolio_position",
        "description": (
            "Agrega, edita o elimina una posición en portfolio.json. "
            "Usa 'add' para nueva posición, 'edit' para actualizar cantidad/precio, 'remove' para eliminar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action":          {"type": "string", "enum": ["add", "edit", "remove"], "description": "Acción a realizar."},
                "symbol":          {"type": "string", "description": "Símbolo del activo (ej: AAPL)."},
                "cantidad":        {"type": "number", "description": "Número de acciones/unidades."},
                "precio_promedio": {"type": "number", "description": "Precio promedio de compra."},
                "nombre":          {"type": "string", "description": "Nombre completo de la empresa."},
                "exchange":        {"type": "string", "description": "Exchange: NYSE, NASDAQ, AMEX."},
                "notas":           {"type": "string", "description": "Notas adicionales sobre la posición."},
            },
            "required": ["action", "symbol"],
        },
    },
    {
        "name": "screen_stocks",
        "description": (
            "Escanea el mercado americano con Finviz para encontrar oportunidades de trading según una estrategia. "
            "Estrategias disponibles:\n"
            "- 'momentum': acciones en tendencia alcista fuerte (precio sobre SMA20/50/200)\n"
            "- 'oversold': sobrevendidas (RSI<30) con tendencia de largo plazo alcista — rebotes potenciales\n"
            "- 'breakout': volumen relativo >2x — posible breakout en curso\n"
            "- 'golden_cross': SMA50 cruzó sobre SMA200 recientemente\n"
            "- 'strong_buy': múltiples señales alcistas alineadas, RSI no sobrecomprado\n"
            "Úsalo cuando el usuario pida ideas de trading, quiera saber qué acciones tienen buen setup, "
            "o pida un screener de mercado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "strategy": {
                    "type": "string",
                    "description": "Estrategia de búsqueda.",
                    "enum": ["momentum", "oversold", "breakout", "golden_cross", "strong_buy"]
                },
                "sector": {
                    "type": "string",
                    "description": "Sector a filtrar (opcional). Ej: 'Technology', 'Healthcare', 'Energy', 'Financial', 'Consumer Cyclical', 'Industrials'. Si no se especifica, busca en todos los sectores."
                },
                "market_cap": {
                    "type": "string",
                    "description": "Tamaño de empresa: 'mega' (>$200B), 'large' ($10B-$200B), 'mid' ($2B-$10B), 'small' ($300M-$2B), 'any' (todas >$300M). Default: 'large'.",
                    "enum": ["mega", "large", "mid", "small", "any"],
                    "default": "large"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Número máximo de resultados a devolver (1-30). Default: 15.",
                    "default": 15
                }
            },
            "required": ["strategy"]
        }
    },
]


# ─────────────────────────────────────────────────────────────
# Historial de consultas
# ─────────────────────────────────────────────────────────────
HISTORIAL_DIR = Path(__file__).parent / "historial"


def _save_historial(consulta: str, respuesta: str, tools_usadas: list, tokens: dict) -> None:
    """Guarda la consulta y respuesta en el archivo de historial del día."""
    HISTORIAL_DIR.mkdir(exist_ok=True)
    filepath = HISTORIAL_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.json"

    entrada = {
        "hora":          datetime.now().strftime("%H:%M:%S"),
        "consulta":      consulta,
        "respuesta":     respuesta,
        "tools_usadas":  tools_usadas,
        "tokens":        tokens,
    }

    entries = []
    if filepath.exists():
        try:
            entries = json.loads(filepath.read_text(encoding="utf-8"))
        except Exception:
            entries = []

    entries.append(entrada)
    filepath.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def show_historial(n_dias: int = 7) -> None:
    """Muestra las últimas consultas del historial."""
    if not HISTORIAL_DIR.exists():
        print("  Sin historial guardado todavía.")
        return

    archivos = sorted(HISTORIAL_DIR.glob("*.json"), reverse=True)[:n_dias]
    if not archivos:
        print("  Sin historial guardado todavía.")
        return

    for archivo in archivos:
        fecha = archivo.stem
        try:
            entries = json.loads(archivo.read_text(encoding="utf-8"))
        except Exception:
            continue
        print(f"\n  📅 {fecha} — {len(entries)} consulta(s)")
        for e in entries:
            tools_str = ", ".join(e.get("tools_usadas", [])) or "—"
            print(f"     {e['hora']}  {e['consulta'][:70]}")
            print(f"           Tools: {tools_str}")


# ─────────────────────────────────────────────────────────────
# Dispatcher de herramientas
# ─────────────────────────────────────────────────────────────
def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Ejecuta la herramienta solicitada y devuelve el resultado como JSON string."""
    dispatch = {
        "get_technical_analysis":       get_technical_analysis,
        "get_price_data":               get_price_data,
        "get_multi_timeframe_analysis": get_multi_timeframe_analysis,
        "calculate_fibonacci_levels":   calculate_fibonacci_levels,
        "calculate_support_resistance": calculate_support_resistance,
        "analyze_volume":               analyze_volume,
        "get_market_overview":          get_market_overview,
        "analyze_portfolio":            analyze_portfolio,
        "analyze_watchlist":            analyze_watchlist,
        "screen_stocks":                screen_stocks,
        "get_fundamental_analysis":     get_fundamental_analysis,
        "get_historial":                get_historial,
        "switch_tv_chart":              switch_tv_chart,
        "draw_tv_line":                 draw_tv_line,
        "update_portfolio_position":    update_portfolio_position,
    }

    fn = dispatch.get(tool_name)
    if fn is None:
        return json.dumps({"error": f"Herramienta desconocida: {tool_name}"})

    try:
        result = fn(**tool_input)
        return json.dumps(result, indent=2, default=str, ensure_ascii=False)
    except TypeError as e:
        return json.dumps({"error": f"Parámetros incorrectos para {tool_name}: {str(e)}"})
    except Exception as e:
        return json.dumps({"error": f"Error en {tool_name}: {str(e)}"})


# ─────────────────────────────────────────────────────────────
# Agente principal
# ─────────────────────────────────────────────────────────────
def run_trader_agent(user_query: str, verbose_tools: bool = True) -> None:
    """
    Ejecuta el agente de trading con la consulta del usuario.
    Usa streaming + adaptive thinking + prompt caching en el system prompt.
    """
    print(f"\n{'═'*65}")
    print(f"  CONSULTA: {user_query}")
    print(f"  Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'═'*65}")

    # Contexto dinámico en el PRIMER mensaje (no en system prompt para preservar caché)
    context_prefix = (
        f"[Contexto: Fecha actual {datetime.now().strftime('%A %d de %B de %Y, %H:%M')}. "
        f"Usuario: Sergio]\n\n"
    )

    messages = [{"role": "user", "content": context_prefix + user_query}]

    # System prompt con cache_control para reutilizar entre llamadas
    system_with_cache = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}
        }
    ]

    iteration     = 0
    max_iterations = 12
    full_response  = []   # texto completo para historial
    tools_usadas   = []   # tools llamadas en esta consulta
    tokens_info    = {}

    while iteration < max_iterations:
        iteration += 1

        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=system_with_cache,
            tools=TOOLS,
            messages=messages,
        ) as stream:

            thinking_shown = False
            has_text = False

            for event in stream:
                if event.type == "content_block_start":
                    if event.content_block.type == "thinking":
                        if not thinking_shown:
                            print("\n⚙️  [Analizando con 40 años de experiencia...]", flush=True)
                            thinking_shown = True
                    elif event.content_block.type == "text":
                        if thinking_shown and not has_text:
                            print()
                        has_text = True

                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        print(event.delta.text, end="", flush=True)
                        full_response.append(event.delta.text)

                elif event.type == "content_block_stop":
                    pass

            response = stream.get_final_message()

        usage = response.usage
        cache_read    = getattr(usage, "cache_read_input_tokens", 0)
        cache_created = getattr(usage, "cache_creation_input_tokens", 0)

        if iteration == 1 and (cache_read or cache_created):
            print(f"\n\n[Tokens: entrada={usage.input_tokens} | "
                  f"caché_lectura={cache_read} | caché_escritura={cache_created} | "
                  f"salida={usage.output_tokens}]", flush=True)

        tokens_info = {
            "entrada":       usage.input_tokens,
            "salida":        usage.output_tokens,
            "cache_lectura": cache_read,
        }

        if response.stop_reason == "end_turn":
            print(f"\n{'═'*65}\n")
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tools_usadas.append(block.name)
                    if verbose_tools:
                        args_str = json.dumps(block.input, ensure_ascii=False)
                        print(f"\n\n📡 [{block.name}({args_str})]", flush=True)

                    result_str = execute_tool(block.name, block.input)

                    if verbose_tools:
                        try:
                            preview_keys = list(json.loads(result_str).keys())[:3]
                            print(f"   ↳ OK: {preview_keys}...", flush=True)
                        except Exception:
                            print(f"   ↳ OK", flush=True)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

            messages.append({"role": "user", "content": tool_results})

        else:
            print(f"\n[Stop reason: {response.stop_reason}]")
            break

    if iteration >= max_iterations:
        print(f"\n⚠️  Límite de iteraciones alcanzado ({max_iterations})")

    # Guardar en historial
    try:
        _save_historial(
            consulta    = user_query,
            respuesta   = "".join(full_response),
            tools_usadas = list(dict.fromkeys(tools_usadas)),  # sin duplicados
            tokens      = tokens_info,
        )
    except Exception:
        pass  # El historial nunca debe interrumpir la sesión


# ─────────────────────────────────────────────────────────────
# Sesión multi-turno
# ─────────────────────────────────────────────────────────────
def run_interactive_session():
    """
    Sesión interactiva de trading. El agente mantiene contexto entre preguntas
    dentro de la misma sesión.
    """
    print("\n" + "╔" + "═"*63 + "╗")
    print("║  🏦 AGENTE EXPERTO EN TRADING — 40 AÑOS DE EXPERIENCIA  ║")
    print("║      TradingView + Claude Opus 4.6 + Adaptive Thinking      ║")
    print("╚" + "═"*63 + "╝")
    print()
    print("Ejemplos de consultas:")
    print("  • Analiza AAPL en el timeframe diario")
    print("  • ¿Cuál es el estado del mercado crypto hoy?")
    print("  • Dame un setup de entrada para BTCUSDT")
    print("  • Analiza EURUSD con multi-timeframe y dame niveles Fibonacci")
    print("  • ¿Hay alguna oportunidad interesante en acciones tecnológicas?")
    print()
    print("Comandos: 'salir'/'exit' para terminar | 'nuevo' para limpiar sesión | 'historial' para ver consultas")
    print("─" * 65)

    while True:
        try:
            query = input("\n💬 Tu consulta: ").strip()

            if not query:
                continue

            if query.lower() in ("salir", "exit", "quit", "q"):
                print("\n✅ Sesión finalizada. Opera con disciplina y gestiona bien el riesgo.")
                break

            if query.lower() == "nuevo":
                print("\n🔄 Nueva sesión iniciada.")
                continue

            if query.lower() in ("historial", "historia", "log"):
                print(f"\n{'─'*65}")
                print("  HISTORIAL DE CONSULTAS (últimos 7 días)")
                print(f"{'─'*65}")
                show_historial(7)
                print()
                continue

            run_trader_agent(query)

        except KeyboardInterrupt:
            print("\n\n✅ Sesión interrumpida. ¡Hasta pronto!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("Intenta de nuevo con otra consulta.")


if __name__ == "__main__":
    run_interactive_session()
