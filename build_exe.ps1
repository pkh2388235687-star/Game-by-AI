# 特工67 一键打包脚本
# 用法：在项目根目录执行  .\build_exe.ps1
# 依赖：pip install pyinstaller
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host ">>> 清理旧产物..."
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
Remove-Item -Force "特工67.spec" -ErrorAction SilentlyContinue

Write-Host ">>> 使用 PyInstaller 打包为单文件 exe..."
pyinstaller `
  --noconfirm `
  --onefile `
  --windowed `
  --name "特工67" `
  --icon "icon.ico" `
  --add-data "game_assets;game_assets" `
  launcher.py

Write-Host ">>> 完成：dist\特工67.exe"
