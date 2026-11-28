#ifndef AppVersion
  #define AppVersion "0.1.0.dev0"
#endif
#ifndef BundleDir
  #define BundleDir "..\dist\Obliryx"
#endif

[Setup]
AppId={{D787E1AF-A716-49F0-8B3F-768EE132E259}
AppName=Obliryx
AppVersion={#AppVersion}
AppPublisher=Obliryx contributors
DefaultDirName={localappdata}\Programs\Obliryx
DefaultGroupName=Obliryx
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
OutputDir=..\dist\installer
OutputBaseFilename=Obliryx-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
SetupMutex=ObliryxSetup
UninstallDisplayIcon={app}\Obliryx.exe
#ifdef PublicRelease
SignTool=release
SignedUninstaller=yes
#endif

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "Crea un collegamento sul desktop"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#ifdef WebViewBootstrapper
Source: "{#WebViewBootstrapper}"; DestDir: "{tmp}"; DestName: "MicrosoftEdgeWebview2Setup.exe"; Flags: deleteafterinstall; Check: NeedsWebView
#endif

[Icons]
Name: "{group}\Obliryx"; Filename: "{app}\Obliryx.exe"
Name: "{autodesktop}\Obliryx"; Filename: "{app}\Obliryx.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Obliryx.exe"; Description: "Apri Obliryx"; Flags: nowait postinstall skipifsilent

[Code]
const WebViewKey = 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function NeedsWebView: Boolean;
var Version: String;
begin
  Result := not ((RegQueryStringValue(HKCU, WebViewKey, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKLM32, WebViewKey, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKLM64, WebViewKey, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var Code: Integer;
begin
  Result := '';
  if not NeedsWebView then exit;
#ifdef WebViewBootstrapper
  if WizardSilent then begin
    Result := 'WebView2 Runtime mancante. Installalo prima di usare il setup silenzioso.';
    exit;
  end;
  if MsgBox('Obliryx richiede Microsoft WebView2 Runtime. Vuoi installarlo per questo utente? Il programma di installazione contatterà Microsoft.', mbConfirmation, MB_YESNO) <> IDYES then begin
    Result := 'Installa Microsoft WebView2 Runtime e riavvia questo setup. È disponibile anche l’installer offline sul sito Microsoft.';
    exit;
  end;
  ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
  if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, Code) then
    Code := -1;
  if (Code <> 0) or NeedsWebView then
    Result := 'Installazione WebView2 non riuscita. Verifica la rete oppure installa WebView2 Evergreen Standalone x64 da https://developer.microsoft.com/microsoft-edge/webview2/ e ripeti il setup.';
#else
  Result := 'WebView2 Runtime mancante. Installa WebView2 Evergreen (anche con installer offline) da https://developer.microsoft.com/microsoft-edge/webview2/ e ripeti il setup.';
#endif
end;
