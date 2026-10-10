' Hidden launcher: starts the map with no console window, logging to logs\map-server.log
'
' Same arguments as Start Map.bat ("--live" for real-time mode, "--lan" to serve the
' network, ...), because it just hands them to that script. The console is hidden by
' window style 0; because of that the server exits on its own once the page is closed
' (see the watchdog in server\index.js), so nothing is left running invisibly.
'
' Use "Start Map.bat" instead when you want to SEE the log or a startup error.

Option Explicit
Dim sh, fso, here, logs, bat, log, cmd, i, extra
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
bat = fso.BuildPath(here, "Start Map.bat")
If Not fso.FileExists(bat) Then
  MsgBox "Start Map.bat not found next to this launcher." & vbCrLf & _
         "\u627e\u4e0d\u5230 Start Map.bat\u3002", 16, "Elden Ring Map"
  WScript.Quit 1
End If
logs = fso.BuildPath(here, "logs")
If Not fso.FolderExists(logs) Then fso.CreateFolder(logs) 
log = fso.BuildPath(logs, "map-server.log")
extra = ""
For i = 0 To WScript.Arguments.Count - 1
  extra = extra & " " & WScript.Arguments(i)
Next
sh.CurrentDirectory = here
cmd = "cmd /c """"" & bat & """ " & extra & " > """ & log & """ 2>&1 < nul"""
sh.Run cmd, 0, False
