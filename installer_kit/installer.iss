; ============================================================================
; NERKN - установщик (Inno Setup 6)
; Компиляция: скачайте Inno Setup (https://jrsoftware.org/isdl.php),
; откройте этот файл в "Inno Setup Compiler" и нажмите Build > Compile,
; либо запустите build.bat - он сделает всё автоматически (сборка exe +
; установщика одной командой).
; ============================================================================

#define MyAppName "NERKN"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "kere"
#define MyAppExeName "NERKN.exe"

[Setup]
; Тот же AppId, что и в исходном ZapretGUI - апгрейд поверх старой
; установки пройдёт как замена одного и того же продукта, а не превратится
; в две параллельные записи в "Установка и удаление программ".
AppId={{B7B9E9B0-6C1E-4D3E-9F2A-2B7B7C7A7A11}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename={#MyAppName}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Программе нужны права администратора (sc create/service, управление
; WinDivert), поэтому и сам установщик, и целевой exe их запрашивают сразу.
; У самого NERKN.exe в манифесте тоже прописан requireAdministrator
; (см. флаг --uac-admin в build.bat) - Windows спросит UAC ещё до старта
; Python, так что после установки программа открывается без ошибок и
; без двойного прыжка "обычный процесс -> сам себя перезапускает с runas".
PrivilegesRequired=admin
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные ярлыки:"

[Files]
; Сам exe (собран PyInstaller'ом в build.bat, лежит в dist\)
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; Иконка приложения (для трея и на будущее) - тот же файл, что зашит в exe
Source: "dist\app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
; Служебные папки нужны рядом с exe:
;   bin      - winws.exe и WinDivert
;   lists    - списки доменов/IP (onlyifdoesntexist - не затираем правки пользователя при апгрейде)
;   utils    - вспомогательные файлы и флаги (game_filter.enabled и т.п.)
;   zapretes - стратегии обхода (.bat)
;   proxy    - встроенный Telegram MTProto-прокси (tg-ws-proxy)
Source: "dist\bin\*";      DestDir: "{app}\bin";      Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "WinDivert64.sys,WinDivert.dll"
; Драйвер WinDivert перед копированием выгружается (см. StopBypassStack в [Code]).
; Если Windows всё же держит файл - он заменится при перезагрузке, а не сорвёт установку.
Source: "dist\bin\WinDivert64.sys"; DestDir: "{app}\bin"; Flags: ignoreversion restartreplace uninsrestartdelete skipifsourcedoesntexist
Source: "dist\bin\WinDivert.dll";   DestDir: "{app}\bin"; Flags: ignoreversion restartreplace uninsrestartdelete skipifsourcedoesntexist
Source: "dist\lists\*";    DestDir: "{app}\lists";    Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist
Source: "dist\utils\*";    DestDir: "{app}\utils";    Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "game_filter.enabled"
Source: "dist\zapretes\*"; DestDir: "{app}\zapretes"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\proxy\*";    DestDir: "{app}\proxy";    Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
; Документация (необязательна для работы программы, но пусть будет под рукой)
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
; Меню "Пуск"
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"
; Ярлык на рабочем столе (по галочке в [Tasks])
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
; Автозапуск при входе в Windows включается в самой программе:
; Настройки -> Управление -> Автозапуск (задача планировщика с правами админа).

[Code]
const
  // Ключ записи об установке (AppId + "_is1") в "Установка и удаление программ"
  UninstKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B7B9E9B0-6C1E-4D3E-9F2A-2B7B7C7A7A11}_is1';

var
  ActionPage: TInputOptionWizardPage;
  AlreadyInstalled: Boolean;
  UninstallCmd: String;
  UninstallRequested: Boolean;

// Путь к uninstaller'у уже установленной версии ('' - программа не установлена)
function FindUninstaller(): String;
var
  S: String;
begin
  Result := '';
  S := '';
  if IsWin64 and RegQueryStringValue(HKLM64, UninstKey, 'UninstallString', S) then
    Result := RemoveQuotes(S)
  else if RegQueryStringValue(HKLM32, UninstKey, 'UninstallString', S) then
    Result := RemoveQuotes(S)
  else if RegQueryStringValue(HKCU, UninstKey, 'UninstallString', S) then
    Result := RemoveQuotes(S);
end;

procedure RunHidden(const Exe, Params: String);
var
  RC: Integer;
begin
  Exec(Exe, Params, '', SW_HIDE, ewWaitUntilTerminated, RC);
end;

// Останавливает всё, что держит файлы программы: службу обхода, winws.exe,
// сам NERKN (вместе со встроенным Telegram-прокси) и драйвер WinDivert,
// который блокирует WinDivert64.sys. Без этого апгрейд падает с "файл занят".
procedure StopBypassStack();
var
  I: Integer;
begin
  RunHidden('sc.exe', 'stop zapret');
  RunHidden('taskkill.exe', '/IM winws.exe /F /T');
  RunHidden('taskkill.exe', '/IM "{#MyAppExeName}" /F /T');
  RunHidden('taskkill.exe', '/IM ZapretGUI.exe /F /T');
  // Драйвер выгружается не мгновенно - повторяем несколько раз
  for I := 1 to 4 do
  begin
    RunHidden('taskkill.exe', '/IM winws.exe /F /T');
    RunHidden('sc.exe', 'stop WinDivert');
    RunHidden('sc.exe', 'stop WinDivert14');
    RunHidden('sc.exe', 'delete WinDivert');
    RunHidden('sc.exe', 'delete WinDivert14');
    Sleep(600);
  end;
end;

// Вызывается после нажатия "Установить", прямо перед копированием файлов
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopBypassStack();
  Result := '';
end;

// Если старая версия программы уже запущена во время апгрейда - Windows
// не даст перезаписать её exe ("файл занят"), из-за чего после установки
// на диске мог оказаться наполовину заменённый файл, который потом
// открывается с ошибкой. Поэтому перед копированием файлов принудительно
// закрываем прежний процесс.
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/IM "{#MyAppExeName}" /F', '', SW_HIDE,
       ewWaitUntilTerminated, ResultCode);
  UninstallCmd := FindUninstaller();
  AlreadyInstalled := (UninstallCmd <> '') and FileExists(UninstallCmd);
  Result := True;
end;

// При повторном запуске установщика первым шагом спрашиваем:
// обновить программу или удалить её.
procedure InitializeWizard();
begin
  ActionPage := CreateInputOptionPage(wpWelcome,
    '{#MyAppName} уже установлен',
    'Выберите действие',
    'На этом компьютере уже есть установленная версия. Что сделать?',
    True, False);
  ActionPage.Add('Обновить: установить новую версию поверх (настройки, тема и список доменов сохранятся)');
  ActionPage.Add('Удалить: полностью убрать программу с компьютера');
  ActionPage.SelectedValueIndex := 0;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = ActionPage.ID) and (not AlreadyInstalled);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  if (CurPageID = ActionPage.ID) and (ActionPage.SelectedValueIndex = 1) then
  begin
    // "Удалить": запускаем штатный деинсталлятор и закрываем установщик
    Result := False;
    UninstallRequested := True;
    if Exec(UninstallCmd, '', '', SW_SHOWNORMAL, ewNoWait, ResultCode) then
      WizardForm.Close
    else
    begin
      UninstallRequested := False;
      MsgBox('Не удалось запустить удаление. Удалите программу через "Параметры - Приложения".',
             mbError, MB_OK);
    end;
  end;
end;

// Закрытие установщика после запуска деинсталлятора - без вопроса "Прервать установку?"
procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  if UninstallRequested then
    Confirm := False;
end;

[InstallDelete]
; Старый ярлык автозагрузки от прошлых версий (он не работал с правами админа)
Type: files; Name: "{userstartup}\{#MyAppName}.lnk"

[Run]
; Удаляем возможную старую службу перед установкой новой версии
Filename: "sc.exe"; Parameters: "stop zapret"; Flags: runhidden; StatusMsg: "Останавливаем предыдущую версию службы..."
Filename: "sc.exe"; Parameters: "delete zapret"; Flags: runhidden

[UninstallRun]
Filename: "schtasks.exe"; Parameters: "/Delete /TN ""NERKN_Autostart"" /F"; Flags: runhidden
Filename: "taskkill.exe"; Parameters: "/IM winws.exe /F /T"; Flags: runhidden
Filename: "taskkill.exe"; Parameters: "/IM ""{#MyAppExeName}"" /F /T"; Flags: runhidden
; При удалении программы аккуратно снимаем службу и WinDivert
Filename: "sc.exe"; Parameters: "stop zapret"; Flags: runhidden
Filename: "sc.exe"; Parameters: "delete zapret"; Flags: runhidden
Filename: "sc.exe"; Parameters: "stop WinDivert"; Flags: runhidden
Filename: "sc.exe"; Parameters: "delete WinDivert"; Flags: runhidden
Filename: "sc.exe"; Parameters: "stop WinDivert14"; Flags: runhidden
Filename: "sc.exe"; Parameters: "delete WinDivert14"; Flags: runhidden

[UninstallDelete]
; Конфиг пользователя (APPDATA\zapret-gui) по умолчанию НЕ трогаем,
; чтобы настройки/список доменов пережили переустановку.
; Если нужно чистить полностью - раскомментируйте строку ниже.
; Type: filesandordirs; Name: "{userappdata}\zapret-gui"
