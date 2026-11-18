$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$tools = Join-Path $PSScriptRoot 'tools/build-tools/android-15'
$platform = Join-Path $PSScriptRoot 'tools/platform/android-35/android.jar'
New-Item -ItemType Directory -Path build/classes,build/dex,output,.signing -Force | Out-Null
& "$tools/aapt2.exe" compile --dir app/src/main/res -o build/resources.zip
if ($LASTEXITCODE -ne 0) { throw 'Resource compilation failed' }
& "$tools/aapt2.exe" link -o build/unsigned.apk -I $platform --manifest app/src/main/AndroidManifest.xml -A app/src/main/assets -R build/resources.zip --auto-add-overlay
if ($LASTEXITCODE -ne 0) { throw 'Resource linking failed' }
 $sources = @(Get-ChildItem app/src/main/java -Recurse -Filter *.java | ForEach-Object FullName)
javac -encoding UTF-8 -source 8 -target 8 -classpath $platform -d build/classes @sources
if ($LASTEXITCODE -ne 0) { throw 'Java compilation failed' }
$classes = @(Get-ChildItem build/classes -Recurse -Filter *.class | ForEach-Object FullName)
java -cp "$tools/lib/d8.jar" com.android.tools.r8.D8 --lib $platform --min-api 26 --output build/dex @classes
if ($LASTEXITCODE -ne 0) { throw 'DEX compilation failed' }
py -3.14 -c "import zipfile; z=zipfile.ZipFile('build/unsigned.apk','a');z.write('build/dex/classes.dex','classes.dex');z.close()"
& "$tools/zipalign.exe" -f -p 4 build/unsigned.apk build/aligned.apk
if ($LASTEXITCODE -ne 0) { throw 'APK alignment failed' }
if (-not (Test-Path .signing/password.xml)) {
  $secret = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
  ConvertTo-SecureString $secret -AsPlainText -Force | Export-Clixml .signing/password.xml
}
$secure = Import-Clixml .signing/password.xml
$env:ACGR_KEYPASS = [System.Net.NetworkCredential]::new('', $secure).Password
try {
  if (-not (Test-Path .signing/release.p12)) {
    keytool -genkeypair -keystore .signing/release.p12 -storetype PKCS12 -storepass:env ACGR_KEYPASS -keypass:env ACGR_KEYPASS -alias acgreader -keyalg RSA -keysize 3072 -validity 10000 -dname 'CN=Acg Reader, O=Acg Reader' -noprompt
    if ($LASTEXITCODE -ne 0) { throw 'Signing key creation failed' }
  }
  & "$tools/apksigner.bat" sign --ks .signing/release.p12 --ks-key-alias acgreader --ks-pass env:ACGR_KEYPASS --key-pass env:ACGR_KEYPASS --out output/AcgReader-1.0.4.apk build/aligned.apk
  if ($LASTEXITCODE -ne 0) { throw 'APK signing failed' }
  & "$tools/apksigner.bat" verify --verbose output/AcgReader-1.0.4.apk
  if ($LASTEXITCODE -ne 0) { throw 'APK signature verification failed' }
} finally { Remove-Item Env:ACGR_KEYPASS -ErrorAction SilentlyContinue }

