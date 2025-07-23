@echo off
setlocal

:: === CONFIG ===
set BASE_DIR=%~dp0
set LOG_DIR=%BASE_DIR%logs
set PYTHON_EXEC=python

:: Ensure logs directory exists
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:: Timestamp for log entry
set timestamp=%date% %time%

:: Start log
echo =============================== >> "%LOG_DIR%\\sync_runner.log"
echo Started sync at %timestamp% >> "%LOG_DIR%\\sync_runner.log"
echo =============================== >> "%LOG_DIR%\\sync_runner.log"

echo Running run_sync_and_cleanup.py...
echo [%time%] Running run_sync_and_cleanup.py >> "%LOG_DIR%\\sync_runner.log"
%PYTHON_EXEC% "%BASE_DIR%run_sync_and_cleanup.py" >> "%LOG_DIR%\\combined_sync_output.log" 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ run_sync_and_cleanup.py failed with exit code %ERRORLEVEL% >> "%LOG_DIR%\\sync_runner.log"
) else (
    echo ✅ run_sync_and_cleanup.py completed successfully >> "%LOG_DIR%\\sync_runner.log"
)

:: Pause before next task
echo Waiting 5 minutes before shopify_sync.py...
echo [%time%] Waiting 5 minutes before shopify_sync.py >> "%LOG_DIR%\\sync_runner.log"
timeout /t 300 /nobreak

:: Run shopify_sync.py
echo Running shopify_sync.py...
echo [%time%] Running shopify_sync.py >> "%LOG_DIR%\\sync_runner.log"
%PYTHON_EXEC% "%BASE_DIR%shopify_sync.py" >> "%LOG_DIR%\\shopify_sync_output.log" 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ shopify_sync.py failed with exit code %ERRORLEVEL% >> "%LOG_DIR%\\sync_runner.log"
) else (
    echo ✅ shopify_sync.py completed successfully >> "%LOG_DIR%\\sync_runner.log"
)

:: Done
echo Completed sync at %time% >> "%LOG_DIR%\\sync_runner.log"
echo. >> "%LOG_DIR%\\sync_runner.log"

echo All tasks complete. Check logs in %LOG_DIR%
pause
endlocal
