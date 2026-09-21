' Install Kopied into the current user's Startup folder
' Installs TWO shortcuts: the clipboard service and the GUI viewer server
Option Explicit
Dim sh, startup, sc

Set sh = CreateObject("WScript.Shell")
startup = sh.SpecialFolders("Startup")

' 1. Clipboard service shortcut
Set sc = sh.CreateShortcut(startup & "\Kopied.lnk")
sc.TargetPath = "wscript.exe"
sc.Arguments = "C:\Kopied\bin\launch_kopied.vbs"
sc.WorkingDirectory = "C:\Kopied"
sc.WindowStyle = 7
sc.Description = "Kopied clipboard and screenshot persistence service"
sc.Save
WScript.Echo "Installed: " & startup & "\Kopied.lnk"

' 2. GUI viewer server shortcut
Set sc = sh.CreateShortcut(startup & "\Kopied GUI.lnk")
sc.TargetPath = "wscript.exe"
sc.Arguments = "C:\Kopied\bin\launch_gui_silent.vbs"
sc.WorkingDirectory = "C:\Kopied"
sc.WindowStyle = 7
sc.Description = "Kopied Archive GUI Viewer server"
sc.Save
WScript.Echo "Installed: " & startup & "\Kopied GUI.lnk"
