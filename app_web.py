"""
Interfaz web del Agente Trader — Streamlit
Ejecutar: streamlit run app_web.py
"""

import streamlit as st
import anthropic
import json
import os
from datetime import datetime
from dotenv import load_dotenv

from system_prompt import SYSTEM_PROMPT
from agent import execute_tool, TOOLS, _save_historial

load_dotenv()

# API key: primero Streamlit Secrets (nube), luego .env (local)
def _get_api_key() -> str:
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        return os.getenv("ANTHROPIC_API_KEY", "")

# ─────────────────────────────────────────────────────────────
# Protección con contraseña
# ─────────────────────────────────────────────────────────────
def _check_password() -> bool:
    def _verify():
        try:
            pwd_correct = st.secrets["APP_PASSWORD"]
        except Exception:
            pwd_correct = os.getenv("APP_PASSWORD", "trader")
        st.session_state["auth"] = (st.session_state["pwd_input"] == pwd_correct)

    if st.session_state.get("auth"):
        return True

    st.title("🏦 Agente Trader")
    st.text_input("Contraseña", type="password", key="pwd_input", on_change=_verify)
    if st.session_state.get("auth") is False:
        st.error("Contraseña incorrecta.")
    return False

if not _check_password():
    st.stop()

# ─────────────────────────────────────────────────────────────
# Configuración de página
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Agente Trader",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .stChatMessage { padding: 0.5rem 0; }
    .tool-box { background:#1e2a3a; border-left:3px solid #4a9eff;
                padding:0.5rem 1rem; border-radius:4px; margin:0.3rem 0;
                font-size:0.85rem; color:#a0c4ff; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📈 Agente Trader")
    st.caption("TradingView + Claude Opus 4.6")
    st.divider()

    st.markdown("**Consultas rápidas**")
    quick = [
        "Analiza mi portfolio",
        "¿Qué activos de mi watchlist tienen mejor setup?",
        "Dame oportunidades momentum en tecnología",
        "¿Cómo está el mercado hoy?",
        "Análisis multi-timeframe de PLTR",
        "Análisis fundamental de ORCL",
    ]
    for q in quick:
        if st.button(q, use_container_width=True, key=f"q_{q[:20]}"):
            st.session_state.pending_query = q

    st.divider()
    if st.button("🗑️ Limpiar conversación", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

    st.divider()
    st.caption(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    api_ok = bool(os.getenv("ANTHROPIC_API_KEY"))
    st.caption("🟢 API conectada" if api_ok else "🔴 API key no encontrada")

# ─────────────────────────────────────────────────────────────
# Estado de sesión
# ─────────────────────────────────────────────────────────────
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "pending_query" not in st.session_state:
    st.session_state.pending_query = None

client = anthropic.Anthropic(api_key=_get_api_key())

# ─────────────────────────────────────────────────────────────
# Cabecera
# ─────────────────────────────────────────────────────────────
st.title("🏦 Agente Experto en Trading")
st.caption("40 años de experiencia · TradingView · Yahoo Finance · Finviz")

# ─────────────────────────────────────────────────────────────
# Historial de chat
# ─────────────────────────────────────────────────────────────
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "📊"):
        st.markdown(msg["content"])
        if msg.get("tools"):
            for t in msg["tools"]:
                st.markdown(
                    f'<div class="tool-box">📡 <b>{t["name"]}</b> '
                    f'— {json.dumps(t["input"], ensure_ascii=False)[:120]}</div>',
                    unsafe_allow_html=True,
                )

# ─────────────────────────────────────────────────────────────
# Función principal del agente
# ─────────────────────────────────────────────────────────────
def run_agent(user_query: str):
    context_prefix = (
        f"[Contexto: Fecha actual {datetime.now().strftime('%A %d de %B de %Y, %H:%M')}. "
        f"Usuario: Sergio]\n\n"
    )

    api_messages = [{"role": "user", "content": context_prefix + user_query}]
    system_cached = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]

    iteration      = 0
    max_iterations = 12
    full_text      = []
    tools_used     = []
    tokens_info    = {}

    response_placeholder = st.empty()
    tool_boxes           = []

    while iteration < max_iterations:
        iteration += 1
        streamed_text = []

        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=system_cached,
            tools=TOOLS,
            messages=api_messages,
        ) as stream:

            for event in stream:
                if event.type == "content_block_start":
                    if event.content_block.type == "thinking":
                        response_placeholder.markdown("*⚙️ Analizando...*")

                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        streamed_text.append(event.delta.text)
                        full_text.append(event.delta.text)
                        response_placeholder.markdown("".join(full_text) + "▌")

            response = stream.get_final_message()

        usage = response.usage
        tokens_info = {
            "entrada":       usage.input_tokens,
            "salida":        usage.output_tokens,
            "cache_lectura": getattr(usage, "cache_read_input_tokens", 0),
        }

        if response.stop_reason == "end_turn":
            response_placeholder.markdown("".join(full_text))
            break

        if response.stop_reason == "tool_use":
            api_messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    tools_used.append({"name": block.name, "input": block.input})
                    tool_boxes.append({"name": block.name, "input": block.input})

                    # Mostrar tool call en el placeholder
                    tool_line = (
                        f'<div class="tool-box">📡 <b>{block.name}</b> '
                        f'— {json.dumps(block.input, ensure_ascii=False)[:120]}</div>'
                    )
                    response_placeholder.markdown(
                        "".join(full_text) + tool_line, unsafe_allow_html=True
                    )

                    result_str = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

            api_messages.append({"role": "user", "content": tool_results})
        else:
            break

    # Guardar en historial
    final_text = "".join(full_text)
    try:
        _save_historial(
            consulta     = user_query,
            respuesta    = final_text,
            tools_usadas = list({t["name"] for t in tools_used}),
            tokens       = tokens_info,
        )
    except Exception:
        pass

    return final_text, tool_boxes


# ─────────────────────────────────────────────────────────────
# Input del usuario
# ─────────────────────────────────────────────────────────────
query = st.chat_input("Tu consulta al agente trader...")

# Procesar consulta rápida del sidebar
if st.session_state.pending_query:
    query = st.session_state.pending_query
    st.session_state.pending_query = None

if query:
    if not _get_api_key():
        st.error("Falta la ANTHROPIC_API_KEY. Configúrala en .env (local) o en Streamlit Secrets (nube).")
        st.stop()

    # Mostrar mensaje del usuario
    with st.chat_message("user", avatar="🧑"):
        st.markdown(query)
    st.session_state.chat_history.append({"role": "user", "content": query})

    # Ejecutar agente
    with st.chat_message("assistant", avatar="📊"):
        response_text, tools_called = run_agent(query)

    # Guardar respuesta en historial de chat
    st.session_state.chat_history.append({
        "role":    "assistant",
        "content": response_text,
        "tools":   tools_called,
    })

    st.rerun()
