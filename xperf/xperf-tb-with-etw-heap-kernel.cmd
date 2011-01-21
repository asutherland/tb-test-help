@echo off
set session=mytrace
if not @%1@ == @@ set session=%1

xperf -on Latency -f %session%kernel.etl -BufferSize 1024 -MinBuffers 128 -MaxBuffers 256 -start %session%js -on MozillaSpiderMonkey -f %session%js.etl -BufferSize 1024 -MinBuffers 128 -MaxBuffers 256 -start %session%heap -heap -PidNewProcess "c:\rev_control\hg\comm-central\objdir-thunderbird-probes\mozilla\dist\bin\thunderbird.exe" -f %session%heap.etl -BufferSize 1024 -MinBuffers 128 -MaxBuffers 256
 
if not errorlevel 0 goto :eof
 
echo.
echo Performance Trace started. 
echo.
echo When done with profile actions, 
 
pause 
 
echo.
xperf -stop %session%heap
if not errorlevel 0 goto :eof
xperf -stop %session%js
if not errorlevel 0 goto :eof
xperf -stop
if not errorlevel 0 goto :eof
 
xperf -merge %session%js.etl %session%heap.etl %session%kernel.etl %session%combined.etl
if not errorlevel 0 goto :eof
