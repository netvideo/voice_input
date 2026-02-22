@echo off
chcp 65001 >nul
title ASR语音输入测试工具
cls

echo ========================================
echo    ASR语音输入测试工具
echo ========================================
echo.
echo  1. 启动服务端测试程序
echo  2. 测试客户端连接
echo  3. 使用麦克风测试
echo  4. 退出
echo.
echo ========================================

set /p choice=请选择 (1-4): 

if "%choice%"=="1" goto server
if "%choice%"=="2" goto client
if "%choice%"=="3" goto mic
if "%choice%"=="4" goto end

echo 无效选择，请重新运行
goto end

:server
echo.
echo 正在启动服务端测试程序...
echo 默认端口: 8765
echo 模式: random (返回随机文本)
echo.
python asr_server_test.py --port 8765 --mode random
goto end

:client
echo.
echo 正在测试客户端连接...
echo 目标: ws://localhost:8765
echo.
python asr_client_test.py --url ws://localhost:8765
goto end

:mic
echo.
echo 正在启动麦克风测试...
echo 请确保麦克风已连接，对着麦克风说话
echo.
python asr_client_test.py --url ws://localhost:8765 --mic --duration 5
goto end

:end
echo.
echo 按任意键退出...
pause >nul
