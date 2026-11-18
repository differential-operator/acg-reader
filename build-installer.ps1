$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$compiler = Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Install Inno Setup 6 first.' }
if (-not (Test-Path -LiteralPath 'MicrosoftEdgeWebview2Setup.exe')) {
  curl.exe -L --fail --max-time 120 -o MicrosoftEdgeWebview2Setup.exe 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'
  if ($LASTEXITCODE -ne 0) { throw 'WebView2 bootstrapper download failed' }
  $signature = Get-AuthenticodeSignature -LiteralPath MicrosoftEdgeWebview2Setup.exe
  if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Microsoft Corporation*') { throw 'WebView2 bootstrapper signature verification failed' }
}
& $compiler installer/AcgReader.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
