@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo === Martin watchlist jobs ===
py -c "from pathlib import Path; import json; d=Path('data/watchlist_jobs');
files=sorted(d.glob('*.json'));
print('none') if not files else None
for p in files:
 j=json.loads(p.read_text(encoding='utf-8'));
 print(f\"{p.stem:14} {j.get('status','?'):10} {j.get('step','?'):16} {j.get('done','')}/{j.get('total','')}\")"
echo.
echo === E_Main files ===
dir /b /o-d outputs\watchlists\Martin_Luk_*_E_Main.txt 2>nul
echo.
pause
