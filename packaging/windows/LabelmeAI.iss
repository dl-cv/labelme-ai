#define AppName "LabelmeAI"
#define AppPublisher "DLCV"
#define AppURL "https://github.com/dl-cv/labelme-ai"
#define AppExeName "labelme.exe"

; Allow overriding these from command line, e.g.:
;   ISCC.exe packaging/windows/LabelmeAI.iss /DAppVersion=2026.01.06.0a0 /DSourceDir=dist\labelme /DCompressionProfile=fast
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#ifndef SourceDir
  #define SourceDir "..\..\dist\labelme"
#endif

; Compression profiles:
; - small: smaller installer, slower build
; - fast: faster build, larger installer
#ifndef CompressionProfile
  #define CompressionProfile "small"
#endif

#if CompressionProfile == "fast"
  #define AppCompression "zip"
  #define AppSolidCompression "no"
#else
  #define AppCompression "lzma2"
  #define AppSolidCompression "yes"
#endif

[Setup]
AppId={{F2A9AE26-7E27-4A9D-9B6A-9C6A6A2A7F30}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\..\installer_output
OutputBaseFilename={#AppName}_Setup_{#AppVersion}
SetupIconFile=..\..\labelme\icons\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression={#AppCompression}
SolidCompression={#AppSolidCompression}
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "运行 {#AppName}"; Flags: nowait postinstall skipifsilent

