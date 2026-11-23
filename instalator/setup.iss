; Skrypt instalatora Inno Setup (budowany automatycznie przez GitHub Actions)
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "Anonimizator CV"
#define AppExe "AnonimizatorCV.exe"

[Setup]
AppId={{6B1E3C52-8A4D-4F7E-9C11-2D7A5B9E4F30}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Anonimizator CV
DefaultDirName={autopf}\Anonimizator CV
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; instalacja dla bieżącego użytkownika - nie wymaga uprawnień administratora
PrivilegesRequired=lowest
OutputDir=..\dist
; stała nazwa = stały link do pobrania (…/releases/latest/download/AnonimizatorCV-Setup.exe)
OutputBaseFilename=AnonimizatorCV-Setup
SetupIconFile=ikona.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Windows 10 lub 11 (starsze systemy dostaną czytelny komunikat)
MinVersion=10.0
ArchitecturesAllowed=x64compatible

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "contextmenu"; Description: "Dodaj „Anonimizuj CV” do menu prawego przycisku myszy (PDF, Word, JPG, PNG)"; GroupDescription: "Integracja:"

[Files]
Source: "..\dist\AnonimizatorCV\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENCJE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Odinstaluj {#AppName}"; Filename: "{uninstallexe}"
Name: "{group}\Licencje"; Filename: "{app}\LICENCJE.txt"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\AnonimizujCV"; ValueType: string; ValueName: ""; ValueData: "Anonimizuj CV"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\AnonimizujCV"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#AppExe}"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\AnonimizujCV\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\AnonimizujCV"; ValueType: string; ValueName: ""; ValueData: "Anonimizuj CV"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\AnonimizujCV"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#AppExe}"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\AnonimizujCV\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\AnonimizujCV"; ValueType: string; ValueName: ""; ValueData: "Anonimizuj CV"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\AnonimizujCV"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#AppExe}"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\AnonimizujCV\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\AnonimizujCV"; ValueType: string; ValueName: ""; ValueData: "Anonimizuj CV"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\AnonimizujCV"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#AppExe}"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\AnonimizujCV\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\AnonimizujCV"; ValueType: string; ValueName: ""; ValueData: "Anonimizuj CV"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\AnonimizujCV"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#AppExe}"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\AnonimizujCV\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
