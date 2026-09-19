@echo off
setlocal
title GVN Bordro - Windows Kurulum Dosyasi Olusturucu
py -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python assets\create_icon.py
pyinstaller --noconfirm --clean --windowed --onefile --name "GVN Bordro" --icon assets\gvn_bordro.ico app.py
echo.
echo Hazir: dist\GVN Bordro.exe
pause
