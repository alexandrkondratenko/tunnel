@echo off

setlocal enableextensions enabledelayedexpansion

openssl req -x509 -nodes -days 3652 -newkey rsa:4096 -sha256 -keyout tunnel.key -out tunnel.crt

endlocal
exit /b
