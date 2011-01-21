@echo off
set session=mytrace
if not @%1@ == @@ set session=%1

xperf -start %session%js -on MozillaSpiderMonkey -f %session%js.etl -BufferSize 1024 -MinBuffers 128 -MaxBuffers 1024
 
if not errorlevel 0 goto :eof
 
echo.
echo Performance Trace started. 
echo.
echo When done with profile actions, 
 
pause 
 
echo.
xperf -stop %session%js
if not errorlevel 0 goto :eof
