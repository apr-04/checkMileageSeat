Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strScriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
strRunnerDir = strScriptDir & "\actions-runner"

If fso.FolderExists(strRunnerDir) Then
    WshShell.CurrentDirectory = strRunnerDir
    WshShell.Run "cmd.exe /c run.cmd", 0, False
Else
    WScript.Echo "오류: actions-runner 폴더를 찾을 수 없습니다: " & strRunnerDir
End If
