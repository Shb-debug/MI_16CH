@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
python server.py --config mi_config.json --demo
pause
