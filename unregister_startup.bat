@echo off
chcp 65001 > nul
set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\KAL_Seat_Runner.lnk"

echo ========================================================
echo   대한항공 좌석 모니터링 러너 - 윈도우 시작프로그램 해제
echo ========================================================
echo.

if exist "%SHORTCUT%" (
    del "%SHORTCUT%"
    echo [완료] 윈도우 시작프로그램에서 성공적으로 제거되었습니다.
) else (
    echo 시작프로그램에 등록된 KAL_Seat_Runner 바로가기가 없습니다.
)

echo.
pause
