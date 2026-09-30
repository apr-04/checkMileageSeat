@echo off
chcp 65001 > nul
echo ========================================================
echo  GitHub Actions Runner 백그라운드 프로세스 종료
echo ========================================================
echo.
taskkill /f /im Runner.Listener.exe /im Runner.Worker.exe 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [성공] 백그라운드 러너가 정상적으로 종료되었습니다.
) else (
    echo [알림] 현재 실행 중인 러너 프로세스가 없습니다.
)
echo.
pause
