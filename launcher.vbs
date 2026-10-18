Option Explicit
Dim shell, fso, scriptDir, pathText, parts, part, candidate
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = scriptDir

pathText = shell.ExpandEnvironmentStrings("%PATH%")
parts = Split(pathText, ";")
For Each part In parts
    part = Trim(part)
    If Len(part) > 0 Then
        candidate = part & "\pythonw.exe"
        If fso.FileExists(candidate) Then
            shell.Run Chr(34) & candidate & Chr(34) & " -m app.bootstrap", 0, False
            WScript.Quit 0
        End If
    End If
Next

If fso.FileExists(scriptDir & "\.venv\Scripts\pythonw.exe") Then
    shell.Run Chr(34) & scriptDir & "\.venv\Scripts\pythonw.exe" & Chr(34) & " -m app.bootstrap", 0, False
    WScript.Quit 0
End If

For Each part In parts
    part = Trim(part)
    If Len(part) > 0 Then
        candidate = part & "\python.exe"
        If fso.FileExists(candidate) Then
            shell.Run Chr(34) & candidate & Chr(34) & " -m app.bootstrap", 0, False
            WScript.Quit 0
        End If
    End If
Next

MsgBox "Python 3.11 ou superior não foi encontrado. Instale o Python e execute novamente.", 16, "ChatGPT Media Downloader"
