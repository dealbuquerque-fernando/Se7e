; Inno Setup script for Se7e.
; Build the PyInstaller onedir output first (packaging/se7e.spec -> dist/Se7e),
; then compile this with ISCC.exe.

#define MyAppName "Se7e"
#define MyAppVersion "1.1.1"
#define MyAppExeName "Se7e.exe"
; Must match the string passed to SetCurrentProcessExplicitAppUserModelID
; in se7e/app.py exactly — without a shortcut carrying the same
; AppUserModelID, Explorer can't find a match for the process's group on
; the first window it ever shows, and falls back to a provisional/generic
; taskbar icon for about a second before resolving it.
#define MyAppUserModelID "Se7eQt.TrayApp"

[Setup]
AppId={{B6A2C6C2-6D6C-4C7C-9B7A-2B7F7C1E7E7E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
; Per-user install, no admin prompt — matches the app's own registry
; autostart, which already only ever touches HKCU.
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=Se7e-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "portuguese_brazilian"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos adicionais:"
Name: "startupicon"; Description: "Iniciar o Se7e junto com o Windows"; GroupDescription: "Opções adicionais:"

[Files]
Source: "..\dist\Se7e\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
  IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelID}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
  IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelID}"; \
  Tasks: desktopicon

; Same HKCU Run-key value name and quoted-path format that se7e.autostart
; already reads/writes when frozen, so toggling "Iniciar com Windows" in the
; app's own Settings later sees this exact entry as already enabled.
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "se7e"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: startupicon; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "install-hooks"; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Iniciar o {#MyAppName} agora"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  // Must run in usUninstall (before files are removed) — by the later
  // usPostUninstall step {app}\Se7e.exe no longer exists to run at all.
  // hooks_install.uninstall() also backs up the user's whole settings.json
  // before touching it, same as install-hooks does.
  if CurUninstallStep = usUninstall then
  begin
    Exec(ExpandConstant('{app}\{#MyAppExeName}'), 'uninstall-hooks', '',
      SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
