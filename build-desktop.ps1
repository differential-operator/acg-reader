$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
py -3.14 -c "import imageio_ffmpeg,shutil;shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(),'ffmpeg.exe')"
py -3.14 -m PyInstaller --noconfirm --onefile --noconsole --name acg-backend --icon favicon.ico --add-data 'index.html;.' --add-data 'hls.min.js;.' --add-binary 'ffmpeg.exe;.' app.py
if ($LASTEXITCODE -ne 0) { throw 'Backend build failed' }
dotnet publish desktop/AcgReader.csproj -c Release -r win-x64 --self-contained true -o release
if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed' }
Copy-Item -LiteralPath THIRD-PARTY.md,hls-LICENSE.txt,ffmpeg-GPLv3.txt -Destination release
Write-Host 'Built release/Acg连页.exe'
