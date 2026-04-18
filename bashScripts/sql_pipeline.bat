del data\literature.db
@echo off
echo currently running: build_ror.bat
call bashScripts\build_ror.bat
echo build_ror.bat finished, start running build_sq.bat
call bashScripts\build_sq.bat
