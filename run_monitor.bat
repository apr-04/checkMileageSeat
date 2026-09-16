@echo off
chcp 65001 > nul
echo ========================================================
echo  대한항공 마일리지 빈좌석 자동 감시 백그라운드 서비스
echo ========================================================
echo.
echo 설정 파일(config.json)에 등록된 노선들을 주기적으로 감시합니다.
echo 중단하려면 Ctrl+C 를 누르세요.
echo.

python src\monitor.py
pause
