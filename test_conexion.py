"""
Script de diagnóstico para verificar la conexión con TradingView.

Ejecutar:
    python test_conexion.py

Comprueba:
  1. tradingview-ta  — indicadores técnicos (no requiere login)
  2. tvdatafeed      — datos históricos OHLCV (usa credenciales del .env)
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

VERDE  = "\033[92m"
ROJO   = "\033[91m"
AMARILLO = "\033[93m"
AZUL   = "\033[94m"
RESET  = "\033[0m"
NEGRITA = "\033[1m"


def ok(msg):  print(f"   {VERDE}✅ OK{RESET}  — {msg}")
def fallo(msg): print(f"   {ROJO}❌ FALLO{RESET} — {msg}")
def aviso(msg): print(f"   {AMARILLO}⚠️  {msg}{RESET}")
def info(msg):  print(f"   {AZUL}ℹ️  {msg}{RESET}")


# ─────────────────────────────────────────────────────────────
# 1. Variables de entorno
# ─────────────────────────────────────────────────────────────
def check_env():
    print(f"\n{NEGRITA}1. Variables de entorno (.env){RESET}")

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if api_key.startswith("sk-ant-"):
        ok(f"ANTHROPIC_API_KEY configurada ({api_key[:15]}...)")
    elif api_key:
        aviso(f"ANTHROPIC_API_KEY presente pero formato inesperado: {api_key[:10]}...")
    else:
        fallo("ANTHROPIC_API_KEY no encontrada. Crea el archivo .env a partir de .env.example")

    session_token = os.getenv("TV_SESSION_TOKEN", "").strip()
    username      = os.getenv("TV_USERNAME", "").strip()
    password      = os.getenv("TV_PASSWORD", "").strip()

    if session_token:
        ok(f"TV_SESSION_TOKEN configurado ({session_token[:20]}...)")
        info("Se usará el token de sesión (tiene prioridad sobre user/pass).")
    elif username and password:
        ok(f"TV_USERNAME: {username}")
        ok("TV_PASSWORD: (configurada)")
    else:
        aviso("Sin credenciales de TradingView → modo anónimo (datos limitados).")
        info("Añade TV_USERNAME + TV_PASSWORD al .env para acceso completo.")

    return bool(api_key)


# ─────────────────────────────────────────────────────────────
# 2. tradingview-ta
# ─────────────────────────────────────────────────────────────
def check_tradingview_ta():
    print(f"\n{NEGRITA}2. tradingview-ta (indicadores técnicos — sin login){RESET}")
    try:
        from tradingview_ta import TA_Handler, Interval
        handler = TA_Handler(
            symbol="AAPL",
            screener="america",
            exchange="NASDAQ",
            interval=Interval.INTERVAL_1_DAY,
        )
        analysis = handler.get_analysis()
        price = analysis.indicators.get("close", "N/A")
        rec   = analysis.summary.get("RECOMMENDATION", "N/A")
        rsi   = analysis.indicators.get("RSI", "N/A")
        ok(f"AAPL | Precio: ${price} | RSI: {rsi} | Señal: {rec}")
        return True
    except ImportError:
        fallo("tradingview-ta no instalado.")
        info("Ejecuta: pip install tradingview-ta")
        return False
    except Exception as e:
        fallo(str(e))
        return False


# ─────────────────────────────────────────────────────────────
# 3. yfinance
# ─────────────────────────────────────────────────────────────
def check_yfinance():
    print(f"\n{NEGRITA}3. yfinance (datos históricos OHLCV){RESET}")
    try:
        import yfinance as yf

        # Test: 5 velas diarias de AAPL
        ticker = yf.Ticker("AAPL")
        data   = ticker.history(period="5d", interval="1d", auto_adjust=True)

        if data is not None and not data.empty:
            data.columns = [c.lower() for c in data.columns]
            last = data.iloc[-1]
            ok(f"AAPL | {len(data)} barras obtenidas | "
               f"Último cierre: ${last['close']:.2f} ({data.index[-1].date()})")

            # Test crypto
            btc   = yf.Ticker("BTC-USD")
            d_btc = btc.history(period="3d", interval="1d", auto_adjust=True)
            if d_btc is not None and not d_btc.empty:
                d_btc.columns = [c.lower() for c in d_btc.columns]
                ok(f"BTC-USD | Último cierre: ${d_btc['close'].iloc[-1]:,.0f}")
            else:
                aviso("BTC-USD no disponible temporalmente.")

            return True
        else:
            fallo("No se obtuvieron datos de AAPL.")
            return False

    except ImportError:
        fallo("yfinance no instalado.")
        info("Ejecuta: pip install yfinance")
        return False
    except Exception as e:
        fallo(str(e))
        return False


# ─────────────────────────────────────────────────────────────
# 4. Test del agente completo
# ─────────────────────────────────────────────────────────────
def check_agente():
    print(f"\n{NEGRITA}4. Test rápido del agente (tools.py){RESET}")
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from tools import get_technical_analysis, get_market_overview
        result = get_technical_analysis(
            symbol="AAPL",
            exchange="NASDAQ",
            screener="america",
            interval="1d",
        )
        if "error" in result:
            fallo(result["error"])
            return False
        precio = result.get("precio_actual", "N/A")
        señal  = result.get("recomendacion_general", {}).get("señal", "N/A")
        rsi    = result.get("osciladores", {}).get("RSI_14", "N/A")
        ok(f"get_technical_analysis → AAPL ${precio} | Señal: {señal} | RSI: {rsi}")
        return True
    except Exception as e:
        fallo(f"Error importando tools.py: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# Resumen final
# ─────────────────────────────────────────────────────────────
def main():
    print(f"\n{NEGRITA}{'═'*55}")
    print("  TEST DE CONEXIÓN — AGENTE TRADER")
    print(f"{'═'*55}{RESET}")

    r_env = check_env()
    r_ta  = check_tradingview_ta()
    r_tv  = check_yfinance()
    r_ag  = check_agente()

    print(f"\n{NEGRITA}{'─'*55}")
    print("  RESUMEN")
    print(f"{'─'*55}{RESET}")

    estados = {
        "Variables de entorno (.env)":       r_env,
        "tradingview-ta (indicadores)":      r_ta,
        "yfinance (datos históricos)":        r_tv,
        "Agente — tools.py":                 r_ag,
    }
    for nombre, estado in estados.items():
        simbolo = f"{VERDE}✅{RESET}" if estado else f"{ROJO}❌{RESET}"
        print(f"  {simbolo}  {nombre}")

    print()
    if r_ta and r_tv:
        print(f"{VERDE}{NEGRITA}  ✅ Conexión completa. El agente tiene acceso total a TradingView.{RESET}")
        print(f"  Ejecuta: {AZUL}python agent.py{RESET}")
    elif r_ta and not r_tv:
        print(f"{AMARILLO}{NEGRITA}  ⚠️  Conexión parcial. El agente funciona con indicadores pero sin datos históricos.{RESET}")
        print(f"  Para datos históricos ejecuta: {AZUL}pip install yfinance{RESET}")
    else:
        print(f"{ROJO}{NEGRITA}  ❌ Faltan dependencias. Ejecuta: pip install -r requirements.txt{RESET}")
    print()


if __name__ == "__main__":
    main()
