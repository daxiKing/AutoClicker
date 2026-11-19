; AutoClicker installer - Inno Setup 6
#define MyAppName "AutoClicker"
#define MyAppVersion "2.5.0"
#define MyAppPublisher "AutoClicker"
#define MyAppExeName "AutoClicker.exe"

[Setup]
AppId={{A7E3C4F2-8D1B-4C9A-B5E6-3F2D7A1C8B94}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer
OutputBaseFilename=AutoClicker-Setup-{#MyAppVersion}
SetupIconFile=autoclicker.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0
AppMutex=AutoClicker.Singleton.1
VersionInfoVersion=2.5.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=AutoClicker installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce
Name: "startupicon"; Description: "Start AutoClicker with &Windows"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "dist\AutoClicker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Comment: "Auto clicks, auto keys and macros for Windows."; Tasks: desktopicon
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Comment: "Auto clicks, auto keys and macros for Windows."
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

; User macros, settings and logs live under {app}\data. Inno only removes the
; files it installed, so the vault survives an uninstall for later reinstalls.



