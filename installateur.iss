; Installateur PhilPDF (Inno Setup)
; Installation pour l'utilisateur courant, sans droits administrateur.
; Aucune association de fichiers ici : elle se regle dans PhilPDF (Preferences), reversible.
#ifndef Version
  #define Version "0.1"
#endif

[Setup]
AppId={{D12154DE-3AA3-4B54-8054-5733C419D89A}
AppName=PhilPDF
AppVersion={#Version}
AppPublisher=PhilPDF
DefaultDirName={localappdata}\Programs\PhilPDF
DefaultGroupName=PhilPDF
PrivilegesRequired=lowest
OutputBaseFilename=PhilPDF_Setup
SetupIconFile=philpdf.ico
UninstallDisplayIcon={app}\PhilPDF.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=yes

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "Créer une icône sur le Bureau"; Flags: unchecked

[Files]
Source: "dist\PhilPDF\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "LISEZMOI.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\PhilPDF"; Filename: "{app}\PhilPDF.exe"
Name: "{userdesktop}\PhilPDF"; Filename: "{app}\PhilPDF.exe"; Tasks: bureau

[Run]
Filename: "{app}\PhilPDF.exe"; Description: "Lancer PhilPDF"; Flags: nowait postinstall skipifsilent
