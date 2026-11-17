@echo off
cd /d %~dp0
python training.py --config mi_config.json --collect --trials-per-class 40 --data data\left_hand.npz
pause
