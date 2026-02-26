# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/

# Duplicate System Remover
# Identifies and removes duplicate system entries based on serial numbers.

# --- Configuration ---
Param(
    [switch]$Delete
)

$DRY_RUN = -not $Delete
$RATE_LIMIT_DELAY = 0.1 # Seconds between API calls
$LOG_FILE = "duplicate-remover.log"

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

# --- Logging Setup ---
function Log-Message {
    param(
        [string]$Message,
        [string]$Level = "INFO",
        [ConsoleColor]$Color = [ConsoleColor]::White
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logLine = "$timestamp - $Level - $Message"
    Add-Content -Path $LOG_FILE -Value $logLine -ErrorAction SilentlyContinue
    Write-Host $Message -ForegroundColor $Color
}

function Get-AllSystems {
    Log-Message "[*] Fetching all systems from JumpCloud..." "INFO" Cyan
    $systems = @()
    $limit = 100
    $skip = 0
    
    try {
        # Initial call to get total count
        $response = Invoke-RestMethod -Uri "$BASE_URL/systems?limit=1&fields=id" -Headers $HEADERS -Method Get
        $totalCount = $response.totalCount
        Log-Message "Total systems in JumpCloud: $totalCount" "INFO" Cyan
    }
    catch {
        $totalCount = $null
    }

    while ($true) {
        $uri = "$BASE_URL/systems?limit=$limit&skip=$skip&fields=id serialNumber lastContact hostname os"
        try {
            $response = Invoke-RestMethod -Uri $uri -Headers $HEADERS -Method Get
            if ($null -eq $response.results -or $response.results.Count -eq 0) { break }
            
            $systems += $response.results
            $processed = $systems.Count
            
            if ($null -ne $totalCount) {
                Write-Progress -Activity "Fetching Systems" -Status "$processed / $totalCount" -PercentComplete (($processed / $totalCount) * 100)
            }
            else {
                Write-Progress -Activity "Fetching Systems" -Status "$processed fetched"
            }
            
            if ($response.results.Count -lt $limit) { break }
            $skip += $limit
            Start-Sleep -Milliseconds ($RATE_LIMIT_DELAY * 1000)
        }
        catch {
            Log-Message "Error fetching systems: $_" "ERROR" Red
            return $null
        }
    }
    Write-Progress -Activity "Fetching Systems" -Completed
    Log-Message "[+] Found $($systems.Count) total systems." "INFO" Green
    return $systems
}

function Find-Duplicates {
    param($Systems)
    Log-Message "[SCAN] Scanning for duplicate serial numbers..." "INFO" Magenta
    $systemsBySerial = @{}
    $invalidSerials = 0
    
    foreach ($system in $Systems) {
        $serial = $system.serialNumber
        if ([string]::IsNullOrWhiteSpace($serial) -or $serial -eq "None") {
            $invalidSerials++
            continue
        }
        if (-not $systemsBySerial.ContainsKey($serial)) {
            $systemsBySerial[$serial] = New-Object System.Collections.Generic.List[PSObject]
        }
        $systemsBySerial[$serial].Add($system)
    }
    
    $duplicates = @{}
    foreach ($serial in $systemsBySerial.Keys) {
        if ($systemsBySerial[$serial].Count -gt 1) {
            $duplicates[$serial] = $systemsBySerial[$serial]
        }
    }
    
    Log-Message "[!] Found $($duplicates.Count) serial number(s) with duplicate entries." "WARNING" Yellow
    Log-Message "[i] Skipped $invalidSerials systems with invalid serial numbers." "INFO" Cyan
    return $duplicates
}

function Delete-System {
    param($SystemId, $Hostname)
    $uri = "$BASE_URL/systems/$SystemId"
    
    if ($DRY_RUN) {
        Log-Message "  [DRY RUN] Would delete: $Hostname (ID: $SystemId)" "INFO" Yellow
        return $true
    }
    
    try {
        Log-Message "  [ACTION] Deleting: $Hostname (ID: $SystemId)..." "WARNING" Yellow
        $response = Invoke-WebRequest -Uri $uri -Headers $HEADERS -Method Delete
        if ($response.StatusCode -in 200, 204) {
            Log-Message "  [SUCCESS] Deleted $Hostname." "INFO" Green
            return $true
        }
        else {
            Log-Message "  [FAILED] Unexpected status code $($response.StatusCode) for $Hostname." "ERROR" Red
            return $false
        }
    }
    catch {
        Log-Message "  [ERROR] Failed to delete $($Hostname): $_" "ERROR" Red
        return $false
    }
    finally {
        if (-not $DRY_RUN) { Start-Sleep -Milliseconds ($RATE_LIMIT_DELAY * 1000) }
    }
}

function Main {
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  JumpCloud Duplicate System Remover (PowerShell)  " -ForegroundColor Cyan -BackgroundColor White
    Write-Host "============================================================" -ForegroundColor Cyan
    
    $systems = Get-AllSystems
    if ($null -eq $systems) { exit 1 }
    
    $duplicateGroups = Find-Duplicates -Systems $systems
    if ($duplicateGroups.Count -eq 0) {
        Log-Message "No duplicates to process." "INFO" Green
        exit 0
    }

    if ($DRY_RUN) {
        Write-Host "`n*** STARTING DRY RUN MODE ***" -ForegroundColor Yellow -BackgroundColor Blue
    }
    else {
        Write-Host "`n! STARTING DELETION RUN - PERMANENT ACTION !" -ForegroundColor White -BackgroundColor Red
        $confirm = Read-Host "Are you absolutely sure you want to delete duplicates? (yes/no)"
        if ($confirm -ne "yes") {
            Log-Message "Operation cancelled by user." "INFO" Yellow
            exit 0
        }
    }

    $totalDeleted = 0
    $processedGroups = 0
    $totalGroups = $duplicateGroups.Count

    foreach ($serial in $duplicateGroups.Keys) {
        $processedGroups++
        $group = $duplicateGroups[$serial]
        Write-Host "`n[PROC] Processing Serial Number: $serial ($($group.Count) entries) - Group $processedGroups/$totalGroups" -ForegroundColor Cyan
        Write-Host ("-" * 60) -ForegroundColor Cyan
        
        # Sort systems by lastContact, newest first
        $sortedSystems = $group | Sort-Object { 
            if ([string]::IsNullOrEmpty($_.lastContact)) { [DateTime]::MinValue }
            else { [DateTime]::Parse($_.lastContact) }
        } -Descending
        
        $keep = $sortedSystems[0]
        $keepHostname = if ($keep.hostname) { $keep.hostname } else { $keep.displayName }
        Log-Message "  [KEEP] Keeping newest: $keepHostname (Last contact: $($keep.lastContact))" "INFO" Green
        
        for ($i = 1; $i -lt $sortedSystems.Count; $i++) {
            $system = $sortedSystems[$i]
            $hostname = if ($system.hostname) { $system.hostname } else { $system.displayName }
            if (Delete-System -SystemId $system.id -Hostname $hostname) {
                $totalDeleted++
            }
        }
    }

    Write-Host "`n============================================================" -ForegroundColor Cyan
    if ($DRY_RUN) {
        Log-Message "[DRY] Dry run finished. Would have deleted $totalDeleted device(s)." "INFO" Yellow
        Log-Message "[INFO] To run for real, use the -Delete switch: .\duplicate-remover.ps1 -Delete" "INFO" Cyan
    }
    else {
        Log-Message "[DONE] Deletion run finished. $totalDeleted device(s) deleted." "INFO" Green
    }
}

Main
