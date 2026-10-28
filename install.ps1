$ErrorActionPreference = 'Stop'
$AnkiXVersion = if ($env:ANKI_X_VERSION) { $env:ANKI_X_VERSION } else { '1.0.0rc2' }
$AnkiXArch = if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -eq 'Arm64') { 'arm64' } else { 'x64' }
$AnkiXBase = "https://github.com/HunterChan-SR/anki-x/releases/download/v$AnkiXVersion"
$AnkiXFile = "anki-x-$AnkiXVersion-windows-$AnkiXArch.zip"
$AnkiXTemp = Join-Path ([System.IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $AnkiXTemp | Out-Null
try {
    Invoke-WebRequest "$AnkiXBase/$AnkiXFile" -OutFile (Join-Path $AnkiXTemp $AnkiXFile)
    Invoke-WebRequest "$AnkiXBase/SHA256SUMS" -OutFile (Join-Path $AnkiXTemp 'SHA256SUMS')
    $AnkiXExpected = (Get-Content (Join-Path $AnkiXTemp 'SHA256SUMS') | Where-Object { ($_ -split '\s+')[1] -eq $AnkiXFile } | ForEach-Object { ($_ -split '\s+')[0] })
    $AnkiXActual = (Get-FileHash (Join-Path $AnkiXTemp $AnkiXFile) -Algorithm SHA256).Hash.ToLower()
    if (-not $AnkiXExpected -or $AnkiXActual -ne $AnkiXExpected) { throw 'Download verification failed; nothing was installed.' }
    Expand-Archive (Join-Path $AnkiXTemp $AnkiXFile) (Join-Path $AnkiXTemp 'release')
    & (Join-Path $AnkiXTemp 'release\anki-x\anki-x.exe') install
    if ($LASTEXITCODE -ne 0) { throw 'anki-x installation did not complete.' }
} finally {
    Remove-Item -LiteralPath $AnkiXTemp -Recurse -Force -ErrorAction SilentlyContinue
}
