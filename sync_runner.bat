@echo off
setlocal

:: === CONFIG ===
set PYTHON_EXEC=python
set BASE_DIR=C:\your\project
set LOG_DIR=%BASE_DIR%\logs
set RUN_LOG=%LOG_DIR%\sync_runner.log

:: Ensure log directory exists
if not exist "%LOG_DIR%" (
    mkdir "%LOG_DIR%"
)

:: Timestamp for this run
set TIMESTAMP=%date% %time%
echo ============================== >> "%RUN_LOG%"
echo Started sync batch at %TIMESTAMP% >> "%RUN_LOG%"
echo ============================== >> "%RUN_LOG%"

:: === STEP 1: run_sync_and_cleanup.py ===
echo [%time%] Running run_sync_and_cleanup.py >> "%RUN_LOG%"
%PYTHON_EXEC% "%BASE_DIR%\run_sync_and_cleanup.py" >> "%LOG_DIR%\run_sync.log" 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ [%time%] run_sync_and_cleanup.py failed with exit code %ERRORLEVEL% >> "%RUN_LOG%"
) else (
    echo ✅ [%time%] run_sync_and_cleanup.py completed successfully >> "%RUN_LOG%"
)

:: === WAIT 5 minutes ===
echo Waiting 5 minutes before Shopify sync... >> "%RUN_LOG%"
timeout /t 300 /nobreak >nul

:: === STEP 2: shopify_sync.py ===
echo [%time%] Running shopify_sync.py >> "%RUN_LOG%"
%PYTHON_EXEC% "%BASE_DIR%\shopify_sync.py" >> "%LOG_DIR%\shopify_sync.log" 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ [%time%] shopify_sync.py failed with exit code %ERRORLEVEL% >> "%RUN_LOG%"
) else (
    echo ✅ [%time%] shopify_sync.py completed successfully >> "%RUN_LOG%"
)

echo Done. >> "%RUN_LOG%"
echo. >> "%RUN_LOG%"

endlocal
exit /b
