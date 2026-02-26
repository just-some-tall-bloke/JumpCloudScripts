# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/

# Device Uptime Monitor
# Automatically manages device groups for systems with high uptime.

# --- Configuration ---
$UPTIME_THRESHOLD_DAYS = 14
$CONTACT_WINDOW_DAYS = 7
$RATE_LIMIT_DELAY = 100 # Milliseconds between API calls

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

function Get-SystemUptime {
    param($SystemId)
    $uri = "$BASE_URL/v2/systeminsights/$SystemId/uptime"
    try {
        $response = Invoke-RestMethod -Uri $uri -Headers $HEADERS -Method Get
        if ($response -and $response.Count -gt 0) {
            return $response[0].days
        }
    }
    catch { }
    return $null
}

function Main {
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  JumpCloud High Uptime Management (PowerShell)  " -ForegroundColor Cyan -BackgroundColor White
    Write-Host "  Systems with uptime > $UPTIME_THRESHOLD_DAYS days" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan

    $targetGroupId = Read-Host "`nEnter target JumpCloud group ID"
    if ([string]::IsNullOrWhiteSpace($targetGroupId)) { exit 1 }

    $groupInfo = Get-GroupInfo -GroupId $targetGroupId
    if ($null -eq $groupInfo) {
        Write-Host "❌ Group not found." -ForegroundColor Red
        exit 1
    }
    Write-Host "Current group name: $($groupInfo.name)" -ForegroundColor Cyan

    $suggestedName = "Macs with High Uptime"
    if ($groupInfo.name -ne $suggestedName) {
        $choice = Read-Host "Rename group to '$suggestedName'? (y/n)"
        if ($choice.ToLower() -eq 'y') {
            Rename-Group -GroupId $targetGroupId -NewName $suggestedName
        }
    }

    $allSystems = Get-AllSystems
    $groupMemberIds = Get-GroupMembers -GroupId $targetGroupId
    $groupMemberSet = [System.Collections.Generic.HashSet[string]]::new($groupMemberIds)

    $toAdd = @()
    $toRemove = @()
    
    $macSystems = $allSystems | Where-Object { 
        $_.os -eq "Mac OS X" -and $_.hostname -like "MAC*"
    }

    $cutoffDate = (Get-Date).AddDays(-$CONTACT_WINDOW_DAYS)
    $processedCount = 0

    Write-Host "`nChecking uptimes for $($macSystems.Count) Macs..." -ForegroundColor Cyan
    foreach ($system in $macSystems) {
        $processedCount++
        $hostname = $system.hostname
        Write-Progress -Activity "Checking Uptimes" -Status "$hostname ($processedCount/$($macSystems.Count))" -PercentComplete (($processedCount / $macSystems.Count) * 100)
        
        $lastContact = if ($system.lastContact) { [DateTime]::Parse($system.lastContact) } else { [DateTime]::MinValue }
        $isStale = $lastContact -lt $cutoffDate
        
        if ($isStale) {
            if ($groupMemberSet.Contains($system._id)) { $toRemove += $system }
            Write-Host "  $($hostname): Stale (last: $($lastContact.ToString('yyyy-MM-dd')))" -ForegroundColor Yellow
            continue
        }

        $uptime = Get-SystemUptime -SystemId $system._id
        if ($null -eq $uptime) {
            Write-Host "  $($hostname): No uptime data" -ForegroundColor Gray
            continue
        }

        if ($uptime -gt $UPTIME_THRESHOLD_DAYS) {
            if (-not $groupMemberSet.Contains($system._id)) { $toAdd += $system }
            Write-Host "  $($hostname): High uptime ($uptime days)" -ForegroundColor Yellow
        }
        else {
            if ($groupMemberSet.Contains($system._id)) { $toRemove += $system }
            Write-Host "  $($hostname): Low uptime ($uptime days)" -ForegroundColor Green
        }
        Start-Sleep -Milliseconds $RATE_LIMIT_DELAY
    }
    Write-Progress -Activity "Checking Uptimes" -Completed

    # Check for non-Macs or bad hostnames in group to remove
    foreach ($systemId in $groupMemberIds) {
        $system = $allSystems | Where-Object { $_._id -eq $systemId }
        if ($null -eq $system -or $system.os -ne "Mac OS X" -or $system.hostname -notlike "MAC*") {
            $toRemove += [PSCustomObject]@{ _id = $systemId; hostname = (if ($system) { $system.hostname } else { $systemId }) }
        }
    }

    Write-Host "`n📋 Summary:" -ForegroundColor Cyan
    Write-Host "  Systems to ADD: $($toAdd.Count)" -ForegroundColor Green
    Write-Host "  Systems to REMOVE: $($toRemove.Count)" -ForegroundColor Yellow

    if ($toAdd.Count -gt 0) {
        $confirm = Read-Host "`nAdd these systems? (y/n)"
        if ($confirm.ToLower() -eq 'y') {
            foreach ($s in $toAdd) {
                $payload = @{ op = "add"; type = "system"; id = $s._id } | ConvertTo-Json
                Invoke-RestMethod -Uri "$BASE_URL/v2/systemgroups/$targetGroupId/members" -Headers $HEADERS -Method Post -Body $payload
                Write-Host "  ✅ Added $($s.hostname)" -ForegroundColor Green
                Start-Sleep -Milliseconds $RATE_LIMIT_DELAY
            }
        }
    }

    if ($toRemove.Count -gt 0) {
        $confirm = Read-Host "`nRemove these systems? (y/n)"
        if ($confirm.ToLower() -eq 'y') {
            foreach ($s in $toRemove) {
                $payload = @{ op = "remove"; type = "system"; id = $s._id } | ConvertTo-Json
                Invoke-RestMethod -Uri "$BASE_URL/v2/systemgroups/$targetGroupId/members" -Headers $HEADERS -Method Post -Body $payload
                Write-Host "  ✅ Removed $($s.hostname)" -ForegroundColor Green
                Start-Sleep -Milliseconds $RATE_LIMIT_DELAY
            }
        }
    }

    Write-Host "`n✅ Operation complete!" -ForegroundColor Green
}

Main
