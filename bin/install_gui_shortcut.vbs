' Install Kopied Viewer Desktop Shortcut
Option Explicit
Dim sh, sc, desktop, linkPath
Set sh = CreateObject("WScript.Shell")
desktop = sh.SpecialFolders("Desktop")
linkPath = desktop & "\Kopied Viewer.lnk"

Set sc = sh.CreateShortcut(linkPath)
sc.TargetPath = "wscript.exe"
sc.Arguments = "C:\Kopied\bin\launch_gui_silent.vbs"
sc.WorkingDirectory = "C:\Kopied"
sc.WindowStyle = 7
sc.Description = "Kopied Clipboard and Screenshot GUI Viewer"
sc.Save

WScript.Echo "Installed shortcut: " & linkPath
