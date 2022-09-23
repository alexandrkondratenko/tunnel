@echo off

setlocal enableextensions enabledelayedexpansion

set COMMAND=tunnel.py client my.server.com 12345
wmic process where "commandline like '%%%COMMAND%%%' and not commandline like '%%wmic%%'" call terminate > nul 2>&1
python %COMMAND% --forward 3389 >> tunnel.log 2>&1

endlocal
exit /b
