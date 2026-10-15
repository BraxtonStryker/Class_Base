@echo off
REM Build one course:  build.bat ml-hasan   (a folder name under courses\)
REM Extra options pass through, e.g.  build.bat ml-hasan --check
if "%~1"=="" (
  echo Usage: build.bat COURSE_FOLDER_NAME [options]
  exit /b 1
)
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% "%~dp0build.py" "%~dp0courses\%~1" %2 %3 %4 %5
if errorlevel 1 (
  echo.
  echo Build failed. If a module is missing, run:  %PY% -m pip install -r "%~dp0requirements.txt"
  pause
  exit /b 1
)
echo.
echo Opening the output folder...
start "" "%~dp0dist\%~1"
