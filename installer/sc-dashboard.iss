; Inno Setup script. Built by .github/workflows/build.yml:
;   iscc /DAppVersion=1.2.3 installer\sc-dashboard.iss
; Installs per user (no admin prompt), so the tray app can update itself silently.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "SC Dashboard"
#define AppExe "SC Dashboard.exe"

[Setup]
AppId={{6E2B4C1A-8F3D-4B7E-9A51-3C0D2E7F9B14}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=pikkon38
AppPublisherURL=https://github.com/pikkon38/sc-dashboard
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=SC-Dashboard-{#AppVersion}-Setup
SetupIconFile=..\build\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "startup"; Description: "Start SC Dashboard when Windows starts"; GroupDescription: "Options:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Options:"; Flags: unchecked

[Files]
Source: "..\dist\SC Dashboard\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; clear out the previous version's bundled files so nothing stale is left behind
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"""; Tasks: startup; Flags: uninsdeletevalue

[Run]
; also runs after a silent update, which is how the app comes back after updating itself
Filename: "{app}\{#AppExe}"; Description: "Start SC Dashboard now"; Flags: nowait postinstall

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM ""{#AppExe}"" /F"; Flags: runhidden; RunOnceId: "StopApp"
