@echo off
setlocal DisableDelayedExpansion
rem Windows CMD launcher: no PowerShell execution-policy changes or optional installs.
set "IT3D_READ_ONLY="
for %%A in (%*) do if /I "%%~A"=="--check-only" set "IT3D_READ_ONLY=1"
call :find_python
if not errorlevel 1 goto run
if defined IMAGE_TO_3D_PYTHON (
  echo IMAGE_TO_3D_PYTHON must point to Python 3.10+.
  exit /b 2
)
if defined IT3D_READ_ONLY (
  echo Python 3.10+ missing. Check-only made no changes.
  exit /b 2
)
where winget >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ and winget unavailable. Nothing installed.
  echo Install Python from https://www.python.org/downloads/windows/ and rerun.
  exit /b 2
)
echo Python 3.10+ missing. Proposed command:
echo winget install --id Python.Python.3.13 --exact --source winget --scope user
echo The per-user Python installer may update Python registration, launcher and user PATH.
echo Review any installer or license prompts yourself. No optional tools will be installed.
choice /C YN /N /M "Install Python? [Y/N]: "
if errorlevel 2 (
  echo Cancelled. Nothing installed.
  exit /b 2
)
winget install --id Python.Python.3.13 --exact --source winget --scope user
if errorlevel 1 (
  echo Python installation failed. No automatic retry or elevation.
  exit /b 2
)
call :find_python
if errorlevel 1 (
  echo New Python not detected. Open a new terminal or set IMAGE_TO_3D_PYTHON to python.exe.
  exit /b 2
)
:run
if "%IT3D_MODE%"=="py" (
  py -3 -B -X utf8 "%~dp0scripts\setup_skill.py" %*
) else (
  "%IT3D_PYTHON%" -B -X utf8 "%~dp0scripts\setup_skill.py" %*
)
set "IT3D_RESULT=%ERRORLEVEL%"
exit /b %IT3D_RESULT%

:find_python
set "IT3D_MODE="
set "IT3D_PYTHON="
if defined IMAGE_TO_3D_PYTHON (
  "%IMAGE_TO_3D_PYTHON%" -B -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>nul
  if errorlevel 1 exit /b 1
  set "IT3D_PYTHON=%IMAGE_TO_3D_PYTHON%"
  exit /b 0
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -B -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>nul
  if not errorlevel 1 (
    set "IT3D_MODE=py"
    exit /b 0
  )
)
for %%P in (python python3) do (
  where %%P >nul 2>nul
  if not errorlevel 1 (
    %%P -B -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>nul
    if not errorlevel 1 (
      set "IT3D_PYTHON=%%P"
      exit /b 0
    )
  )
)
for %%P in ("%LocalAppData%\Programs\Python\Python313\python.exe" "%ProgramFiles%\Python313\python.exe") do (
  if exist "%%~P" (
    "%%~P" -B -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>nul
    if not errorlevel 1 (
      set "IT3D_PYTHON=%%~P"
      exit /b 0
    )
  )
)
exit /b 1
