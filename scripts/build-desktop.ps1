#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Python = 'python',
    [string]$Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    [string]$WebViewBootstrapper,
    [switch]$PublicRelease,
    [string]$SignTool,
    [string]$CertificateThumbprint,
    [string]$TimestampUrl = 'http://timestamp.digicert.com'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if (!(Test-Path -LiteralPath $Iscc -PathType Leaf)) { throw 'Inno Setup 6 non trovato. Passa -Iscc con il percorso di ISCC.exe.' }
    & $Python -c "import sys; assert sys.platform == 'win32' and sys.version_info[:2] == (3,13), 'Build supportata: Python 3.13 Windows x64'; assert sys.maxsize > 2**32"
    if ($LASTEXITCODE) { throw 'Interprete di build non compatibile.' }
    if ($PublicRelease -and (!$SignTool -or !$CertificateThumbprint)) { throw 'Per una release pubblica servono SignTool e CertificateThumbprint.' }
    if ($WebViewBootstrapper) {
        $WebViewBootstrapper = (Resolve-Path -LiteralPath $WebViewBootstrapper).Path
        $signature = Get-AuthenticodeSignature -LiteralPath $WebViewBootstrapper
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { throw 'Il bootstrapper WebView2 deve avere firma Microsoft valida.' }
    }
    # Generated environments and artifacts are isolated from existing build/, .venv/ and .local/.
    $venv = Join-Path $root '.desktop-work\packaging'
    if (!(Test-Path -LiteralPath (Join-Path $venv 'Scripts\python.exe'))) {
        & $Python -m venv $venv
        if ($LASTEXITCODE) { throw 'Creazione ambiente non riuscita.' }
    }
    $buildPython = Join-Path $venv 'Scripts\python.exe'
    $buildId = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
    $artifactDirectory = Join-Path $root ('dist\windows-' + $buildId)
    & $buildPython -m pip install -r packaging/requirements-windows.lock
    if ($LASTEXITCODE) { throw 'Installazione dipendenze non riuscita.' }
    & $buildPython -m pip install --no-deps --no-build-isolation .
    if ($LASTEXITCODE) { throw 'Installazione pacchetto non riuscita.' }
    Push-Location frontend
    try {
        & npm.cmd ci --ignore-scripts
        if ($LASTEXITCODE) { throw 'npm ci non riuscito.' }
        & npm.cmd run build
        if ($LASTEXITCODE) { throw 'Build frontend non riuscita.' }
        & npm.cmd test
        if ($LASTEXITCODE) { throw 'Test frontend non riusciti.' }
        & npm.cmd audit --audit-level=moderate
        if ($LASTEXITCODE) { throw 'Dipendenze frontend da revisionare.' }
    } finally { Pop-Location }
    & $buildPython -m pip check
    if ($LASTEXITCODE) { throw 'pip check non riuscito.' }
    & $buildPython -m unittest discover -s tests -v
    if ($LASTEXITCODE) { throw 'Test Python non riusciti.' }
    & $buildPython -m PyInstaller --workpath (Join-Path $root ('.desktop-work\pyinstaller-' + $buildId)) --distpath $artifactDirectory packaging/Obliryx.spec
    if ($LASTEXITCODE) { throw 'Packaging non riuscito.' }
    if ($PublicRelease) {
        & $SignTool sign /sha1 $CertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 (Join-Path $artifactDirectory 'Obliryx\Obliryx.exe')
        if ($LASTEXITCODE) { throw 'Firma eseguibile non riuscita.' }
    }
    $isccArgs = @('packaging/installer.iss', ('/DBundleDir=' + (Join-Path $artifactDirectory 'Obliryx')), ('/O' + (Join-Path $artifactDirectory 'installer')))
    if ($WebViewBootstrapper) { $isccArgs += '/DWebViewBootstrapper=' + $WebViewBootstrapper }
    if ($PublicRelease) {
        $isccArgs += '/DPublicRelease=1'
        $isccArgs += '/Srelease="' + $SignTool + '" sign /sha1 ' + $CertificateThumbprint + ' /fd SHA256 /tr ' + $TimestampUrl + ' /td SHA256 $f'
    }
    & $Iscc @isccArgs
    if ($LASTEXITCODE) { throw 'Creazione installer non riuscita.' }
    & $buildPython scripts/release-inventory.py --directory $artifactDirectory
    if ($LASTEXITCODE) { throw 'Inventario non riuscito.' }
    if ($PublicRelease) {
        $installer = Join-Path $artifactDirectory 'installer\Obliryx-0.1.0.dev0-windows-x64-setup.exe'
        foreach ($signed in @((Join-Path $artifactDirectory 'Obliryx\Obliryx.exe'), $installer)) {
            if ((Get-AuthenticodeSignature -LiteralPath $signed).Status -ne 'Valid') { throw "Firma finale non valida: $signed" }
        }
    }
    @{directory=$artifactDirectory; version='0.1.0.dev0'; publicRelease=[bool]$PublicRelease} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'dist\latest-desktop.json') -Encoding utf8
    Write-Host "Artefatti creati in $artifactDirectory. Nessun commit o pubblicazione eseguiti."
} finally { Pop-Location }
