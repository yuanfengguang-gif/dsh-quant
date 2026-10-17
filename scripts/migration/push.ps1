<#
.SYNOPSIS
  Push local repo to YOUR OWN GitHub repo (ASCII-only, no BOM needed).

.DESCRIPTION
  Current origin points to someone else's repo (yuanwang589-dev/deepseek-harness-quant).
  This script renames it to 'upstream' (keeps the reference) and points origin to your repo.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\migration\push.ps1 -NewRepoUrl "https://github.com/OWNER/REPO.git"
#>
param(
    [Parameter(Mandatory = $true)][string]$NewRepoUrl,
    [string]$Branch = "master",
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $root

function Invoke-Git([string]$cmd) {
    Write-Host "  > $cmd" -ForegroundColor Cyan
    if (-not $DryRun) { Invoke-Expression $cmd }
}

function Get-RemoteNames {
    $out = & git remote 2>$null
    return @($out | Where-Object { $_ -ne $null -and "$_".Trim() -ne "" })
}

Write-Host ""
Write-Host "=== 0) check ===" -ForegroundColor Yellow
Write-Host "  root: $root"
$remotes = Get-RemoteNames
Write-Host ("  remotes: " + ($remotes -join ", "))
$cur = ""
if ($remotes -contains "origin") { $cur = (& git remote get-url origin 2>$null) }
Write-Host "  origin url: $cur"
$dirty = (& git status --porcelain 2>$null | Measure-Object).Count
Write-Host "  uncommitted files: $dirty"
if ($dirty -gt 0) { Write-Host "  [WARN] uncommitted changes exist" -ForegroundColor Yellow }

Write-Host ""
Write-Host "=== 1) keep upstream ===" -ForegroundColor Yellow
if ($cur -and ($cur.Trim() -ne $NewRepoUrl.Trim())) {
    if ($remotes -notcontains "upstream") {
        Invoke-Git "git remote rename origin upstream"
    } else {
        Write-Host "  upstream already exists, keep it"
    }
} else {
    Write-Host "  origin already the target, skip"
}

Write-Host ""
Write-Host "=== 2) point origin to new repo ===" -ForegroundColor Yellow
if ($remotes -contains "origin") {
    Invoke-Git "git remote set-url origin `"$NewRepoUrl`""
} else {
    Invoke-Git "git remote add origin `"$NewRepoUrl`""
}

Write-Host ""
Write-Host "=== 3) push ===" -ForegroundColor Yellow
Invoke-Git "git push -u origin $Branch"

Write-Host ""
Write-Host "=== 4) result ===" -ForegroundColor Yellow
if (-not $DryRun) {
    Write-Host "  recent commits:"
    & git log --oneline -3
    Write-Host ""
    Write-Host ("  on the new machine: git clone " + $NewRepoUrl) -ForegroundColor Green
} else {
    Write-Host "  (DryRun only, nothing executed)"
}

Write-Host ""
Write-Host "NOTE: when prompted, log in as yuanfengguang-gif" -ForegroundColor Yellow
Write-Host "      if 403: cmdkey /delete:git:https://github.com" -ForegroundColor Yellow
