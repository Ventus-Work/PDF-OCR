param(
    [ValidateSet("install", "build", "dev", "preview")]
    [string]$Command = "build"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $ProjectRoot "frontend"
$WorkRoot = Join-Path $env:LOCALAPPDATA "Codex\ps-docparser-frontend-work"
$CacheRoot = Join-Path $env:LOCALAPPDATA "Codex\npm-cache"

if (-not (Test-Path $FrontendRoot)) {
    throw "frontend folder not found: $FrontendRoot"
}

New-Item -ItemType Directory -Force -Path $WorkRoot | Out-Null
New-Item -ItemType Directory -Force -Path $CacheRoot | Out-Null

foreach ($file in @("package.json", "index.html", "tsconfig.json", "vite.config.ts")) {
    Copy-Item -LiteralPath (Join-Path $FrontendRoot $file) -Destination (Join-Path $WorkRoot $file) -Force
}

$packageLock = Join-Path $FrontendRoot "package-lock.json"
if (Test-Path $packageLock) {
    Copy-Item -LiteralPath $packageLock -Destination (Join-Path $WorkRoot "package-lock.json") -Force
}

$sourceSrc = Join-Path $FrontendRoot "src"
$targetSrc = Join-Path $WorkRoot "src"
if (Test-Path $targetSrc) {
    $resolvedTarget = (Resolve-Path $targetSrc).Path
    $resolvedWork = (Resolve-Path $WorkRoot).Path
    if (-not $resolvedTarget.StartsWith($resolvedWork, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove outside frontend work root: $resolvedTarget"
    }
    Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
}
Copy-Item -LiteralPath $sourceSrc -Destination $targetSrc -Recurse -Force

Push-Location $WorkRoot
try {
    npm install --no-audit --no-fund --cache $CacheRoot
    if ($LASTEXITCODE -ne 0) {
        throw "npm install failed with exit code $LASTEXITCODE"
    }

    if ($Command -eq "install") {
        Write-Host "Frontend dependencies installed in $WorkRoot"
        exit 0
    }

    npm run $Command
    if ($LASTEXITCODE -ne 0) {
        throw "npm run $Command failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
