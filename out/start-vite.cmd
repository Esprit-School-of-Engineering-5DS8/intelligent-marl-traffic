@echo off
cd /d "C:\Users\Hazem\Desktop\KEMETRA\frontend"
call npm.cmd run dev > ..\out\vite.stdout.log 2> ..\out\vite.stderr.log
