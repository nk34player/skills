@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars32.bat" >nul 2>&1
cl /O2 /EHsc /nologo dbq.cpp /Fe:dbq.exe
cl /O2 /EHsc /nologo dbdump.cpp odbc32.lib /Fe:dbdump.exe

rem fallback: dbq.cpp is plain C++ (no ODBC), so MinGW g++ works too
if not exist dbq.exe g++ -O2 -std=c++17 -o dbq.exe dbq.cpp
