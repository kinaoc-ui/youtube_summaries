@echo off
setlocal EnableExtensions
cd /d "%~dp0"
py -m pip install -q -r requirements-streamlit.txt
py -m streamlit run streamlit_app.py --server.headless true --server.port 8502
