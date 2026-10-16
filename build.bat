@echo off
REM ============================================================
REM  Kaguya_dat_Tool —— 一键打包脚本（build.bat）
REM
REM  作用：把本仓库源码打包成 dist\ 文件夹里的三个 exe：
REM        KaguyaEngine_Patch.exe  （启动器）
REM        KaguyaPatch.exe         （图形界面）
REM        KaguyaPatchCLI.exe      （命令行）
REM
REM  用法：双击本文件即可。首次运行会自己建虚拟环境并安装 PyInstaller，
REM        之后只要双击就行，几秒搞定。
REM
REM  前提：电脑已装 Python 3.11（含 tcl/tk）。没装运行会提示你，
REM        去 https://www.python.org/downloads/ 装，安装时务必勾选：
REM          “Add python.exe to PATH”  和  “tcl/tk and IDLE”。
REM ============================================================

cd /d "%~dp0"

REM --- 第 1 步：确认 Python 已安装 ---
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo [失败] 没有找到 Python。请先安装 Python 3.11，并务必勾选：
    echo        1. Add python.exe to PATH
    echo        2. tcl/tk and IDLE   —— 点 Customize installation 就能看到
    echo    下载地址：https://www.python.org/downloads/
    echo.
    pause
    goto :eof
)

REM --- 第 2 步：建虚拟环境（只有第一次会真正创建）---
if not exist venv (
    echo [1/4] 首次运行：创建虚拟环境 venv ...
    python -m venv venv
) else (
    echo [1/4] 已经存在 venv，跳过创建。
)

REM --- 第 3 步：激活 venv 并安装打包依赖 ---
echo [2/4] 安装打包依赖 PyInstaller ...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>nul
pip install pyinstaller

REM --- 第 4 步：确认 tkinter 可用（图形界面打包必须有它）---
python -c "import tkinter" >nul 2>nul
if errorlevel 1 (
    echo.
    echo [失败] 当前 Python 没有带 tcl/tk，打包会失败。
    echo        请重装 Python 时勾选 “tcl/tk and IDLE”，再双击本脚本。
    echo.
    pause
    goto :eof
)

REM --- 第 5 步：正式打包 ---
echo [3/4] 开始打包（首次稍慢，请耐心等待）...
python build.py

echo.
echo [4/4] 完成！三个 exe 已经生成在 dist\ 文件夹里：
echo        KaguyaEngine_Patch.exe
echo        KaguyaPatch.exe
echo        KaguyaPatchCLI.exe
echo.
echo 按任意键关闭本窗口。
pause >nul
