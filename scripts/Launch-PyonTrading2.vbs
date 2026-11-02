Option Explicit

Const APP_URL = "http://127.0.0.1:8765"
Const WAIT_SECONDS = 20

Dim shell, fso, projectRoot, launcher, startedAt
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
projectRoot = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
launcher = projectRoot & "\Start-PyonTrading2.bat"

If Not fso.FileExists(launcher) Then
  MsgBox "PyonTrading 2 could not find its launcher." & vbCrLf & projectRoot, vbCritical, "PyonTrading 2"
  WScript.Quit 1
End If

If Not IsHealthy() Then
  shell.Run "cmd.exe /d /c call " & Quote(launcher) & " --no-browser", 0, False
  startedAt = Timer
  Do While Not IsHealthy() And ElapsedSeconds(startedAt) < WAIT_SECONDS
    WScript.Sleep 500
  Loop
End If

If IsHealthy() Then
  shell.Run APP_URL, 1, False
Else
  MsgBox "PyonTrading 2 did not start within " & WAIT_SECONDS & " seconds." & vbCrLf & _
    "Open the project folder and run setup.bat if this is the first launch.", vbExclamation, "PyonTrading 2"
End If

Function IsHealthy()
  Dim request
  On Error Resume Next
  Set request = CreateObject("WinHttp.WinHttpRequest.5.1")
  request.SetTimeouts 500, 500, 500, 500
  request.Open "GET", APP_URL & "/api/health", False
  request.Send
  IsHealthy = (Err.Number = 0 And request.Status = 200)
  Err.Clear
  On Error GoTo 0
End Function

Function ElapsedSeconds(started)
  ElapsedSeconds = Timer - started
  If ElapsedSeconds < 0 Then ElapsedSeconds = ElapsedSeconds + 86400
End Function

Function Quote(value)
  Quote = Chr(34) & value & Chr(34)
End Function
