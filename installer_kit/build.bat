@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo NERKN - sborka exe + ustanovshika
echo ============================================================
echo.

rem --- 0. Proverka nalichiya neobhodimyh papok ---
if not exist "..\main.py" (
    echo [ERROR] Ne naiden ..\main.py. Polozhite installer_kit ryadom s main.py.
    pause
    exit /b 1
)
if not exist "..\bin\winws.exe" (
    echo [ERROR] Ne naiden ..\bin\winws.exe.
    pause
    exit /b 1
)
if not exist "..\proxy\tg_ws_proxy.py" (
    echo [WARNING] Ne naidena papka ..\proxy - vkladka "Telegram proksi"
    echo           v sobrannoy programme rabotat ne budet.
    echo.
)

rem --- 1. Ustanovka zavisimostey ---
echo [1/5] Ustanavlivaem zavisimosti...
set "PYTHON=python"
if exist "..\.venv\Scripts\python.exe" set "PYTHON=..\.venv\Scripts\python.exe"
"%PYTHON%" -m pip install -r "..\requirements-build.txt"
if errorlevel 1 (
    echo [ERROR] Oshibka pri ustanovke pip.
    pause
    exit /b 1
)

rem --- 1.5 Generatsiya app_icon.ico, esli ego eshe net ---
if not exist "app_icon.ico" (
    echo [INFO] Generiruem app_icon.ico ^(make_icon.py^)...
    "%PYTHON%" make_icon.py
    if errorlevel 1 (
        echo [WARNING] Ne udalos sgenerirovat ikonku - sborka prodolzhitsya bez nee.
    )
)

rem --- 1.6 Sozdanie korrektnogo version_info.txt ---
if not exist "version_info.txt" (
    echo [INFO] Sozdaem version_info.txt...
    (
        echo VSVersionInfo^(
        echo   ffi=FixedFileInfo^(
        echo     filevers=^(1, 0, 0, 0^),
        echo     prodvers=^(1, 0, 0, 0^),
        echo     mask=0x3f,
        echo     flags=0x0,
        echo     OS=0x40004,
        echo     fileType=0x1,
        echo     subtype=0x0,
        echo     date=^(0, 0^)
        echo   ^),
        echo   kids=[
        echo     StringFileInfo^(
        echo       [
        echo         StringTable^(
        echo           '040904B0',
        echo           [StringStruct^('CompanyName', 'NERKN'^),
        echo            StringStruct^('FileDescription', 'NERKN - obhod blokirovok'^),
        echo            StringStruct^('FileVersion', '1.0.0.0'^),
        echo            StringStruct^('InternalName', 'NERKN'^),
        echo            StringStruct^('LegalCopyright', 'Copyright 2026'^),
        echo            StringStruct^('OriginalFilename', 'NERKN.exe'^),
        echo            StringStruct^('ProductName', 'NERKN'^),
        echo            StringStruct^('ProductVersion', '1.0.0.0'^)]^)
        echo       ]
        echo     ^),
        echo     VarFileInfo^([VarStruct^('Translation', [1033, 1200]^)^]^)
        echo   ]
        echo ^)
    ) > version_info.txt
)

rem --- 2. Sborka PyInstaller ---
echo.
echo [2/5] Sborka NERKN.exe...

set "ICON_FLAG="
if exist "app_icon.ico" set ICON_FLAG=--icon=app_icon.ico
set "VER_FLAG="
if exist "version_info.txt" set VER_FLAG=--version-file=version_info.txt
set "DATA_FLAG="
if exist "app_icon.ico" set DATA_FLAG=--add-data=app_icon.ico;.

rem --uac-admin vshivaet v manifest .exe trebovanie prav administratora,
rem  tak chto Windows sprosit UAC SRAZU pri zapuske (do starta Python),
rem  eshe do togo, kak zaprosit ih sam main.py cherez ShellExecute "runas".
rem --collect-all nuzhen dlya proxy/ (cryptography ispolzuet rust/cffi-backend,
rem  a certifi taskaet svoi dannye - PyInstaller ne vsegda nahodit ih sam).
"%PYTHON%" -m PyInstaller --noconfirm --clean --noconsole --onefile --uac-admin ^
    --name "NERKN" %ICON_FLAG% %VER_FLAG% %DATA_FLAG% ^
    --collect-all cryptography --collect-all certifi ^
    "..\main.py"

if errorlevel 1 (
    echo [ERROR] Oshibka PyInstaller.
    pause
    exit /b 1
)

if not exist "dist\NERKN.exe" (
    echo [ERROR] dist\NERKN.exe ne sozdan.
    pause
    exit /b 1
)

rem --- 3. Kopirovanie papok ryadom s exe ---
echo.
echo [3/5] Kopirovanie fajlov v dist...
if exist "..\bin"      xcopy /e /i /y "..\bin"      "dist\bin\"      >nul
if exist "..\lists"    xcopy /e /i /y "..\lists"    "dist\lists\"    >nul
if exist "..\utils"    xcopy /e /i /y "..\utils"    "dist\utils\"    >nul
if exist "..\zapretes" xcopy /e /i /y "..\zapretes" "dist\zapretes\" >nul
if exist "..\proxy"    xcopy /e /i /y "..\proxy"    "dist\proxy\"    >nul
if exist "app_icon.ico" copy /y "app_icon.ico" "dist\app_icon.ico" >nul
echo Gotovo!

rem --- 4. Proverka sostava dist ---
echo.
echo [4/5] Proverka sostava dist...
for %%D in (bin lists utils zapretes proxy) do (
    if not exist "dist\%%D" echo [WARNING] dist\%%D otsutstvuet - eta chast programmy rabotat ne budet.
)
if not exist "dist\bin\winws.exe" echo [WARNING] dist\bin\winws.exe otsutstvuet!
if not exist "dist\proxy\tg_ws_proxy.py" echo [WARNING] dist\proxy\tg_ws_proxy.py otsutstvuet - Telegram-proksi rabotat ne budet!

rem --- 5. Sborka Inno Setup ---
echo.
echo [5/5] Sborka ustanovshika (Inno Setup)...

set ISCC=
for %%P in (
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles%\Inno Setup 6\ISCC.exe"
    "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
) do (
    if exist %%P set ISCC=%%~P
)

if "%ISCC%"=="" (
    echo [PROPUSK] ISCC.exe ne naiden.
    echo Esli Inno Setup ustanovlen, ukazhite put k ISCC.exe v skripte vruchnuyu
    echo ^(peremennaya ISCC v etom fajle^).
) else (
    "%ISCC%" installer.iss
    if errorlevel 1 (
        echo [ERROR] Oshibka Inno Setup.
        pause
        exit /b 1
    )
    echo Gotovo: Output\NERKN-Setup.exe
)

echo.
echo ============================================================
echo Sborka zavershena.
echo ============================================================
pause
