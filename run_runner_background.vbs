Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strScriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
strRunnerDir = strScriptDir & "\actions-runner"

If fso.FolderExists(strRunnerDir) Then
    WshShell.CurrentDirectory = strRunnerDir
    WshShell.Run "cmd.exe /c run.cmd", 0, False
    WScript.Echo "GitHub Actions Runner가 검은 창 없이 백그라운드에서 실행되었습니다!" & vbCrLf & vbCrLf & "종료를 원하실 때는 stop_runner.bat을 실행하세요."
Else
    WScript.Echo "오류: actions-runner 폴더를 찾을 수 없습니다: " & strRunnerDir
End If
