@echo off
chcp 65001 > nul

:: Check for Administrator privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [안내] 관리자 권한이 필요합니다. 관리자 권한으로 다시 실행합니다...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"%~f0\"' -Verb RunAs"
    exit /b
)

echo ========================================================
echo  기존 GitHub Actions 윈도우 서비스(NETWORK SERVICE) 제거
echo ========================================================
echo.

net stop actions.runner.apr-04-checkMileageSeat.LAPHROAIG 2>nul
sc.exe delete actions.runner.apr-04-checkMileageSeat.LAPHROAIG 2>nul

echo.
echo [성공] 기존 서비스가 완전히 중지 및 삭제되었습니다!
echo 이제 권한 에러(EPERM)를 유발하던 서비스가 제거되었습니다.
echo.
echo 앞으로는 run_runner_background.vbs 를 더블 클릭하여
echo 사용자 계정(aumie) 권한으로 백그라운드 러너를 구동하시면 됩니다.
echo ========================================================
echo.
pause
