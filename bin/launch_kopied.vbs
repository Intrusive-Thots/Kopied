' Silently launch Kopied (no console). Prefer known Python312 paths, then PATH.
Option Explicit
Dim sh, fso, cmd, pythonw, pyw
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Avoid launching a second instance
If AlreadyRunning() Then WScript.Quit 0

pythonw = ResolvePythonw()
If pythonw <> "" Then
  cmd = """" & pythonw & """ ""C:\Kopied\bin\kopied.py"""
Else
  pyw = FindOnPath("pyw.exe")
  If pyw <> "" Then
    cmd = """" & pyw & """ -3 ""C:\Kopied\bin\kopied.py"""
  Else
    ' Last resort (may flash a console briefly)
    cmd = "py -3 ""C:\Kopied\bin\kopied.py"""
  End If
End If

Do
  sh.Run cmd, 0, True
  WScript.Sleep 2000
Loop


Function ResolvePythonw()
  Dim candidates(3), i, path
  candidates(0) = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe")
  candidates(1) = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe")
  candidates(2) = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe")
  candidates(3) = FindOnPath("pythonw.exe")
  For i = 0 To UBound(candidates)
    path = candidates(i)
    If path <> "" And fso.FileExists(path) Then
      ResolvePythonw = path
      Exit Function
    End If
  Next
  ResolvePythonw = ""
End Function

Function AlreadyRunning()
  Dim wmi, procs, p, cl
  On Error Resume Next
  Set wmi = GetObject("winmgmts:\\.\root\cimv2")
  Set procs = wmi.ExecQuery("SELECT CommandLine FROM Win32_Process WHERE Name='python.exe' OR Name='pythonw.exe' OR Name='py.exe' OR Name='pyw.exe'")
  For Each p In procs
    cl = LCase("" & p.CommandLine)
    If InStr(cl, "kopied.py") > 0 Then
      AlreadyRunning = True
      Exit Function
    End If
  Next
  AlreadyRunning = False
End Function

Function FindOnPath(exeName)
  Dim exec, line
  On Error Resume Next
  Set exec = sh.Exec("cmd /c where " & exeName & " 2>nul")
  Do While exec.Status = 0
    WScript.Sleep 50
  Loop
  line = Trim(exec.StdOut.ReadLine)
  If line <> "" And fso.FileExists(line) Then
    FindOnPath = line
  Else
    FindOnPath = ""
  End If
End Function
