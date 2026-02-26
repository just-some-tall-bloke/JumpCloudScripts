# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/

# macOS Version Compliance
# Manages device groups for macOS version compliance tracking.

# --- Configuration ---
# Get API key from environment variable
$API_KEY = $env:JUMPCLOUD_API_KEY
if ([string]::IsNullOrEmpty($API_KEY)) {
    Write-Host "Error: JUMPCLOUD_API_KEY environment variable is not set" -ForegroundColor Red
    Write-Host "Please set it using: `$env:JUMPCLOUD_API_KEY = 'your_api_key'" -ForegroundColor Yellow
    exit 1
}

$BASE_URL = "https://console.jumpcloud.com/api"
$HEADERS = @{
    "x-api-key"    = $API_KEY
    "Content-Type" = "application/json"
    "Accept"       = "application/json"
}

# --- Functions ---
function Get-GroupInfo {
    param($GroupId)
    $uri = "$BASE_URL/v2/systemgroups/$GroupId"
    try {
        $response = Invoke-RestMethod -Uri $uri -Headers $HEADERS -Method Get
        return $response
    }
    catch {
        return $null
    }
}

function Rename-Group {
    param($GroupId, $NewName)
    $uri = "$BASE_URL/v2/systemgroups/$GroupId"
    $payload = @{ name = $NewName } | ConvertTo-Json
    try {
        Invoke-RestMethod -Uri $uri -Headers $HEADERS -Method Put -Body $payload
        Write-Host "✅ Group renamed to: $NewName" -ForegroundColor Green
    }
    catch {
        Write-Host "⚠️ Failed to rename group: $_" -ForegroundColor Yellow
    }
}

function Get-AllSystems {
    Write-Host "Fetching systems from JumpCloud..." -ForegroundColor Cyan
    $systems = @()
    $skip = 0
    $limit = 100
    while ($true) {
        $uri = "$BASE_URL/systems?limit=$limit&skip=$skip"
        $response = Invoke-RestMethod -Uri $uri -Headers $HEADERS -Method Get
        if ($null -eq $response.results -or $response.results.Count -eq 0) { break }
        $systems += $response.results
        Write-Progress -Activity "Fetching Systems" -Status "$($systems.Count) fetched"
        if ($response.results.Count -lt $limit) { break }
        $skip += $limit
    }
    Write-Progress -Activity "Fetching Systems" -Completed
    Write-Host "Found $($systems.Count) total systems" -ForegroundColor Green
    return $systems
}

function Get-GroupMembers {
    param($GroupId)
    Write-Host "Fetching current group members..." -ForegroundColor Cyan
    $members = @()
    $skip = 0
    $limit = 100
    while ($true) {
        $uri = "$BASE_URL/v2/systemgroups/$GroupId/members?limit=$limit&skip=$skip"
        $response = Invoke-RestMethod -Uri $uri -Headers $HEADERS -Method Get
        if (-not $response) { break }
        foreach ($item in $response) {
            $id = if ($item.id) { $item.id } elseif ($item._id) { $item._id } else { $item.to.id }
            if ($id) { $members += $id }
        }
        if ($response.Count -lt $limit) { break }
        $skip += $limit
    }
    Write-Host "Found $($members.Count) systems currently in group" -ForegroundColor Green
    return $members
}

function Compare-Versions {
    param([string]$current, [string]$target)
    try {
        $v1 = [System.Version]$current
        $v2 = [System.Version]$target
        return $v1 -lt $v2
    }
    catch {
        # Fallback to manual split if part is missing (e.g., "15" instead of "15.0.0")
        $cParts = $current.Split('.')
        $tParts = $target.Split('.')
        $max = [Math]::Max($cParts.Count, $tParts.Count)
        for ($i = 0; $i -lt $max; $i++) {
            $cVal = if ($i -lt $cParts.Count) { [int]$cParts[$i] } else { 0 }
            $tVal = if ($i -lt $tParts.Count) { [int]$tParts[$i] } else { 0 }
            if ($cVal -lt $tVal) { return $true }
            if ($cVal -gt $tVal) { return $false }
        }
        return $false
    }
}

function Main {
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  JumpCloud macOS Compliance Management (PowerShell)  " -ForegroundColor Cyan -BackgroundColor White
    Write-Host "============================================================" -ForegroundColor Cyan

    $targetGroupId = Read-Host "`nEnter target JumpCloud group ID"
    if ([string]::IsNullOrWhiteSpace($targetGroupId)) { exit 1 }

    $groupInfo = Get-GroupInfo -GroupId $targetGroupId
    if ($null -eq $groupInfo) {
        Write-Host "❌ Group not found." -ForegroundColor Red
        exit 1
    }
    Write-Host "Current group name: $($groupInfo.name)" -ForegroundColor Cyan

    $minVersion = Read-Host "`nEnter target macOS version (e.g., 15.7.1)"
    if ([string]::IsNullOrWhiteSpace($minVersion)) { exit 1 }

    $suggestedName = "Macs below $minVersion"
    if ($groupInfo.name -ne $suggestedName) {
        $choice = Read-Host "Rename group to '$suggestedName'? (y/n)"
        if ($choice.ToLower() -eq 'y') {
            Rename-Group -GroupId $targetGroupId -NewName $suggestedName
        }
    }

    $allSystems = Get-AllSystems
    $groupMemberIds = Get-GroupMembers -GroupId $targetGroupId
    $groupMemberSet = [System.Collections.Generic.HashSet[string]]::new($groupMemberIds)

    Write-Host "`nChecking ALL Macs for non-compliance..." -ForegroundColor Cyan
    $toAdd = @()
    $toRemove = @()

    foreach ($system in $allSystems) {
        if ($system.os -ne "Mac OS X") {
            if ($groupMemberSet.Contains($system._id)) { $toRemove += $system }
            continue
        }

        $v = $system.version
        $hostname = $system.hostname
        if ([string]::IsNullOrEmpty($v)) {
            Write-Host "  ⚠️  $($hostname): No version found" -ForegroundColor Yellow
            continue
        }

        if (Compare-Versions -current $v -target $minVersion) {
            if (-not $groupMemberSet.Contains($system._id)) { $toAdd += $system }
            Write-Host "  ❌ $($hostname): $v < $minVersion" -ForegroundColor Red
        }
        else {
            if ($groupMemberSet.Contains($system._id)) { $toRemove += $system }
            Write-Host "  ✅ $($hostname): $v >= $minVersion" -ForegroundColor Green
        }
    }

    Write-Host "`n📊 Summary:" -ForegroundColor Cyan
    Write-Host "  Non-compliant Macs: $($toAdd.Count)" -ForegroundColor Green
    Write-Host "  Compliant Macs in group: $($toRemove.Count)" -ForegroundColor Yellow

    if ($toAdd.Count -gt 0) {
        $confirm = Read-Host "`nAdd $($toAdd.Count) systems to group? (y/n)"
        if ($confirm.ToLower() -eq 'y') {
            foreach ($s in $toAdd) {
                $payload = @{ op = "add"; type = "system"; id = $s._id } | ConvertTo-Json
                Invoke-RestMethod -Uri "$BASE_URL/v2/systemgroups/$targetGroupId/members" -Headers $HEADERS -Method Post -Body $payload
                Write-Host "  ✅ Added $($s.hostname)" -ForegroundColor Green
            }
        }
    }

    if ($toRemove.Count -gt 0) {
        $confirm = Read-Host "`nRemove $($toRemove.Count) systems from group? (y/n)"
        if ($confirm.ToLower() -eq 'y') {
            foreach ($s in $toRemove) {
                $payload = @{ op = "remove"; type = "system"; id = $s._id } | ConvertTo-Json
                Invoke-RestMethod -Uri "$BASE_URL/v2/systemgroups/$targetGroupId/members" -Headers $HEADERS -Method Post -Body $payload
                Write-Host "  ✅ Removed $($s.hostname)" -ForegroundColor Green
            }
        }
    }

    Write-Host "`n✅ Operation complete!" -ForegroundColor Green
}

Main
