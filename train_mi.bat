@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
python training.py --config mi_config.json --data data\left_hand.npz --model artifacts\mi_model.joblib
pause
