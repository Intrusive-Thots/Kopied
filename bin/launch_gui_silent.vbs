' Silently launch Kopied GUI Server with crash restart loop and duplicate detection
Option Explicit
Dim sh, fso, cmd

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Avoid launching a second instance
If AlreadyRunning() Then WScript.Quit 0

cmd = "py -3 ""C:\Kopied\bin\kopied_gui.py"" --no-browser"

Do
  sh.Run cmd, 0, True
  ' If we get here, the server exited — wait before restarting
  WScript.Sleep 3000
  ' Re-check if another instance started while we were sleeping
  If AlreadyRunning() Then WScript.Quit 0
Loop

Function AlreadyRunning()
  Dim wmi, procs, p, cl
  On Error Resume Next
  Set wmi = GetObject("winmgmts:\\.\root\cimv2")
  Set procs = wmi.ExecQuery("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name='python.exe' OR Name='pythonw.exe' OR Name='py.exe' OR Name='pyw.exe'")
  For Each p In procs
    cl = LCase("" & p.CommandLine)
    If InStr(cl, "kopied_gui.py") > 0 Then
      AlreadyRunning = True
      Exit Function
    End If
  Next
  AlreadyRunning = False
End Function
