"""
Herramientas de análisis técnico con integración TradingView y Yahoo Finance.
Usa tradingview-ta para indicadores y yfinance para datos OHLCV históricos.
"""

import os
import json
import numpy as np
import pandas as pd
from typing import Optional

from tradingview_ta import TA_Handler, Interval as TVInterval


# ─────────────────────────────────────────────────────────────
# Datos históricos OHLCV vía Yahoo Finance (yfinance)
# ─────────────────────────────────────────────────────────────
_COMMODITY_MAP = {
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "USOIL":  "CL=F",
    "UKOIL":  "BZ=F",
    "XNGUSD": "NG=F",
}


def _to_yf_symbol(symbol: str, exchange: str) -> str:
    """Convierte símbolo TradingView (symbol + exchange) a formato Yahoo Finance."""
    s  = symbol.upper()
    ex = exchange.upper()

    if s in _COMMODITY_MAP:
        return _COMMODITY_MAP[s]

    if ex in ("BINANCE", "COINBASE", "KRAKEN", "BYBIT", "OKX"):
        if s.endswith("USDT"):
            return s[:-4] + "-USD"
        if s.endswith("USDC"):
            return s[:-4] + "-USD"
        if s.endswith("BTC"):
            return s[:-3] + "-BTC"
        return s + "-USD"

    if ex in ("FX_IDC", "FX", "OANDA", "FXCM"):
        return s + "=X"

    return s   # acciones USA: AAPL, MSFT, SPY...


def _get_yf_data(
    symbol: str,
    exchange: str,
    interval: str = "1D",
    n_bars: int = 100,
) -> Optional[pd.DataFrame]:
    """
    Obtiene datos OHLCV históricos desde Yahoo Finance.
    Devuelve DataFrame con columnas en minúsculas: open, high, low, close, volume.
    Retorna None si yfinance no está instalado o hay error.
    """
    try:
        import yfinance as yf
    except ImportError:
        return None

    try:
        yf_symbol = _to_yf_symbol(symbol, exchange)
        iv = interval.lower()

        yf_iv_map = {
            "1m": "1m",  "5m": "5m",  "15m": "15m", "30m": "30m",
            "1h": "1h",  "2h": "1h",  "4h": "1h",
            "1d": "1d",  "1w": "1wk", "1wk": "1wk",
            "1mo": "1mo",
        }
        yf_iv = yf_iv_map.get(iv, "1d")

        period_map = {
            "1m": "7d",  "5m": "60d",  "15m": "60d", "30m": "60d",
            "1h": "2y",  "1d": "3y",   "1wk": "15y", "1mo": "max",
        }
        period = period_map.get(yf_iv, "2y")

        ticker = yf.Ticker(yf_symbol)
        data = ticker.history(period=period, interval=yf_iv, auto_adjust=True)

        if data is None or data.empty:
            return None

        data.columns = [c.lower() for c in data.columns]

        # Resamplear a 4h / 2h si fue pedido (yfinance no los soporta nativamente)
        if iv == "4h":
            data = data.resample("4h").agg(
                {"open": "first", "high": "max", "low": "min",
                 "close": "last", "volume": "sum"}
            ).dropna()
        elif iv == "2h":
            data = data.resample("2h").agg(
                {"open": "first", "high": "max", "low": "min",
                 "close": "last", "volume": "sum"}
            ).dropna()

        return data.tail(n_bars) if len(data) >= n_bars else data

    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# Mapeo de intervalos para tradingview-ta
# ─────────────────────────────────────────────────────────────
INTERVAL_MAP = {
    "1m":  TVInterval.INTERVAL_1_MINUTE,
    "5m":  TVInterval.INTERVAL_5_MINUTES,
    "15m": TVInterval.INTERVAL_15_MINUTES,
    "30m": TVInterval.INTERVAL_30_MINUTES,
    "1h":  TVInterval.INTERVAL_1_HOUR,
    "2h":  TVInterval.INTERVAL_2_HOURS,
    "4h":  TVInterval.INTERVAL_4_HOURS,
    "1d":  TVInterval.INTERVAL_1_DAY,
    "1D":  TVInterval.INTERVAL_1_DAY,
    "1W":  TVInterval.INTERVAL_1_WEEK,
    "1M":  TVInterval.INTERVAL_1_MONTH,
}


def _get_ta_interval(interval_str: str):
    """Obtiene el intervalo de tradingview-ta desde string."""
    return INTERVAL_MAP.get(interval_str, TVInterval.INTERVAL_1_DAY)


# ─────────────────────────────────────────────────────────────
# HERRAMIENTA 1: Análisis Técnico Completo (TradingView TA)
# ─────────────────────────────────────────────────────────────
def get_technical_analysis(
    symbol: str,
    exchange: str,
    screener: str,
    interval: str = "1d"
) -> dict:
    """
    Obtiene análisis técnico completo desde TradingView para un símbolo dado.
    Devuelve osciladores, medias móviles, indicadores y recomendación general.
    """
    ta_interval = _get_ta_interval(interval)
    handler = TA_Handler(
        symbol=symbol.upper(),
        screener=screener.lower(),
        exchange=exchange.upper(),
        interval=ta_interval,
    )
    analysis = handler.get_analysis()
    indicators = analysis.indicators

    # RSI
    rsi = indicators.get("RSI", None)
    rsi_condition = "NEUTRAL"
    if rsi is not None:
        if rsi > 70:
            rsi_condition = "SOBRECOMPRADO"
        elif rsi < 30:
            rsi_condition = "SOBREVENDIDO"
        elif rsi > 55:
            rsi_condition = "ALCISTA"
        elif rsi < 45:
            rsi_condition = "BAJISTA"

    # MACD
    macd = indicators.get("MACD.macd", None)
    macd_signal = indicators.get("MACD.signal", None)
    macd_hist = round(macd - macd_signal, 4) if (macd and macd_signal) else None
    macd_condition = "NEUTRAL"
    if macd and macd_signal:
        if macd > macd_signal and macd_hist > 0:
            macd_condition = "ALCISTA (cruce alcista, histograma positivo)"
        elif macd > macd_signal and macd_hist < 0:
            macd_condition = "ALCISTA (por encima señal, momentum debilitándose)"
        elif macd < macd_signal and macd_hist < 0:
            macd_condition = "BAJISTA (cruce bajista, histograma negativo)"
        elif macd < macd_signal and macd_hist > 0:
            macd_condition = "BAJISTA (por debajo señal, momentum recuperándose)"

    # EMAs
    ema9   = indicators.get("EMA9", None) or indicators.get("EMA[9]", None)
    ema20  = indicators.get("EMA20", None)
    ema50  = indicators.get("EMA50", None)
    ema200 = indicators.get("EMA200", None)
    price  = indicators.get("close", None)

    ema_analysis = {}
    if price and ema200:
        ema_analysis["tendencia_largo_plazo"] = "ALCISTA (precio > EMA200)" if price > ema200 else "BAJISTA (precio < EMA200)"
    if price and ema50:
        ema_analysis["tendencia_medio_plazo"] = "ALCISTA (precio > EMA50)" if price > ema50 else "BAJISTA (precio < EMA50)"
    if price and ema20:
        ema_analysis["tendencia_corto_plazo"] = "ALCISTA (precio > EMA20)" if price > ema20 else "BAJISTA (precio < EMA20)"
    if ema50 and ema200:
        if ema50 > ema200:
            ema_analysis["golden_death_cross"] = "GOLDEN CROSS activo (EMA50 > EMA200) - sesgo alcista"
        else:
            ema_analysis["golden_death_cross"] = "DEATH CROSS activo (EMA50 < EMA200) - sesgo bajista"

    # Stochastic
    stoch_k = indicators.get("Stoch.K", None)
    stoch_d = indicators.get("Stoch.D", None)
    stoch_condition = "NEUTRAL"
    if stoch_k:
        if stoch_k > 80:
            stoch_condition = "SOBRECOMPRADO"
        elif stoch_k < 20:
            stoch_condition = "SOBREVENDIDO"

    # Bollinger Bands
    bb_upper = indicators.get("BB.upper", None)
    bb_lower = indicators.get("BB.lower", None)
    bb_basis = indicators.get("BB.basis", None)
    bb_analysis = {}
    if price and bb_upper and bb_lower and bb_basis:
        bb_width = round((bb_upper - bb_lower) / bb_basis * 100, 2)
        bb_analysis["ancho_bb_pct"] = bb_width
        if price > bb_upper:
            bb_analysis["posicion"] = "Por encima banda superior (sobreextendido alcista)"
        elif price < bb_lower:
            bb_analysis["posicion"] = "Por debajo banda inferior (sobreextendido bajista)"
        else:
            bb_pct = round((price - bb_lower) / (bb_upper - bb_lower) * 100, 1)
            bb_analysis["posicion"] = f"Dentro de bandas ({bb_pct}% desde inferior)"
        if bb_width < 5:
            bb_analysis["compresion"] = "ALTA COMPRESIÓN - posible breakout inminente"

    # ADX
    adx = indicators.get("ADX", None)
    adx_plus = indicators.get("ADX+DI", None)
    adx_minus = indicators.get("ADX-DI", None)
    adx_analysis = {}
    if adx:
        if adx > 25:
            adx_analysis["fuerza_tendencia"] = f"TENDENCIA FUERTE (ADX={round(adx,1)})"
        elif adx > 20:
            adx_analysis["fuerza_tendencia"] = f"TENDENCIA MODERADA (ADX={round(adx,1)})"
        else:
            adx_analysis["fuerza_tendencia"] = f"MERCADO LATERAL (ADX={round(adx,1)})"
        if adx_plus and adx_minus:
            if adx_plus > adx_minus:
                adx_analysis["direccion"] = f"+DI ({round(adx_plus,1)}) > -DI ({round(adx_minus,1)}) → fuerza alcista"
            else:
                adx_analysis["direccion"] = f"-DI ({round(adx_minus,1)}) > +DI ({round(adx_plus,1)}) → fuerza bajista"

    # Pivotes clásicos
    pivot_m  = indicators.get("Pivot.M.Classic.Middle", None)
    pivot_r1 = indicators.get("Pivot.M.Classic.R1", None)
    pivot_r2 = indicators.get("Pivot.M.Classic.R2", None)
    pivot_s1 = indicators.get("Pivot.M.Classic.S1", None)
    pivot_s2 = indicators.get("Pivot.M.Classic.S2", None)

    pivots = {}
    for k, v in [("pivot", pivot_m), ("R1", pivot_r1), ("R2", pivot_r2),
                 ("S1", pivot_s1), ("S2", pivot_s2)]:
        if v is not None:
            pivots[k] = round(v, 4)

    return {
        "simbolo": f"{symbol.upper()} ({exchange.upper()}) - {interval}",
        "precio_actual": round(price, 4) if price else None,
        "recomendacion_general": {
            "señal": analysis.summary.get("RECOMMENDATION", "NEUTRAL"),
            "compra": analysis.summary.get("BUY", 0),
            "venta": analysis.summary.get("SELL", 0),
            "neutral": analysis.summary.get("NEUTRAL", 0),
        },
        "osciladores": {
            "señal": analysis.oscillators.get("RECOMMENDATION", "NEUTRAL"),
            "RSI_14": round(rsi, 2) if rsi else None,
            "RSI_condicion": rsi_condition,
            "MACD": round(macd, 4) if macd else None,
            "MACD_señal": round(macd_signal, 4) if macd_signal else None,
            "MACD_histograma": macd_hist,
            "MACD_condicion": macd_condition,
            "Estocastico_K": round(stoch_k, 2) if stoch_k else None,
            "Estocastico_D": round(stoch_d, 2) if stoch_d else None,
            "Estocastico_condicion": stoch_condition,
        },
        "medias_moviles": {
            "señal": analysis.moving_averages.get("RECOMMENDATION", "NEUTRAL"),
            "EMA9": round(ema9, 4) if ema9 else None,
            "EMA20": round(ema20, 4) if ema20 else None,
            "EMA50": round(ema50, 4) if ema50 else None,
            "EMA200": round(ema200, 4) if ema200 else None,
            "analisis_tendencia": ema_analysis,
        },
        "bollinger_bands": bb_analysis,
        "adx": adx_analysis,
        "pivotes_clasicos": pivots,
    }


# ─────────────────────────────────────────────────────────────
# HERRAMIENTA 2: Datos Históricos OHLCV (Yahoo Finance)
# ─────────────────────────────────────────────────────────────
def get_price_data(
    symbol: str,
    exchange: str,
    interval: str = "1D",
    n_bars: int = 100
) -> dict:
    """
    Obtiene datos OHLCV históricos desde Yahoo Finance.
    Incluye estadísticas de las últimas velas, volumen y tendencia de SMAs.
    """
    try:
        n_bars = min(n_bars, 500)
        data = _get_yf_data(symbol, exchange, interval, n_bars)

        if data is None or data.empty:
            return {
                "error": f"No se encontraron datos para {symbol} en {exchange}.",
                "solucion": "Verifica que yfinance esté instalado: pip install yfinance",
                "alternativa": "Usa get_technical_analysis para indicadores técnicos sin datos históricos",
            }

        last = data.iloc[-1]
        prev = data.iloc[-2] if len(data) > 1 else last

        price_change = (last["close"] - prev["close"]) / prev["close"] * 100
        avg_volume   = data["volume"].mean()
        vol_ratio    = last["volume"] / avg_volume if avg_volume > 0 else 1

        closes = data["close"].values
        sma20 = closes[-20:].mean() if len(closes) >= 20 else closes.mean()
        sma50 = closes[-50:].mean() if len(closes) >= 50 else closes.mean()

        return {
            "simbolo": f"{symbol.upper()} ({exchange.upper()}) - {interval}",
            "barras_analizadas": len(data),
            "ultima_vela": {
                "fecha": str(data.index[-1]),
                "apertura": round(last["open"], 4),
                "maximo":   round(last["high"], 4),
                "minimo":   round(last["low"], 4),
                "cierre":   round(last["close"], 4),
                "volumen":  int(last["volume"]),
                "cambio_pct": round(price_change, 2),
            },
            "rango_periodo": {
                "maximo":        round(data["high"].max(), 4),
                "minimo":        round(data["low"].min(), 4),
                "precio_actual": round(last["close"], 4),
            },
            "volumen": {
                "ultimo":          int(last["volume"]),
                "media_20p":       int(avg_volume),
                "ratio_vs_media":  round(vol_ratio, 2),
                "interpretacion": (
                    "VOLUMEN ALTO (>1.5x media)" if vol_ratio > 1.5 else
                    "VOLUMEN NORMAL"              if vol_ratio > 0.7 else
                    "VOLUMEN BAJO (<0.7x media)"
                ),
            },
            "tendencia_precio": {
                "SMA20":          round(sma20, 4),
                "SMA50":          round(sma50, 4),
                "precio_vs_SMA20": "SOBRE" if last["close"] > sma20 else "BAJO",
                "precio_vs_SMA50": "SOBRE" if last["close"] > sma50 else "BAJO",
                "SMA20_vs_SMA50":  "ALCISTA (SMA20>SMA50)" if sma20 > sma50 else "BAJISTA (SMA20<SMA50)",
            },
            "ultimas_5_velas": [
                {
                    "fecha": str(data.index[i]),
                    "O": round(data["open"].iloc[i], 4),
                    "H": round(data["high"].iloc[i], 4),
                    "L": round(data["low"].iloc[i], 4),
                    "C": round(data["close"].iloc[i], 4),
                    "V": int(data["volume"].iloc[i]),
                    "tipo": "ALCISTA" if data["close"].iloc[i] > data["open"].iloc[i] else "BAJISTA",
                }
                for i in range(-5, 0)
            ],
        }

    except ImportError:
        return {
            "error": "yfinance no instalado",
            "solucion": "Ejecuta: pip install yfinance",
        }
    except Exception as e:
        return {"error": f"Error obteniendo datos: {str(e)}"}


# ─────────────────────────────────────────────────────────────
# HERRAMIENTA 3: Análisis Multi-Timeframe
# ─────────────────────────────────────────────────────────────
def get_multi_timeframe_analysis(
    symbol: str,
    exchange: str,
    screener: str
) -> dict:
    """
    Analiza el símbolo en múltiples timeframes para identificar confluencias.
    Timeframes: Semanal, Diario, 4H, 1H
    """
    timeframes = {
        "Semanal (1W)":  "1W",
        "Diario (1D)":   "1D",
        "4 Horas (4H)":  "4h",
        "1 Hora (1H)":   "1h",
    }

    results = {}
    buy_count = 0
    sell_count = 0

    for tf_name, tf_code in timeframes.items():
        try:
            ta_interval = _get_ta_interval(tf_code)
            handler = TA_Handler(
                symbol=symbol.upper(),
                screener=screener.lower(),
                exchange=exchange.upper(),
                interval=ta_interval,
            )
            analysis = handler.get_analysis()
            ind = analysis.indicators

            recommendation = analysis.summary.get("RECOMMENDATION", "NEUTRAL")
            if "BUY" in recommendation:
                buy_count += 1
            elif "SELL" in recommendation:
                sell_count += 1

            rsi         = ind.get("RSI", None)
            macd        = ind.get("MACD.macd", None)
            macd_signal = ind.get("MACD.signal", None)
            ema50       = ind.get("EMA50", None)
            ema200      = ind.get("EMA200", None)
            price       = ind.get("close", None)

            results[tf_name] = {
                "recomendacion": recommendation,
                "compras": analysis.summary.get("BUY", 0),
                "ventas":  analysis.summary.get("SELL", 0),
                "RSI": round(rsi, 1) if rsi else None,
                "MACD_posicion": "ALCISTA" if (macd and macd_signal and macd > macd_signal) else "BAJISTA",
                "tendencia_EMA": (
                    "ALCISTA" if (price and ema50 and ema200 and price > ema50 > ema200) else
                    "BAJISTA" if (price and ema50 and ema200 and price < ema50 < ema200) else
                    "MIXTA"
                ),
                "precio": round(price, 4) if price else None,
            }
        except Exception as e:
            results[tf_name] = {"error": str(e)}

    total_valid = buy_count + sell_count
    if total_valid == 0:
        confluencia      = "NEUTRAL - Sin señal clara"
        probabilidad_est = 50
    elif buy_count >= 3:
        confluencia      = f"ALCISTA FUERTE - {buy_count}/4 timeframes alineados al alza"
        probabilidad_est = 60 + (buy_count * 5)
    elif sell_count >= 3:
        confluencia      = f"BAJISTA FUERTE - {sell_count}/4 timeframes alineados a la baja"
        probabilidad_est = 60 + (sell_count * 5)
    elif buy_count == 2:
        confluencia      = f"SESGO ALCISTA MODERADO - {buy_count}/4 timeframes alcistas"
        probabilidad_est = 55
    elif sell_count == 2:
        confluencia      = f"SESGO BAJISTA MODERADO - {sell_count}/4 timeframes bajistas"
        probabilidad_est = 55
    else:
        confluencia      = "NEUTRAL/MIXTO - Señales contradictorias entre timeframes"
        probabilidad_est = 45

    return {
        "simbolo": f"{symbol.upper()} ({exchange.upper()})",
        "analisis_por_timeframe": results,
        "confluencia": {
            "descripcion":          confluencia,
            "timeframes_alcistas":  buy_count,
            "timeframes_bajistas":  sell_count,
            "probabilidad_estimada": f"{min(probabilidad_est, 80)}%",
            "recomendacion": (
                "OPERAR AL ALZA (alta confluencia)"   if buy_count >= 3 else
                "OPERAR A LA BAJA (alta confluencia)" if sell_count >= 3 else
                "ESPERAR MAYOR CONFIRMACIÓN"
            ),
        },
    }


# ─────────────────────────────────────────────────────────────
# HERRAMIENTA 4: Niveles Fibonacci
# ─────────────────────────────────────────────────────────────
def calculate_fibonacci_levels(
    symbol: str,
    exchange: str,
    interval: str = "1D",
    n_bars: int = 100
) -> dict:
    """
    Calcula niveles de retroceso y extensión de Fibonacci usando el swing
    alto y bajo más recientes del período analizado.
    """
    data_result = get_price_data(symbol, exchange, interval, n_bars)

    if "error" in data_result:
        # Fallback: usar TA handler para obtener high/low aproximados
        try:
            ta_interval = _get_ta_interval(interval)
            handler = TA_Handler(
                symbol=symbol.upper(),
                screener="america" if exchange.upper() in ["NASDAQ", "NYSE", "AMEX"] else "crypto",
                exchange=exchange.upper(),
                interval=ta_interval,
            )
            ind = handler.get_analysis().indicators
            swing_high    = ind.get("high", None)
            swing_low     = ind.get("low", None)
            current_price = ind.get("close", None)

            if not (swing_high and swing_low):
                return {"error": "No se pudieron obtener datos de precio para Fibonacci"}
        except Exception as e:
            return {"error": f"No se pudo calcular Fibonacci: {str(e)}"}
    else:
        swing_high    = data_result["rango_periodo"]["maximo"]
        swing_low     = data_result["rango_periodo"]["minimo"]
        current_price = data_result["ultima_vela"]["cierre"]

    diff = swing_high - swing_low

    ret_levels = {
        "0.0% (Máximo)":  round(swing_high, 4),
        "23.6%":          round(swing_high - 0.236 * diff, 4),
        "38.2%":          round(swing_high - 0.382 * diff, 4),
        "50.0%":          round(swing_high - 0.500 * diff, 4),
        "61.8% (Golden)": round(swing_high - 0.618 * diff, 4),
        "78.6%":          round(swing_high - 0.786 * diff, 4),
        "100% (Mínimo)":  round(swing_low, 4),
    }

    ext_levels = {
        "127.2%": round(swing_low + 1.272 * diff, 4),
        "141.4%": round(swing_low + 1.414 * diff, 4),
        "161.8%": round(swing_low + 1.618 * diff, 4),
        "200.0%": round(swing_low + 2.000 * diff, 4),
        "261.8%": round(swing_low + 2.618 * diff, 4),
    }

    all_levels = {**ret_levels, **ext_levels}
    nearest    = min(all_levels.items(), key=lambda x: abs(x[1] - current_price))

    fib_618 = swing_high - 0.618 * diff
    fib_382 = swing_high - 0.382 * diff
    fib_50  = swing_high - 0.500 * diff

    zona_analisis = "FUERA DE ZONAS FIBONACCI CLAVE"
    if abs(current_price - fib_618) / fib_618 < 0.01:
        zona_analisis = "⭐ PRECIO EN ZONA 61.8% (GOLDEN RATIO) - Soporte/Resistencia de alta probabilidad"
    elif abs(current_price - fib_382) / fib_382 < 0.01:
        zona_analisis = "⭐ PRECIO EN ZONA 38.2% - Retroceso moderado, posible rebote"
    elif abs(current_price - fib_50) / fib_50 < 0.01:
        zona_analisis = "⭐ PRECIO EN ZONA 50% - Nivel de equilibrio psicológico"

    return {
        "simbolo":      f"{symbol.upper()} ({exchange.upper()}) - {interval}",
        "precio_actual": round(current_price, 4),
        "swing_alto":    round(swing_high, 4),
        "swing_bajo":    round(swing_low, 4),
        "rango":         round(diff, 4),
        "retrocesos_fibonacci": ret_levels,
        "extensiones_fibonacci": ext_levels,
        "nivel_mas_cercano": {
            "nivel":        nearest[0],
            "precio":       nearest[1],
            "distancia_pct": round(abs(nearest[1] - current_price) / current_price * 100, 2),
        },
        "analisis_zona_actual": zona_analisis,
        "zonas_clave_para_trading": {
            "soporte_profundo_618":  round(fib_618, 4),
            "soporte_moderado_382":  round(fib_382, 4),
            "soporte_equilibrio_50": round(fib_50, 4),
        },
    }


# ─────────────────────────────────────────────────────────────
# HERRAMIENTA 5: Soporte y Resistencia
# ─────────────────────────────────────────────────────────────
def calculate_support_resistance(
    symbol: str,
    exchange: str,
    interval: str = "1D",
    n_bars: int = 100
) -> dict:
    """
    Calcula niveles de soporte y resistencia usando:
    - Puntos pivot clásicos
    - Niveles psicológicos (redondos)
    - Máximos/mínimos recientes del período
    """
    data = _get_yf_data(symbol, exchange, interval, n_bars)

    if data is None or data.empty:
        # Fallback con pivot points del indicador TA
        try:
            ta_interval = _get_ta_interval(interval)
            screener    = "crypto" if any(x in exchange.upper() for x in ["BINANCE", "COINBASE", "KRAKEN"]) else "america"
            handler = TA_Handler(
                symbol=symbol.upper(),
                screener=screener,
                exchange=exchange.upper(),
                interval=ta_interval,
            )
            ind = handler.get_analysis().indicators
            current_price = ind.get("close", 0)

            pivots = {
                "Pivot": ind.get("Pivot.M.Classic.Middle"),
                "R1":    ind.get("Pivot.M.Classic.R1"),
                "R2":    ind.get("Pivot.M.Classic.R2"),
                "R3":    ind.get("Pivot.M.Classic.R3"),
                "S1":    ind.get("Pivot.M.Classic.S1"),
                "S2":    ind.get("Pivot.M.Classic.S2"),
                "S3":    ind.get("Pivot.M.Classic.S3"),
            }
            pivots = {k: round(v, 4) for k, v in pivots.items() if v is not None}

            return {
                "simbolo":             f"{symbol.upper()} ({exchange.upper()})",
                "precio_actual":       round(current_price, 4) if current_price else None,
                "pivot_points_clasicos": pivots,
                "nota": "Calculado con pivots de TradingView (datos históricos no disponibles)"
            }
        except Exception as e:
            return {"error": str(e)}

    last  = data.iloc[-1]
    H     = last["high"]
    L     = last["low"]
    C     = last["close"]
    current_price = C

    # Pivot points clásicos (basados en la última vela)
    P  = (H + L + C) / 3
    R1 = 2*P - L
    R2 = P + (H - L)
    R3 = H + 2*(P - L)
    S1 = 2*P - H
    S2 = P - (H - L)
    S3 = L - 2*(H - P)

    # Niveles psicológicos (redondos)
    price_mag    = 10 ** (len(str(int(current_price))) - 1)
    psych_levels = [
        round(current_price / price_mag) * price_mag * i / 10
        for i in range(int(current_price / price_mag * 10) - 3, int(current_price / price_mag * 10) + 4)
    ]
    psych_levels = [p for p in psych_levels if p > 0 and abs(p - current_price) / current_price < 0.1]

    high_periodo = data["high"].max()
    low_periodo  = data["low"].min()

    return {
        "simbolo":       f"{symbol.upper()} ({exchange.upper()}) - {interval}",
        "precio_actual": round(current_price, 4),
        "pivot_points_clasicos": {
            "R3":        round(R3, 4),
            "R2":        round(R2, 4),
            "R1":        round(R1, 4),
            "Pivot (P)": round(P, 4),
            "S1":        round(S1, 4),
            "S2":        round(S2, 4),
            "S3":        round(S3, 4),
        },
        "maximo_periodo":                  round(high_periodo, 4),
        "minimo_periodo":                  round(low_periodo, 4),
        "niveles_psicologicos_proximos":   [round(p, 2) for p in psych_levels],
        "zona_precio": (
            "SOBRE PIVOT - Sesgo alcista a corto plazo" if current_price > P else
            "BAJO PIVOT - Sesgo bajista a corto plazo"
        ),
        "resistencias_inmediatas": [round(r, 4) for r in sorted([R1, R2]) if r > current_price],
        "soportes_inmediatos":     [round(s, 4) for s in sorted([S1, S2], reverse=True) if s < current_price],
    }


# ─────────────────────────────────────────────────────────────
# HERRAMIENTA 6: Análisis de Volumen
# ─────────────────────────────────────────────────────────────
def analyze_volume(
    symbol: str,
    exchange: str,
    interval: str = "1D"
) -> dict:
    """
    Analiza patrones de volumen: OBV, tendencia del volumen, divergencias precio-volumen.
    """
    data = _get_yf_data(symbol, exchange, interval, 50)

    if data is None or data.empty:
        # Fallback: usar indicadores de TA
        try:
            ta_interval = _get_ta_interval(interval)
            screener    = "crypto" if any(x in exchange.upper() for x in ["BINANCE", "COINBASE"]) else "america"
            handler = TA_Handler(
                symbol=symbol.upper(),
                screener=screener,
                exchange=exchange.upper(),
                interval=ta_interval,
            )
            ind    = handler.get_analysis().indicators
            volume = ind.get("volume", None)
            obv    = ind.get("OBV", None)
            vwap   = ind.get("VWAP", None)
            close  = ind.get("close", None)

            return {
                "simbolo":        f"{symbol.upper()} ({exchange.upper()})",
                "volumen_actual": int(volume) if volume else None,
                "OBV":            round(obv, 2) if obv else None,
                "VWAP":           round(vwap, 4) if vwap else None,
                "precio_vs_VWAP": (
                    "SOBRE VWAP (compradores en control)" if (close and vwap and close > vwap) else
                    "BAJO VWAP (vendedores en control)"
                ) if (close and vwap) else None,
            }
        except Exception as e:
            return {"error": str(e)}

    closes  = data["close"].values
    volumes = data["volume"].values

    # OBV manual
    obv    = np.zeros(len(closes))
    obv[0] = volumes[0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv[i] = obv[i-1] + volumes[i]
        elif closes[i] < closes[i-1]:
            obv[i] = obv[i-1] - volumes[i]
        else:
            obv[i] = obv[i-1]

    # Tendencia OBV y precio (últimas 10 velas)
    obv_recent   = obv[-10:]
    price_recent = closes[-10:]
    obv_slope    = np.polyfit(range(len(obv_recent)),   obv_recent,   1)[0]
    price_slope  = np.polyfit(range(len(price_recent)), price_recent, 1)[0]

    if price_slope > 0 and obv_slope > 0:
        divergence = "CONFIRMACION ALCISTA (precio sube + OBV sube) - Tendencia sana"
    elif price_slope < 0 and obv_slope < 0:
        divergence = "CONFIRMACION BAJISTA (precio baja + OBV baja) - Tendencia sana"
    elif price_slope > 0 and obv_slope < 0:
        divergence = "⚠️ DIVERGENCIA BAJISTA (precio sube pero OBV baja) - Señal de debilidad"
    else:
        divergence = "⚠️ DIVERGENCIA ALCISTA (precio baja pero OBV sube) - Señal de acumulación"

    avg_vol_20  = volumes[-20:].mean()
    current_vol = volumes[-1]
    vol_ratio   = current_vol / avg_vol_20 if avg_vol_20 > 0 else 1

    buy_days  = sum(1 for i in range(-10, 0) if closes[i] > data["open"].values[i])
    sell_days = 10 - buy_days

    return {
        "simbolo":          f"{symbol.upper()} ({exchange.upper()}) - {interval}",
        "volumen_actual":   int(current_vol),
        "media_volumen_20p": int(avg_vol_20),
        "ratio_volumen":    round(vol_ratio, 2),
        "evaluacion_volumen": (
            "🔥 VOLUMEN MUY ALTO (>2x media) - Movimiento institucional significativo" if vol_ratio > 2 else
            "📈 VOLUMEN ALTO (1.5-2x media) - Interés aumentado"                       if vol_ratio > 1.5 else
            "✅ VOLUMEN NORMAL (0.7-1.5x media)"                                        if vol_ratio > 0.7 else
            "📉 VOLUMEN BAJO (<0.7x media) - Movimiento poco confiable"
        ),
        "OBV_tendencia": {
            "direccion":   "SUBIENDO (acumulación)" if obv_slope > 0 else "BAJANDO (distribución)",
            "OBV_actual":  round(obv[-1], 0),
            "OBV_hace_10p": round(obv[-10], 0),
        },
        "divergencia_precio_volumen": divergence,
        "presion_compradora_vs_vendedora": {
            "ultimas_10_velas": f"{buy_days} alcistas / {sell_days} bajistas",
            "sesgo": "COMPRADORES en control" if buy_days > sell_days else "VENDEDORES en control",
        },
    }


# ─────────────────────────────────────────────────────────────
# HERRAMIENTA 7: Análisis de Portfolio Personal
# ─────────────────────────────────────────────────────────────
def _find_portfolio_path() -> str:
    """Busca portfolio.json probando varias ubicaciones posibles."""
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio.json"),
        os.path.join(os.getcwd(), "portfolio.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Agente Trader", "portfolio.json"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]  # devuelve el primero para mostrar el error con la ruta


def analyze_portfolio() -> dict:
    """
    Analiza todas las posiciones en portfolio.json.
    Calcula P&L en tiempo real y señal técnica de cada activo.
    """
    portfolio_path = _find_portfolio_path()

    try:
        with open(portfolio_path, "r", encoding="utf-8") as f:
            portfolio_data = json.load(f)
    except FileNotFoundError:
        return {
            "error": "portfolio.json no encontrado.",
            "solucion": "Crea el archivo portfolio.json en la carpeta del agente con tus posiciones.",
        }
    except json.JSONDecodeError as e:
        return {"error": f"Error de formato en portfolio.json: {str(e)}"}

    positions = portfolio_data.get("positions", [])
    if not positions:
        return {"info": "No hay posiciones en portfolio.json. Añade tus activos al archivo."}

    results        = []
    total_invertido = 0.0
    total_actual    = 0.0

    for pos in positions:
        symbol          = pos.get("symbol", "")
        exchange        = pos.get("exchange", "")
        screener        = pos.get("screener", "america")
        cantidad        = float(pos.get("cantidad", 0))
        precio_promedio = float(pos.get("precio_promedio", 0))

        try:
            analysis      = get_technical_analysis(symbol, exchange, screener, "1d")
            current_price = analysis.get("precio_actual") or 0.0

            valor_invertido  = cantidad * precio_promedio
            valor_actual     = cantidad * current_price
            pl_absoluto      = valor_actual - valor_invertido
            pl_porcentual    = (pl_absoluto / valor_invertido * 100) if valor_invertido > 0 else 0.0

            total_invertido += valor_invertido
            total_actual    += valor_actual

            señal = analysis.get("recomendacion_general", {}).get("señal", "N/A")
            rsi   = analysis.get("osciladores", {}).get("RSI_14", None)

            # Alerta de riesgo
            alerta = ""
            if rsi and rsi > 75:
                alerta = "⚠️ RSI sobrecomprado — considerar reducir posición"
            elif rsi and rsi < 25:
                alerta = "⚠️ RSI sobrevendido — posible zona de acumulación"
            if pl_porcentual < -10:
                alerta += " | 🔴 Pérdida >10% — revisar stop-loss"

            results.append({
                "simbolo":        symbol,
                "nombre":         pos.get("nombre", symbol),
                "cantidad":       cantidad,
                "precio_entrada": precio_promedio,
                "precio_actual":  current_price,
                "valor_invertido": round(valor_invertido, 2),
                "valor_actual":    round(valor_actual, 2),
                "pl_absoluto":    round(pl_absoluto, 2),
                "pl_porcentual":  round(pl_porcentual, 2),
                "estado_pl":      "GANANCIA" if pl_porcentual >= 0 else "PERDIDA",
                "señal_tecnica":  señal,
                "RSI":            round(rsi, 1) if rsi else None,
                "fecha_entrada":  pos.get("fecha_entrada", "N/A"),
                "notas":          pos.get("notas", ""),
                "alerta":         alerta.strip(" |"),
            })

        except Exception as e:
            results.append({"simbolo": symbol, "nombre": pos.get("nombre", symbol), "error": str(e)})

    pl_total     = total_actual - total_invertido
    pl_total_pct = (pl_total / total_invertido * 100) if total_invertido > 0 else 0.0
    ganadoras    = sum(1 for r in results if r.get("pl_porcentual", 0) >= 0)
    perdedoras   = len(results) - ganadoras

    # Posición con mayor pérdida (riesgo prioritario)
    con_pl = [r for r in results if "pl_porcentual" in r]
    peor   = min(con_pl, key=lambda r: r["pl_porcentual"]) if con_pl else None
    mejor  = max(con_pl, key=lambda r: r["pl_porcentual"]) if con_pl else None

    return {
        "resumen_portfolio": {
            "total_posiciones":     len(results),
            "capital_invertido":    round(total_invertido, 2),
            "valor_actual":         round(total_actual, 2),
            "pl_total_absoluto":    round(pl_total, 2),
            "pl_total_porcentual":  round(pl_total_pct, 2),
            "estado_general":       "EN GANANCIA" if pl_total >= 0 else "EN PERDIDA",
            "posiciones_ganadoras": ganadoras,
            "posiciones_perdedoras": perdedoras,
            "mejor_posicion":       f"{mejor['simbolo']} (+{mejor['pl_porcentual']}%)" if mejor else None,
            "peor_posicion":        f"{peor['simbolo']} ({peor['pl_porcentual']}%)" if peor else None,
        },
        "posiciones": results,
    }


# ─────────────────────────────────────────────────────────────
# HERRAMIENTA 8: Análisis de Watchlist
# ─────────────────────────────────────────────────────────────
def analyze_watchlist() -> dict:
    """
    Analiza todos los activos en la watchlist de portfolio.json.
    Identifica los setups más interesantes del momento.
    """
    portfolio_path = _find_portfolio_path()

    try:
        with open(portfolio_path, "r", encoding="utf-8") as f:
            portfolio_data = json.load(f)
    except FileNotFoundError:
        return {"error": "portfolio.json no encontrado."}
    except json.JSONDecodeError as e:
        return {"error": f"Error de formato en portfolio.json: {str(e)}"}

    watchlist = portfolio_data.get("watchlist", [])
    if not watchlist:
        return {"info": "La watchlist está vacía. Añade activos en portfolio.json → 'watchlist'."}

    results    = []
    oportunidades = []

    for item in watchlist:
        symbol   = item.get("symbol", "")
        exchange = item.get("exchange", "")
        screener = item.get("screener", "america")

        try:
            analysis      = get_technical_analysis(symbol, exchange, screener, "1d")
            current_price = analysis.get("precio_actual")
            señal         = analysis.get("recomendacion_general", {}).get("señal", "NEUTRAL")
            rsi           = analysis.get("osciladores", {}).get("RSI_14", None)
            macd_cond     = analysis.get("osciladores", {}).get("MACD_condicion", "")
            bb            = analysis.get("bollinger_bands", {})
            adx           = analysis.get("adx", {})

            # Puntaje de oportunidad (0-100)
            score = 0
            motivos = []

            if "STRONG_BUY" in señal:
                score += 40; motivos.append("señal STRONG_BUY")
            elif "BUY" in señal:
                score += 20; motivos.append("señal BUY")
            elif "STRONG_SELL" in señal:
                score += 40; motivos.append("señal STRONG_SELL (corto)")
            elif "SELL" in señal:
                score += 20; motivos.append("señal SELL (corto)")

            if rsi and 40 <= rsi <= 60:
                score += 15; motivos.append("RSI en zona neutral (buen punto de entrada)")
            elif rsi and rsi < 35:
                score += 25; motivos.append(f"RSI sobrevendido ({round(rsi,1)})")
            elif rsi and rsi > 65:
                score += 10; motivos.append(f"RSI alto ({round(rsi,1)})")

            if "compresion" in bb:
                score += 20; motivos.append("compresión de Bollinger (breakout inminente)")

            if "FUERTE" in adx.get("fuerza_tendencia", ""):
                score += 15; motivos.append("tendencia fuerte (ADX)")

            entry = {
                "simbolo":      symbol,
                "nombre":       item.get("nombre", symbol),
                "precio":       current_price,
                "señal":        señal,
                "RSI":          round(rsi, 1) if rsi else None,
                "MACD":         macd_cond,
                "score_oportunidad": score,
                "motivos":      motivos,
            }
            results.append(entry)

            if score >= 40:
                oportunidades.append(entry)

        except Exception as e:
            results.append({"simbolo": symbol, "nombre": item.get("nombre", symbol), "error": str(e)})

    # Ordenar por score descendente
    results.sort(key=lambda x: x.get("score_oportunidad", 0), reverse=True)
    oportunidades.sort(key=lambda x: x.get("score_oportunidad", 0), reverse=True)

    return {
        "total_activos_watchlist": len(results),
        "oportunidades_destacadas": oportunidades,
        "analisis_completo": results,
        "resumen": (
            f"{len(oportunidades)} activos con score ≥40/100 en la watchlist"
            if oportunidades else
            "Ningún activo destaca especialmente en este momento. Esperar mejor setup."
        ),
    }


# ─────────────────────────────────────────────────────────────
# HERRAMIENTA 9: Análisis Fundamental (Yahoo Finance)
# ─────────────────────────────────────────────────────────────
def get_fundamental_analysis(symbol: str, exchange: str) -> dict:
    """
    Análisis fundamental completo: valoración, rentabilidad, salud financiera,
    crecimiento, dividendos y consenso de analistas con precio objetivo.
    """
    try:
        import yfinance as yf
    except ImportError:
        return {"error": "yfinance no instalado. Ejecuta: pip install yfinance"}

    def _fmt(v, pct=False, usd=False):
        if v is None:
            return None
        if pct:
            return round(v * 100, 2)
        if usd:
            if abs(v) >= 1e12: return f"${v/1e12:.2f}T"
            if abs(v) >= 1e9:  return f"${v/1e9:.2f}B"
            if abs(v) >= 1e6:  return f"${v/1e6:.2f}M"
            return f"${v:,.0f}"
        return round(v, 2) if isinstance(v, float) else v

    try:
        yf_symbol = _to_yf_symbol(symbol, exchange)
        info = yf.Ticker(yf_symbol).info

        if not info or len(info) < 5:
            return {"error": f"No se encontró información fundamental para {symbol}. "
                             "Verifica que el símbolo sea correcto y sea una acción (no crypto/forex)."}

        # ── Precio y rango 52 semanas ──
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        high_52w      = info.get("fiftyTwoWeekHigh")
        low_52w       = info.get("fiftyTwoWeekLow")
        pct_from_high = round((current_price - high_52w) / high_52w * 100, 1) if (current_price and high_52w) else None
        pct_from_low  = round((current_price - low_52w)  / low_52w  * 100, 1) if (current_price and low_52w)  else None

        # ── Interpretación P/E ──
        pe = info.get("trailingPE")
        if   pe is None:      pe_interp = "No disponible"
        elif pe < 0:          pe_interp = "Pérdidas (P/E negativo)"
        elif pe < 15:         pe_interp = "BARATO — P/E por debajo de la media histórica"
        elif pe < 25:         pe_interp = "RAZONABLE — valoración justa"
        elif pe < 40:         pe_interp = "CARO — exige crecimiento sostenido"
        else:                 pe_interp = "MUY CARO — se paga prima de alto crecimiento"

        # ── Consenso analistas ──
        rec_num  = info.get("recommendationMean")
        if   rec_num is None: rec_text = "Sin cobertura"
        elif rec_num <= 1.5:  rec_text = "STRONG BUY"
        elif rec_num <= 2.5:  rec_text = "BUY"
        elif rec_num <= 3.5:  rec_text = "HOLD"
        elif rec_num <= 4.5:  rec_text = "SELL"
        else:                 rec_text = "STRONG SELL"

        target = info.get("targetMeanPrice")
        upside = round((target - current_price) / current_price * 100, 1) if (target and current_price) else None

        # ── Salud financiera ──
        debt    = info.get("totalDebt")  or 0
        cash    = info.get("totalCash")  or 0
        net_cash = cash - debt
        dte      = info.get("debtToEquity")
        if   dte is None:  dte_interp = "N/A"
        elif dte < 30:     dte_interp = "BAJA — balance sólido"
        elif dte < 80:     dte_interp = "MODERADA — manejable"
        elif dte < 150:    dte_interp = "ALTA — vigilar refinanciamiento"
        else:              dte_interp = "MUY ALTA — riesgo financiero elevado"

        # ── Márgenes ──
        margen_neto = info.get("profitMargins")
        if   margen_neto is None: mg_interp = "N/A"
        elif margen_neto < 0:     mg_interp = "Empresa en pérdidas"
        elif margen_neto < 0.05:  mg_interp = "BAJO (<5%) — negocio de bajo margen"
        elif margen_neto < 0.15:  mg_interp = "MODERADO (5-15%)"
        elif margen_neto < 0.25:  mg_interp = "ALTO (15-25%) — ventaja competitiva"
        else:                     mg_interp = "MUY ALTO (>25%) — negocio de foso profundo"

        return {
            "simbolo":    f"{symbol.upper()} — {info.get('longName', symbol)}",
            "sector":     info.get("sector"),
            "industria":  info.get("industry"),
            "descripcion": (info.get("longBusinessSummary") or "")[:300] + "...",

            "precio": {
                "actual":           current_price,
                "52w_maximo":       high_52w,
                "52w_minimo":       low_52w,
                "pct_desde_maximo": pct_from_high,
                "pct_desde_minimo": pct_from_low,
                "beta":             _fmt(info.get("beta")),
            },

            "valoracion": {
                "market_cap":       _fmt(info.get("marketCap"), usd=True),
                "PE_trailing":      _fmt(pe),
                "PE_forward":       _fmt(info.get("forwardPE")),
                "PB_ratio":         _fmt(info.get("priceToBook")),
                "PS_ratio":         _fmt(info.get("priceToSalesTrailing12Months")),
                "EV_EBITDA":        _fmt(info.get("enterpriseToEbitda")),
                "PEG_ratio":        _fmt(info.get("pegRatio")),
                "interpretacion_PE": pe_interp,
            },

            "rentabilidad": {
                "revenue":              _fmt(info.get("totalRevenue"), usd=True),
                "EBITDA":               _fmt(info.get("ebitda"), usd=True),
                "margen_bruto_pct":     _fmt(info.get("grossMargins"), pct=True),
                "margen_operativo_pct": _fmt(info.get("operatingMargins"), pct=True),
                "margen_neto_pct":      _fmt(margen_neto, pct=True),
                "interpretacion_margen": mg_interp,
                "ROE_pct":  _fmt(info.get("returnOnEquity"), pct=True),
                "ROA_pct":  _fmt(info.get("returnOnAssets"), pct=True),
            },

            "crecimiento": {
                "revenue_growth_pct":   _fmt(info.get("revenueGrowth"), pct=True),
                "earnings_growth_pct":  _fmt(info.get("earningsGrowth"), pct=True),
                "EPS_trailing":         _fmt(info.get("trailingEps")),
                "EPS_forward":          _fmt(info.get("forwardEps")),
            },

            "salud_financiera": {
                "cash":              _fmt(cash, usd=True),
                "deuda_total":       _fmt(debt, usd=True),
                "posicion_neta_caja": _fmt(net_cash, usd=True),
                "deuda_equity":      _fmt(dte),
                "interpretacion_deuda": dte_interp,
                "current_ratio":     _fmt(info.get("currentRatio")),
                "free_cash_flow":    _fmt(info.get("freeCashflow"), usd=True),
            },

            "dividendos": {
                "yield_pct":        _fmt(info.get("dividendYield"), pct=True),
                "dividendo_anual":  _fmt(info.get("dividendRate")),
                "payout_ratio_pct": _fmt(info.get("payoutRatio"), pct=True),
            },

            "consenso_analistas": {
                "recomendacion":             rec_text,
                "score_medio_1a5":           _fmt(rec_num),
                "num_analistas":             info.get("numberOfAnalystOpinions"),
                "precio_objetivo_promedio":  target,
                "precio_objetivo_alto":      info.get("targetHighPrice"),
                "precio_objetivo_bajo":      info.get("targetLowPrice"),
                "upside_potencial_pct":      upside,
            },
        }

    except Exception as e:
        return {"error": f"Error en análisis fundamental de {symbol}: {str(e)}"}


# ─────────────────────────────────────────────────────────────
# HERRAMIENTA 10: Screening de Acciones (Finviz)
# ─────────────────────────────────────────────────────────────
def screen_stocks(
    strategy: str = "momentum",
    sector: str = None,
    market_cap: str = "large",
    max_results: int = 15,
) -> dict:
    """
    Escanea el mercado americano con Finviz para encontrar oportunidades de trading.
    Estrategias: momentum, oversold, breakout, golden_cross, strong_buy
    """
    try:
        from finvizfinance.screener.overview import Overview
    except ImportError:
        return {
            "error": "finvizfinance no instalado",
            "solucion": "pip install finvizfinance",
        }

    cap_map = {
        "mega":  "Mega ($200bln and more)",
        "large": "Large ($10bln to $200bln)",
        "mid":   "Mid ($2bln to $10bln)",
        "small": "Small ($300mln to $2bln)",
        "any":   "Small+ ($300mln and more)",
    }
    cap_filter = cap_map.get(market_cap.lower(), "Large ($10bln to $200bln)")

    strategies = {
        "momentum": {
            "descripcion": "Tendencia alcista fuerte: precio sobre SMA20, SMA50 y SMA200",
            "filters": {
                "Country": "USA",
                "Market Cap.": cap_filter,
                "20-Day Simple Moving Average": "Price above SMA20",
                "50-Day Simple Moving Average":  "Price above SMA50",
                "200-Day Simple Moving Average": "Price above SMA200",
            },
        },
        "oversold": {
            "descripcion": "Sobrevendidas (RSI<30) con tendencia de largo plazo alcista — posible rebote",
            "filters": {
                "Country": "USA",
                "Market Cap.": cap_filter,
                "RSI (14)": "Oversold (< 30)",
                "200-Day Simple Moving Average": "Price above SMA200",
            },
        },
        "breakout": {
            "descripcion": "Volumen relativo >2x media — posible breakout en curso",
            "filters": {
                "Country": "USA",
                "Market Cap.": cap_filter,
                "Relative Volume": "Over 2",
                "20-Day Simple Moving Average": "Price above SMA20",
            },
        },
        "golden_cross": {
            "descripcion": "Golden Cross activo: SMA50 sobre SMA200 con precio confirmando",
            "filters": {
                "Country": "USA",
                "Market Cap.": cap_filter,
                "50-Day Simple Moving Average":  "SMA50 above SMA200",
                "200-Day Simple Moving Average": "Price above SMA200",
            },
        },
        "strong_buy": {
            "descripcion": "Múltiples señales alcistas: precio sobre todas las SMAs, RSI no sobrecomprado",
            "filters": {
                "Country": "USA",
                "Market Cap.": cap_filter,
                "RSI (14)": "Not Overbought (<70)",
                "20-Day Simple Moving Average": "Price above SMA20",
                "50-Day Simple Moving Average":  "Price above SMA50",
                "200-Day Simple Moving Average": "Price above SMA200",
            },
        },
    }

    if strategy not in strategies:
        return {
            "error": f"Estrategia '{strategy}' no reconocida.",
            "estrategias_disponibles": list(strategies.keys()),
        }

    config  = strategies[strategy]
    filters = config["filters"].copy()
    if sector:
        filters["Sector"] = sector

    try:
        foverview = Overview()
        foverview.set_filter(filters_dict=filters)
        df = foverview.screener_view()

        if df is None or df.empty:
            return {
                "estrategia":    strategy,
                "descripcion":   config["descripcion"],
                "resultado":     "Sin resultados con estos filtros. Prueba con market_cap='any' o cambia la estrategia.",
                "filtros_usados": filters,
            }

        df = df.head(max_results)

        resultados = []
        for _, row in df.iterrows():
            resultados.append({
                "ticker":     str(row.get("Ticker", "")),
                "empresa":    str(row.get("Company", "")),
                "sector":     str(row.get("Sector", "")),
                "industria":  str(row.get("Industry", "")),
                "precio":     row.get("Price", None),
                "cambio_pct": row.get("Change", None),
                "volumen":    row.get("Volume", None),
                "market_cap": str(row.get("Market Cap", "")),
                "pe_ratio":   row.get("P/E", None),
            })

        return {
            "estrategia":      strategy,
            "descripcion":     config["descripcion"],
            "market_cap":      market_cap,
            "sector_filtrado": sector or "Todos",
            "total_encontrados": len(df),
            "resultados":      resultados,
            "siguiente_paso":  "Usa get_technical_analysis o get_multi_timeframe_analysis para profundizar en los candidatos más interesantes.",
        }

    except Exception as e:
        return {"error": f"Error en Finviz screener: {str(e)}"}


# ─────────────────────────────────────────────────────────────
# HERRAMIENTA 10: Visión General del Mercado
# ─────────────────────────────────────────────────────────────
def get_market_overview(market: str = "stocks") -> dict:
    """
    Obtiene el estado general de los principales activos del mercado seleccionado.
    Mercados: 'stocks', 'crypto', 'forex', 'commodities'
    """
    market = market.lower()

    symbols_config = {
        "stocks": [
            ("SPY",  "AMEX",    "america", "S&P 500 ETF"),
            ("QQQ",  "NASDAQ",  "america", "Nasdaq 100 ETF"),
            ("DIA",  "AMEX",    "america", "Dow Jones ETF"),
            ("IWM",  "AMEX",    "america", "Russell 2000 ETF"),
            ("VIX",  "CBOE",    "america", "Volatilidad (VIX)"),
        ],
        "crypto": [
            ("BTCUSDT", "BINANCE", "crypto", "Bitcoin"),
            ("ETHUSDT", "BINANCE", "crypto", "Ethereum"),
            ("BNBUSDT", "BINANCE", "crypto", "BNB"),
            ("SOLUSDT", "BINANCE", "crypto", "Solana"),
            ("XRPUSDT", "BINANCE", "crypto", "XRP"),
        ],
        "forex": [
            ("EURUSD", "FX_IDC", "forex", "EUR/USD"),
            ("GBPUSD", "FX_IDC", "forex", "GBP/USD"),
            ("USDJPY", "FX_IDC", "forex", "USD/JPY"),
            ("AUDUSD", "FX_IDC", "forex", "AUD/USD"),
            ("USDCHF", "FX_IDC", "forex", "USD/CHF"),
        ],
        "commodities": [
            ("XAUUSD", "FX_IDC", "forex", "Oro (XAU/USD)"),
            ("XAGUSD", "FX_IDC", "forex", "Plata (XAG/USD)"),
            ("USOIL",  "FX_IDC", "cfd",   "Petróleo WTI"),
            ("UKOIL",  "FX_IDC", "cfd",   "Petróleo Brent"),
            ("XNGUSD", "FX_IDC", "cfd",   "Gas Natural"),
        ],
    }

    if market not in symbols_config:
        return {"error": f"Mercado no reconocido: {market}. Opciones: stocks, crypto, forex, commodities"}

    assets = symbols_config[market]
    results       = {}
    bullish_count = 0
    bearish_count = 0

    for symbol, exchange, screener, name in assets:
        try:
            handler = TA_Handler(
                symbol=symbol,
                screener=screener,
                exchange=exchange,
                interval=TVInterval.INTERVAL_1_DAY,
            )
            analysis       = handler.get_analysis()
            ind            = analysis.indicators
            recommendation = analysis.summary.get("RECOMMENDATION", "NEUTRAL")

            if "BUY" in recommendation:
                bullish_count += 1
            elif "SELL" in recommendation:
                bearish_count += 1

            rsi    = ind.get("RSI", None)
            price  = ind.get("close", None)
            ema200 = ind.get("EMA200", None)

            results[name] = {
                "precio":      round(price, 4) if price else None,
                "señal":       recommendation,
                "RSI":         round(rsi, 1) if rsi else None,
                "sobre_EMA200": price > ema200 if (price and ema200) else None,
            }
        except Exception as e:
            results[name] = {"error": str(e)}

    total         = bullish_count + bearish_count
    sentiment_pct = round(bullish_count / total * 100) if total > 0 else 50

    if sentiment_pct >= 70:
        sentiment = f"ALCISTA FUERTE ({sentiment_pct}% activos en señal de compra)"
    elif sentiment_pct >= 55:
        sentiment = f"SESGO ALCISTA ({sentiment_pct}% activos en señal de compra)"
    elif sentiment_pct <= 30:
        sentiment = f"BAJISTA FUERTE ({100-sentiment_pct}% activos en señal de venta)"
    elif sentiment_pct <= 45:
        sentiment = f"SESGO BAJISTA ({100-sentiment_pct}% activos en señal de venta)"
    else:
        sentiment = f"NEUTRAL/MIXTO ({sentiment_pct}% alcistas)"

    return {
        "mercado":             market.upper(),
        "sentimiento_general": sentiment,
        "activos_alcistas":    bullish_count,
        "activos_bajistas":    bearish_count,
        "detalle_activos":     results,
        "recomendacion_operativa": (
            "✅ CONDICIONES FAVORABLES para operar en largo"                        if sentiment_pct >= 65 else
            "🔴 CONDICIONES FAVORABLES para operar en corto"                        if sentiment_pct <= 35 else
            "⚠️ MERCADO MIXTO - Ser selectivo, esperar setups de alta probabilidad"
        ),
    }
