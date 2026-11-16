@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\AutoClipper.lnk');$s.TargetPath='%~dp0AutoClipper.bat';$s.WorkingDirectory='%~dp0';$s.WindowStyle=1;$s.IconLocation='imageres.dll,18';$s.Save()"
echo A desktop shortcut called AutoClipper was created.
pause
