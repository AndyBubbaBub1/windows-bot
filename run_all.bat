@echo off
call run_backtests.bat
start "" cmd /c run_server.bat
call run_scheduler.bat
