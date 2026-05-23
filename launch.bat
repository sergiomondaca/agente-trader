@echo off
cd /d "%~dp0"
echo Iniciando Agente Trader en http://localhost:8501
streamlit run app_web.py
pause
