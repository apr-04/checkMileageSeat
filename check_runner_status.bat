@echo off
chcp 65001 > nul
echo ========================================================
echo  GitHub Actions Runner 프로세스 실행 상태 확인
echo ========================================================
echo.
tasklist /fi "imagename eq Runner.Listener.exe" | findstr /i "Runner.Listener.exe" > nul
if %ERRORLEVEL% EQU 0 (
    echo  상태: [실행 중] 러너가 백그라운드에서 정상 대기 중입니다!
) else (
    echo  상태: [미실행] 현재 실행 중인 러너 프로세스가 없습니다.
)
echo.
pause
