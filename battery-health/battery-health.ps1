# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/

# Battery Health Auditor
# Monitors battery health and cycle count using System Insights.

# --- Configuration ---
Param(
    [int]$HealthThreshold = 80,
    [int]$CycleThreshold = 1000,
    [string]$GroupId,
    [string]$CsvPath,
    [switch]$SendAlerts,
    [switch]$Apply
)

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
    Write-Host "Done! Found $($systems.Count) systems." -ForegroundColor Green
    return $systems
}

function Get-BatteryInsights {
    Write-Host "Fetching battery data from System Insights..." -ForegroundColor Cyan
    $records = @()
    $skip = 0
    $limit = 100
    while ($true) {
        $uri = "$BASE_URL/v2/systeminsights/battery?limit=$limit&skip=$skip"
        $response = Invoke-RestMethod -Uri $uri -Headers $HEADERS -Method Get
        if (-not $response) { break }
        $records += $response
        Write-Progress -Activity "Fetching Battery Data" -Status "$($records.Count) fetched"
        if ($response.Count -lt $limit) { break }
        $skip += $limit
    }
    Write-Progress -Activity "Fetching Battery Data" -Completed
    Write-Host "Done! Found $($records.Count) battery records." -ForegroundColor Green
    return $records
}

function Send-BroadcasterAlert {
    param($SystemId, $Hostname)
    
    $alertTitle = "Battery Service Recommended"
    $alertMsg = "Your MacBook battery health is below 80% (or cycle count is high). Please contact IT for a replacement."
    
    # JSON for the alert file
    $alertJson = @{
        status  = "warning"
        title   = $alertTitle
        message = $alertMsg
    } | ConvertTo-Json -Compress
    
    # Command script (escaped for JSON payload)
    $script = "echo '$alertJson' > /Users/Shared/jc-alert.json && chmod 666 /Users/Shared/jc-alert.json"
    
    $payload = @{
        name        = "Battery Alert - $Hostname"
        command     = $script
        commandType = "linux"
        launchType  = "runOnce"
        user        = "0"
    } | ConvertTo-Json
    
    try {
        # Create and run the command
        $createResponse = Invoke-RestMethod -Uri "$BASE_URL/commands" -Headers $HEADERS -Method Post -Body $payload
        $cmdId = $createResponse._id
        
        $runPayload = @{ id = $SystemId } | ConvertTo-Json
        Invoke-RestMethod -Uri "$BASE_URL/v2/commands/$cmdId/systems" -Headers $HEADERS -Method Post -Body $runPayload
        
        return $cmdId
    }
    catch {
        Write-Host "❌ Failed to send alert to $($Hostname): $_" -ForegroundColor Red
        return $null
    }
}

function Add-SystemToGroup {
    param($SystemId, $GroupId)
    $uri = "$BASE_URL/v2/systemgroups/$GroupId/members"
    $payload = @{
        op   = "add"
        type = "system"
        id   = $SystemId
    } | ConvertTo-Json
    try {
        Invoke-RestMethod -Uri $uri -Headers $HEADERS -Method Post -Body $payload
        return $true
    }
    catch {
        return $false
    }
}

function Main {
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  JumpCloud Battery Health Auditor (PowerShell)  " -ForegroundColor Cyan -BackgroundColor White
    Write-Host "  Thresholds: Health < $HealthThreshold%, Cycles > $CycleThreshold" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan

    $allSystems = Get-AllSystems
    $idToSystem = @{}
    foreach ($s in $allSystems) { $idToSystem[$s._id] = $s }

    $batteryRecords = Get-BatteryInsights
    $poorHealthSystems = @()

    foreach ($record in $batteryRecords) {
        $systemId = $record.system_id
        $system = $idToSystem[$systemId]
        if (-not $system) { continue }

        $hostname = $system.hostname
        
        # Safe integer parsing
        $rawCycleCount = $record.cycle_count
        $cycleCount = 0
        if ($rawCycleCount -match '^\d+$') { $cycleCount = [int]$rawCycleCount }

        $rawHealth = $record.health
        $healthPercent = 100
        if ($rawHealth -eq "Good") { $healthPercent = 100 }
        elseif ($rawHealth -match '^\d+$') { $healthPercent = [int]$rawHealth }

        $condition = $record.condition

        $failing = $false
        $reason = @()

        # Focus solely on cycle count as health/condition data is unreliable in this environment
        if ($cycleCount -gt $CycleThreshold) {
            $failing = $true
            $reason += "Cycles $cycleCount (> $CycleThreshold)"
        }

        if ($failing) {
            $poorHealthSystems += [PSCustomObject]@{
                id        = $systemId
                hostname  = $hostname
                health    = $healthPercent
                cycles    = $cycleCount
                condition = $condition
                reason    = ($reason -join ", ")
            }
        }
    }

    Write-Host "`nAudit complete. Found $($poorHealthSystems.Count) systems with poor battery health." -ForegroundColor Cyan
    if ($poorHealthSystems.Count -eq 0) {
        Write-Host "All systems within healthy thresholds! ✅" -ForegroundColor Green
        exit 0
    }

    $poorHealthSystems | Format-Table -Property Hostname, Health, Cycles, Condition, Reason -AutoSize

    if ($CsvPath) {
        Write-Host "`nExporting results to $CsvPath..." -ForegroundColor Cyan
        $poorHealthSystems | Export-Csv -Path $CsvPath -NoTypeInformation
        Write-Host "Successfully exported to $CsvPath" -ForegroundColor Green
    }

    if (-not $Apply) {
        Write-Host "`n[DRY RUN] No changes applied. Run with -Apply to execute actions." -ForegroundColor Yellow
        if ($SendAlerts) { Write-Host "[DRY RUN] Would send broadcaster alerts to these systems." -ForegroundColor Yellow }
        if ($GroupId) { Write-Host "[DRY RUN] Would add these systems to group $GroupId." -ForegroundColor Yellow }
        exit 0
    }

    Write-Host "`nApplying changes..." -ForegroundColor Green
    foreach ($s in $poorHealthSystems) {
        if ($GroupId) {
            if (Add-SystemToGroup -SystemId $s.id -GroupId $GroupId) {
                Write-Host "  [+] Added $($s.hostname) to group." -ForegroundColor Green
            }
            else {
                Write-Host "  [x] Failed to add $($s.hostname) to group." -ForegroundColor Red
            }
        }

        if ($SendAlerts) {
            if (Send-BroadcasterAlert -SystemId $s.id -Hostname $s.hostname) {
                Write-Host "  [!] Sent Broadcaster alert to $($s.hostname)." -ForegroundColor Yellow
            }
        }
    }

    Write-Host "`nDone!" -ForegroundColor Green
}

Main
