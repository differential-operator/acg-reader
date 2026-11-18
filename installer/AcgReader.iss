#define AppName "Acg连页"
#define AppVersion "1.0.1"
[Setup]
AppId={{FF09E9A4-6B45-4C40-8D78-2B12E7BDE091}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Acg连页
DefaultDirName={localappdata}\Programs\AcgReader
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\installers
OutputBaseFilename=AcgReader-Setup-{#AppVersion}-x64
SetupIconFile=..\favicon.ico
UninstallDisplayIcon={app}\Acg连页.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayName={#AppName}
VersionInfoVersion=1.0.1.0
VersionInfoDescription=Acg连页安装程序
[Languages]
Name: "chinese"; MessagesFile: "compiler:Default.isl,ChineseSimplified.isl"
[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce
[Files]
Source: "..\release\Acg连页.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\release\THIRD-PARTY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\release\hls-LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\release\ffmpeg-GPLv3.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsWebView2
[Icons]
Name: "{group}\Acg连页"; Filename: "{app}\Acg连页.exe"
Name: "{group}\卸载 Acg连页"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Acg连页"; Filename: "{app}\Acg连页.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\Acg连页.exe"; Description: "启动 Acg连页"; Flags: nowait postinstall skipifsilent
[Code]
function NeedsWebView2: Boolean;
var Version: String;
begin
  Result := not (RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
  if Result then
    Result := not (RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var ExitCode: Integer;
begin
  Result := '';
  if NeedsWebView2 then begin
    ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
    WizardForm.StatusLabel.Caption := '正在安装 WebView2 运行组件，请保持网络连接……';
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then begin
      Result := '无法启动 WebView2 安装程序，请检查网络后重新运行安装包。';
      Exit;
    end;
    if NeedsWebView2 then Result := 'WebView2 运行组件安装未完成，请检查网络后重新运行安装包。';
  end;
end;
