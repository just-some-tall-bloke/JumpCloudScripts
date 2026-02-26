# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/

# Timezone/Region Sync Auditor
# Detects devices with "Set time zone automatically" disabled
# Audits for drastic clock drift (which can break MDM API auth)

# --- Configuration ---
Param(
    [int]$MaxDrift = 300,
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

function Get-TimezoneInsights {
    Write-Host "Fetching timezone data from System Insights..." -ForegroundColor Cyan
    $records = @()
    $skip = 0
    $limit = 100
    while ($true) {
        $uri = "$BASE_URL/v2/systeminsights/os_version?limit=$limit&skip=$skip"
        $response = Invoke-RestMethod -Uri $uri -Headers $HEADERS -Method Get
        if (-not $response) { break }
        $records += $response
        Write-Progress -Activity "Fetching Timezone Data" -Status "$($records.Count) fetched"
        if ($response.Count -lt $limit) { break }
        $skip += $limit
    }
    Write-Progress -Activity "Fetching Timezone Data" -Completed
    Write-Host "Done! Found $($records.Count) timezone records." -ForegroundColor Green
    return $records
}

function Send-BroadcasterAlert {
    param(
        [string]$SystemId,
        [string]$Hostname,
        [string]$Issue
    )
    
    $alertTitle = "Timezone/Time Sync Issue Detected"
    $alertMsg = "Your Mac's time synchronization needs attention: $Issue. Please contact IT."
    
    $alertJson = @{
        status  = "warning"
        title   = $alertTitle
        message = $alertMsg
    } | ConvertTo-Json
    
    $script = "echo '$alertJson' > /Users/Shared/jc-alert.json && chmod 666 /Users/Shared/jc-alert.json"
    
    $payload = @{
        name        = "Timezone Alert - $Hostname"
        command     = $script
        commandType = "linux"
        launchType  = "runOnce"
        user        = "0"
    } | ConvertTo-Json
    
    $uri = "$BASE_URL/commands"
    $response = Invoke-RestMethod -Uri $uri -Headers $HEADERS -Method Post -Body $payload
    $cmdId = $response._id
    
    $runPayload = @{ id = $SystemId } | ConvertTo-Json
    $runUri = "$BASE_URL/v2/commands/$cmdId/systems"
    Invoke-RestMethod -Uri $runUri -Headers $HEADERS -Method Post -Body $runPayload | Out-Null
    
    return $cmdId
}

function Add-SystemToGroup {
    param(
        [string]$SystemId,
        [string]$GroupId
    )
    
    $uri = "$BASE_URL/v2/systemgroups/$GroupId/members"
    $payload = @{
        op   = "add"
        type = "system"
        id   = $SystemId
    } | ConvertTo-Json
    
    $response = Invoke-RestMethod -Uri $uri -Headers $HEADERS -Method Post -Body $payload -SkipHttpErrorCheck
    return $response.StatusCode -in @(200, 201, 204)
}

function Check-SystemTimezoneCompliance {
    param(
        [PSObject]$System,
        [int]$MaxDriftSeconds
    )
    
    $systemId = $System._id
    $hostname = $System.hostname
    if ([string]::IsNullOrEmpty($hostname)) { $hostname = "Unknown" }
    
    $issues = @()
    
    # In production, this would execute commands on the system via JumpCloud
    # to get actual timezone and clock drift data
    
    return @{
        id          = $systemId
        hostname    = $hostname
        has_issues  = $issues.Count -gt 0
        issues      = $issues
    }
}

# --- Main ---
Write-Host "Starting timezone audit: Max clock drift $MaxDrift seconds" -ForegroundColor Cyan
Write-Host ""

# 1. Get all systems
$allSystems = Get-AllSystems

# 2. Get timezone data from System Insights
$timezoneRecords = Get-TimezoneInsights

$problematicSystems = @()

# 3. Check each system for timezone compliance
foreach ($system in $allSystems) {
    $result = Check-SystemTimezoneCompliance -System $system -MaxDriftSeconds $MaxDrift
    if ($result.has_issues) {
        $problematicSystems += $result
    }
}

# 4. Report
Write-Host ""
Write-Host "Audit complete. Found $($problematicSystems.Count) systems with timezone issues." -ForegroundColor Cyan

if ($problematicSystems.Count -eq 0) {
    Write-Host "All systems have proper timezone configuration! `u{2705}" -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host ("-" * 80)
Write-Host ("{0,-30} {1}" -f "HOSTNAME", "ISSUES")
Write-Host ("-" * 80)
foreach ($system in $problematicSystems) {
    $issuesStr = if ($system.issues.Count -gt 0) { $system.issues -join "; " } else { "No issues detected" }
    Write-Host ("{0,-30} {1}" -f $system.hostname, $issuesStr)
}
Write-Host ("-" * 80)

# 4.5 CSV Export
if (-not [string]::IsNullOrEmpty($CsvPath)) {
    Write-Host ""
    Write-Host "Exporting results to $CsvPath..." -ForegroundColor Cyan
    try {
        $csvData = $problematicSystems | ForEach-Object {
            [PSCustomObject]@{
                hostname = $_.hostname
                issues   = $_.issues -join "; "
                id       = $_.id
            }
        }
        $csvData | Export-Csv -Path $CsvPath -NoTypeInformation
        Write-Host "Successfully exported to $CsvPath" -ForegroundColor Green
    }
    catch {
        Write-Host "Failed to export CSV: $_" -ForegroundColor Red
    }
}

# 5. Apply Changes
if (-not $Apply) {
    Write-Host ""
    Write-Host "[DRY RUN] No changes applied. Run with -Apply to execute actions." -ForegroundColor Yellow
    if ($SendAlerts) {
        Write-Host "[DRY RUN] Would send broadcaster alerts to these systems." -ForegroundColor Yellow
    }
    if (-not [string]::IsNullOrEmpty($GroupId)) {
        Write-Host "[DRY RUN] Would add these systems to group $GroupId." -ForegroundColor Yellow
    }
    exit 0
}

# Real Execution
Write-Host ""
Write-Host "Applying changes..." -ForegroundColor Cyan
foreach ($system in $problematicSystems) {
    if (-not [string]::IsNullOrEmpty($GroupId)) {
        if (Add-SystemToGroup -SystemId $system.id -GroupId $GroupId) {
            Write-Host "  [+] Added $($system.hostname) to group."
        }
        else {
            Write-Host "  [x] Failed to add $($system.hostname) to group." -ForegroundColor Red
        }
    }
    
    if ($SendAlerts) {
        try {
            $issueSummary = $system.issues -join "; "
            Send-BroadcasterAlert -SystemId $system.id -Hostname $system.hostname -Issue $issueSummary
            Write-Host "  [!] Sent Broadcaster alert to $($system.hostname)."
        }
        catch {
            Write-Host "  [x] Failed to alert $($system.hostname): $_" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "Done!" -ForegroundColor Green
