@echo off
echo Starting Market Analysis Tool...

set "ORIGINAL_DIR=%CD%"

REM Check for Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed! Please install Python 3.8 or higher.
    pause
    exit /b
)

REM Check for Node.js installation
node --version >nul 2>&1
if errorlevel 1 (
    echo Node.js is not installed! Please install Node.js 14 or higher.
    pause
    exit /b
)

REM Check and install Python requirements
echo Checking Python requirements...
pip freeze > installed_requirements.txt
fc /b requirements.txt installed_requirements.txt >nul 2>&1
if errorlevel 1 (
    echo Installing Python requirements...
    pip install -r requirements.txt
)
del installed_requirements.txt

REM Install frontend dependencies if needed
cd "%ORIGINAL_DIR%\frontend"
if not exist "node_modules" (
    echo Installing frontend dependencies...
    npm install
)

REM Start both servers
echo Starting servers...
start /min cmd /c "cd %ORIGINAL_DIR%\backend && python app.py"
start /min cmd /c "cd %ORIGINAL_DIR%\frontend && npm start"

echo Application started! Please wait for the browser to open...
echo.
echo Press Q to quit the application

:loop
choice /c Q /n /m ""
if errorlevel 1 (
    echo Stopping servers...
    taskkill /F /IM node.exe /T >nul 2>&1
    taskkill /F /IM python.exe /T >nul 2>&1
    deactivate
    exit /b
)