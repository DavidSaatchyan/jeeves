#!/usr/bin/env pwsh
param([string]$TargetDir)
if (-not $TargetDir) { Write-Host "Usage: install.ps1 <target-directory>"; exit 1 }
if (-not (Test-Path $TargetDir)) { Write-Error "Not found: $TargetDir"; exit 1 }

$SrcRoot = Split-Path -Parent $PSScriptRoot
$TargetDir = (Get-Item $TargetDir).FullName
$errors = 0

Write-Host "Installing OpenFlo -> $TargetDir" -ForegroundColor Cyan

# ---- Merge opencode.json ----
$srcConfig = Join-Path $SrcRoot "opencode.json"
$dstConfig = Join-Path $TargetDir "opencode.json"

if (Test-Path $dstConfig) {
  Write-Host "  [MERGE] opencode.json - merging OpenFlo agents into existing config" -ForegroundColor Yellow
  $userConfig = Get-Content $dstConfig -Raw | ConvertFrom-Json
  $openfloConfig = Get-Content $srcConfig -Raw | ConvertFrom-Json

  # Merge agents (add OpenFlo agents that don't conflict with user's)
  if (-not $userConfig.agent) { $userConfig | Add-Member -NotePropertyName "agent" -NotePropertyValue @{} }
  $openfloConfig.agent.PSObject.Properties | ForEach-Object {
    if (-not $userConfig.agent.$($_.Name)) {
      $userConfig.agent | Add-Member -NotePropertyName $_.Name -NotePropertyValue $_.Value
      Write-Host "    + agent $($_.Name)" -ForegroundColor Green
    } else {
      Write-Host "    - agent $($_.Name) [exists, skipped]" -ForegroundColor DarkGray
    }
  }

  # Merge MCP (add openflo-mcp if not present)
  if (-not $userConfig.mcp) { $userConfig | Add-Member -NotePropertyName "mcp" -NotePropertyValue @{} }
  if (-not $userConfig.mcp.'openflo-mcp') {
    $userConfig.mcp | Add-Member -NotePropertyName "openflo-mcp" -NotePropertyValue $openfloConfig.mcp.'openflo-mcp'
    Write-Host "    + mcp server" -ForegroundColor Green
  }

  # Merge plugins (add OpenFlo plugins after user's)
  if (-not $userConfig.plugin) { $userConfig | Add-Member -NotePropertyName "plugin" -NotePropertyValue @() }
  $openfloConfig.plugin | ForEach-Object {
    if ($_ -notin $userConfig.plugin) {
      $userConfig.plugin += $_
      Write-Host "    + plugin $_" -ForegroundColor Green
    }
  }

  # Merge skills paths
  if (-not $userConfig.skills) { $userConfig | Add-Member -NotePropertyName "skills" -NotePropertyValue @{} }
  if (-not $userConfig.skills.paths) { $userConfig.skills | Add-Member -NotePropertyName "paths" -NotePropertyValue @() }
  $openfloConfig.skills.paths | ForEach-Object {
    if ($_ -notin $userConfig.skills.paths) { $userConfig.skills.paths += $_ }
  }

  # Set default agent to swarm only if user has no default
  if (-not $userConfig.default_agent) {
    $userConfig | Add-Member -NotePropertyName "default_agent" -NotePropertyValue "swarm"
    Write-Host "    + default_agent: swarm" -ForegroundColor Green
  }

  # Add instructions pointer
  if (-not $userConfig.instructions) { $userConfig | Add-Member -NotePropertyName "instructions" -NotePropertyValue @() }
  if ("AGENTS.md" -notin $userConfig.instructions) { $userConfig.instructions += "AGENTS.md" }

  $userConfig | ConvertTo-Json -Depth 10 | Set-Content $dstConfig -Encoding UTF8
} else {
  Copy-Item -Path $srcConfig -Destination $dstConfig -Force
  Write-Host "  [OK] opencode.json" -ForegroundColor Green
}

# ---- Merge AGENTS.md ----
$srcAgents = Join-Path $SrcRoot "AGENTS.md"
$dstAgents = Join-Path $TargetDir "AGENTS.md"
if (Test-Path $dstAgents) {
  Write-Host "  [MERGE] AGENTS.md - appending OpenFlo rules" -ForegroundColor Yellow
  $existing = Get-Content $dstAgents -Raw
  $new = Get-Content $srcAgents -Raw
  if ($existing -notmatch "OpenFlo") {
    Add-Content $dstAgents "`n`n$new"
    Write-Host "    + OpenFlo rules appended" -ForegroundColor Green
  } else {
    Write-Host "    - AGENTS.md already has OpenFlo rules [skipped]" -ForegroundColor DarkGray
  }
} else {
  Copy-Item -Path $srcAgents -Destination $dstAgents -Force
  Write-Host "  [OK] AGENTS.md" -ForegroundColor Green
}

# ---- Copy everything else (skip if exists) ----
$dirs = @(
  ".opencode"
  "mcp\openflo-mcp"
  "mcp\openflo-federation"
  "cli"
  "web"
  "scripts"
  "docs"
)

foreach ($dir in $dirs) {
  $src = Join-Path $SrcRoot $dir
  $dst = Join-Path $TargetDir $dir
  if (-not (Test-Path $src)) { Write-Host "  [SKIP] $dir (no source)"; continue }
  if ($dir -eq ".opencode") {
    # Merge .opencode subdirs recursively (agents, skills, plugins)
    Get-ChildItem -Path $src -Directory | ForEach-Object {
      $sub = $_.Name
      $subDst = Join-Path $dst $sub
      if (-not (Test-Path $subDst)) {
        Copy-Item -Path $_.FullName -Destination $subDst -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $subDst) { Write-Host "  [OK] .opencode/$sub" -ForegroundColor Green }
      } else {
        # Merge contents inside subdirs (agents, skills, plugins)
        Get-ChildItem -Path $_.FullName | ForEach-Object {
          $itemName = $_.Name
          $targetItem = Join-Path $subDst $itemName
          if (-not (Test-Path $targetItem)) {
            if ($_.PSIsContainer) { Copy-Item -Path $_.FullName -Destination $targetItem -Recurse -Force }
            else { Copy-Item -Path $_.FullName -Destination $targetItem -Force }
            Write-Host "    + .opencode/$sub/$itemName" -ForegroundColor Green
          }
        }
      }
    }
  } else {
    if (Test-Path $dst) { Write-Host "  - $dir [exists]" -ForegroundColor DarkGray; continue }
    $parent = Split-Path $dst -Parent
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    Copy-Item -Path $src -Destination $dst -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $dst) { Write-Host "  [OK] $dir" -ForegroundColor Green } else { Write-Host "  [FAIL] $dir"; $errors++ }
  }
}

# Copy GUIDE.md if not exists
$srcGuide = Join-Path $SrcRoot "docs\GUIDE.md"
$dstGuide = Join-Path $TargetDir "docs\GUIDE.md"
if (-not (Test-Path $dstGuide)) {
  $parent = Split-Path $dstGuide -Parent
  if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
  Copy-Item -Path $srcGuide -Destination $dstGuide -Force
  Write-Host "  [OK] docs\GUIDE.md" -ForegroundColor Green
} else {
  Write-Host "  - docs\GUIDE.md [exists]" -ForegroundColor DarkGray
}

# ---- npm install ----
$mcpDir = Join-Path $TargetDir "mcp\openflo-mcp"
if (Test-Path "$mcpDir\package.json") {
  Write-Host "`nInstalling MCP deps..." -ForegroundColor Cyan
  Push-Location $mcpDir
  npm install --no-audit --no-fund | Out-Null
  if ($?) { Write-Host "  [OK] npm install" -ForegroundColor Green } else { Write-Host "  [FAIL] npm install"; $errors++ }
  Pop-Location
}

# ---- Result ----
if ($errors -eq 0) {
  Write-Host "`nOpenFlo installed. Run: cd $TargetDir ; opencode ; /agents list" -ForegroundColor Green
} else {
  Write-Host "`n$errors errors" -ForegroundColor Yellow
}
exit $errors
