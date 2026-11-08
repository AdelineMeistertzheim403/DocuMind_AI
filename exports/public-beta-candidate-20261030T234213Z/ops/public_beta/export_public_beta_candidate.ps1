param(
  [string]$OutRoot = "exports",
  [string]$ApiImage = "documind-s14-6-api:local",
  [string]$WebImage = "documind-s14-6-web:local",
  [string]$SafeDirectory = "C:/Users/Adeline/Documents/DocuMind_AI"
)

$ErrorActionPreference = "Stop"

function New-EmptyDirectory([string]$path) {
  if (Test-Path -LiteralPath $path) {
    throw "Refusing to overwrite existing path: $path"
  }
  New-Item -ItemType Directory -Force -Path $path | Out-Null
}

function Remove-IfExists([string]$path) {
  if (Test-Path -LiteralPath $path) {
    Remove-Item -LiteralPath $path -Force -Recurse
  }
}

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$outDir = Join-Path $OutRoot "public-beta-candidate-$timestamp"
New-EmptyDirectory $outDir

Write-Host "Export dir: $outDir"

$git = "git"
$gitSafe = @("-c", "safe.directory=$SafeDirectory")

$head = & $git @gitSafe rev-parse HEAD
$branch = & $git @gitSafe rev-parse --abbrev-ref HEAD

Set-Content -NoNewline -Encoding utf8 (Join-Path $outDir "GIT_HEAD.txt") $head
Set-Content -NoNewline -Encoding utf8 (Join-Path $outDir "GIT_BRANCH.txt") $branch

Write-Host "Git branch: $branch"
Write-Host "Git HEAD:    $head"

# 1) Base export = tracked files at HEAD (no working tree mods, no untracked Beta Lite)
Write-Host "Running git archive (tracked files at HEAD)..."
& $git @gitSafe archive --format=tar HEAD | tar -xf - -C $outDir

# 2) Add deployment-only files created for public beta
$extraPaths = @(
  "compose.public-beta.vps.yaml",
  ".env.public-beta.example",
  ".env.public-beta.images.example",
  "ops/public_beta"
)

foreach ($p in $extraPaths) {
  if (-not (Test-Path -LiteralPath $p)) {
    throw "Expected path not found: $p"
  }
  $dest = Join-Path $outDir $p
  New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
  Copy-Item -LiteralPath $p -Destination $dest -Recurse -Force
}

# 3) Overlay exact runtime sources from the recipe images (4a10) without touching current worktree
Write-Host "Overlaying files from images: $ApiImage / $WebImage"

$apiContainer = (docker create $ApiImage)
try {
  # Map /app/* from API image to repo root
  $apiMappings = @(
    @{ Src = "/app/backend"; Dest = "backend" },
    @{ Src = "/app/migrations"; Dest = "migrations" },
    @{ Src = "/app/tools"; Dest = "tools" },
    @{ Src = "/app/alembic.ini"; Dest = "alembic.ini" },
    @{ Src = "/app/pyproject.toml"; Dest = "pyproject.toml" },
    @{ Src = "/app/requirements.runtime.lock"; Dest = "requirements.runtime.lock" },
    @{ Src = "/app/requirements.test.lock"; Dest = "requirements.test.lock" }
  )

  foreach ($m in $apiMappings) {
    $destPath = Join-Path $outDir $m.Dest
    Remove-IfExists $destPath
    New-Item -ItemType Directory -Force -Path (Split-Path $destPath) | Out-Null
    docker cp "$apiContainer`:$($m.Src)" "$destPath" | Out-Null
  }
}
finally {
  docker rm -f $apiContainer | Out-Null
}

$webContainer = (docker create $WebImage)
try {
  # Map /app/* from WEB image to frontend/
  $webMappings = @(
    @{ Src = "/app/server"; Dest = "frontend/server" },
    @{ Src = "/app/dist"; Dest = "frontend/dist" },
    @{ Src = "/app/package.json"; Dest = "frontend/package.json" },
    @{ Src = "/app/package-lock.json"; Dest = "frontend/package-lock.json" }
  )

  foreach ($m in $webMappings) {
    $destPath = Join-Path $outDir $m.Dest
    Remove-IfExists $destPath
    New-Item -ItemType Directory -Force -Path (Split-Path $destPath) | Out-Null
    docker cp "$webContainer`:$($m.Src)" "$destPath" | Out-Null
  }
}
finally {
  docker rm -f $webContainer | Out-Null
}

# 4) Scrub obvious local/private artifacts from the export
# - Never export real .env
Remove-IfExists (Join-Path $outDir ".env")

# - Never export recipe run artifacts
Remove-IfExists (Join-Path $outDir "var")

# - Never export venvs or caches
Remove-IfExists (Join-Path $outDir ".venv")
Remove-IfExists (Join-Path $outDir "__pycache__")
Get-ChildItem -LiteralPath $outDir -Recurse -Directory -Force |
  Where-Object { $_.Name -in @("__pycache__", ".pytest_cache", "node_modules") } |
  ForEach-Object { Remove-IfExists $_.FullName }

# - Remove any private key-like extensions (defense-in-depth)
Get-ChildItem -LiteralPath $outDir -Recurse -File -Force |
  Where-Object {
    $_.Extension -in @(".pem", ".key", ".p12", ".pfx", ".age") -or
    $_.Name -match "(?i)id_rsa|private|secret"
  } |
  ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }

# 5) Manifest + archive
Write-Host "Computing manifest..."
$files = Get-ChildItem -LiteralPath $outDir -Recurse -File -Force
$manifest = Join-Path $outDir "MANIFEST.sha256"

$lines = foreach ($f in $files) {
  $rel = $f.FullName.Substring($outDir.Length + 1).Replace("\\", "/")
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $f.FullName).Hash.ToLowerInvariant()
  "$hash  $rel"
}

$lines | Sort-Object | Set-Content -Encoding utf8 -LiteralPath $manifest

Write-Host "Creating tar.gz archive..."
$archivePath = "$outDir.tar.gz"
# bsdtar uses -C and relative path
$parent = Split-Path -Parent $outDir
$base = Split-Path -Leaf $outDir
& tar -czf $archivePath -C $parent $base

$archiveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash.ToLowerInvariant()
Set-Content -Encoding utf8 -LiteralPath "$archivePath.sha256" -Value "$archiveHash  $(Split-Path -Leaf $archivePath)"

Write-Host "OK"
Write-Host "Archive: $archivePath"
Write-Host "SHA256:  $archiveHash"

