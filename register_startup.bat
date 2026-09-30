@echo off
chcp 65001 > nul
set "SCRIPT_DIR=%~dp0"
set "TARGET=%SCRIPT_DIR%run_runner_background.vbs"
set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\KAL_Seat_Runner.lnk"

echo ========================================================
echo   대한항공 좌석 모니터링 러너 - 윈도우 시작프로그램 등록
echo ========================================================
echo.

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%TARGET%\"'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Save()"

if exist "%SHORTCUT%" (
    echo [성공] 윈도우 시작프로그램에 등록되었습니다!
    echo 이제 컴퓨터를 켜면 Antigravity 없이도 백그라운드에서 자동으로 러너가 실행됩니다.
    echo.
    echo * 등록 해제를 원하실 때는 unregister_startup.bat 을 실행하세요.
) else (
    echo [오류] 바로가기 생성에 실패했습니다.
)

echo.
pause
