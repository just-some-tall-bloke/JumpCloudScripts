# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/

# JumpCloud API Script to export Macs below a specified macOS version with primary user
# Outputs CSV with system details and primary user username

# Get API key from environment variable
$API_KEY = $env:JUMPCLOUD_API_KEY

if ([string]::IsNullOrEmpty($API_KEY)) {
    Write-Host "Error: JUMPCLOUD_API_KEY environment variable is not set" -ForegroundColor Red
    Write-Host "Please set it using: `$env:JUMPCLOUD_API_KEY = 'your_api_key'" -ForegroundColor Yellow
    Write-Host "Or for persistent setting: [System.Environment]::SetEnvironmentVariable('JUMPCLOUD_API_KEY', 'your_api_key', 'User')" -ForegroundColor Yellow
    exit 1
}

# Get target macOS version from user
$targetVersion = Read-Host "Enter the macOS version to check against (e.g., 15.7.0)"
if ([string]::IsNullOrEmpty($targetVersion)) {
    $targetVersion = "15.7.0"
    Write-Host "Using default version: $targetVersion" -ForegroundColor Yellow
}

# Get number of days for last contact filter
$daysInput = Read-Host "Enter number of days for last contact filter (e.g., 7)"
if ([string]::IsNullOrEmpty($daysInput)) {
    $days = 7
    Write-Host "Using default: 7 days" -ForegroundColor Yellow
}
else {
    try {
        $days = [int]$daysInput
    }
    catch {
        Write-Host "Invalid days input, using default: 7 days" -ForegroundColor Red
        $days = 7
    }
}

# Output file
$OUTPUT_FILE = "mac_systems_below_$($targetVersion.Replace('.','_'))_last_${days}_days.csv"

# Function to get all systems with pagination
function Get-AllSystems {
    $skip = 0
    $limit = 100
    $allSystems = @()
    
    while ($true) {
        $headers = @{
            "x-api-key" = $API_KEY
            "Content-Type" = "application/json"
        }
        
        $uri = "https://console.jumpcloud.com/api/systems?limit=$limit&skip=$skip"
        
        try {
            $response = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get
            
            if ($null -eq $response.results -or $response.results.Count -eq 0) {
                break
            }
            
            $allSystems += $response.results
            $skip += $limit
            
            # Check if we've retrieved all systems
            if ($skip -ge $response.totalCount) {
                break
            }
        }
        catch {
            Write-Host "Error fetching systems: $_" -ForegroundColor Red
            break
        }
    }
    
    return $allSystems
}

# Function to get user details by ID
function Get-UserById {
    param(
        [string]$userId
    )
    
    if ([string]::IsNullOrEmpty($userId)) {
        return ""
    }
    
    $headers = @{
        "x-api-key" = $API_KEY
        "Content-Type" = "application/json"
    }
    
    $uri = "https://console.jumpcloud.com/api/systemusers/$userId"
    
    try {
        $response = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get
        return $response.username
    }
    catch {
        Write-Host "Warning: Could not fetch user $userId" -ForegroundColor Yellow
        return ""
    }
}

# Function to compare version numbers
function Compare-MacOSVersion {
    param(
        [string]$version1,
        [string]$comparisonVersion
    )
    
    try {
        # Parse version strings
        $v1Parts = $version1.Split('.')
        $v2Parts = $comparisonVersion.Split('.')
        
        # Pad arrays to same length
        $maxLength = [Math]::Max($v1Parts.Length, $v2Parts.Length)
        
        for ($i = 0; $i -lt $maxLength; $i++) {
            $v1Val = if ($i -lt $v1Parts.Length) { [int]$v1Parts[$i] } else { 0 }
            $v2Val = if ($i -lt $v2Parts.Length) { [int]$v2Parts[$i] } else { 0 }
            
            if ($v1Val -lt $v2Val) {
                return $true  # version1 is less than target
            }
            elseif ($v1Val -gt $v2Val) {
                return $false  # version1 is greater than target
            }
        }
        
        return $false  # versions are equal
    }
    catch {
        # If we can't parse the version, assume it doesn't meet criteria
        return $false
    }
}

Write-Host "Fetching all systems from JumpCloud..." -ForegroundColor Cyan
$systems = Get-AllSystems

if ($systems.Count -eq 0) {
    Write-Host "No systems found or error occurred" -ForegroundColor Red
    exit 1
}

Write-Host "Found $($systems.Count) total systems" -ForegroundColor Green

# Filter for Mac systems below target version
$macSystemsBelowTarget = @()
$processedCount = 0
$cutoffDate = (Get-Date).AddDays(-$days)

foreach ($system in $systems) {
    $processedCount++
    Write-Progress -Activity "Processing systems" -Status "$processedCount of $($systems.Count)" -PercentComplete (($processedCount / $systems.Count) * 100)
    
    # Check if it's a Mac
    if ($system.os -eq "Mac OS X") {
        # Check version
        if (![string]::IsNullOrEmpty($system.version)) {
            if (Compare-MacOSVersion -version1 $system.version -comparisonVersion $targetVersion) {
                # Check last contact date (within specified days)
                try {
                    $lastContactDate = [DateTime]::Parse($system.lastContact)
                }
                catch {
                    continue  # Skip if we can't parse the date
                }
                if ($lastContactDate -lt $cutoffDate) {
                    continue  # Skip systems not contacted within specified days
                }
                
                Write-Host "Found Mac below $($targetVersion): $($system.hostname) (v$($system.version)) - Last seen: $($lastContactDate.ToString('yyyy-MM-dd'))" -ForegroundColor Yellow
                
                # Get primary user username if exists
                $primaryUsername = ""
                if (![string]::IsNullOrEmpty($system.primaryUser)) {
                    $primaryUsername = Get-UserById -userId $system.primaryUser
                }
                
                # Create custom object for CSV
                $macSystemsBelowTarget += [PSCustomObject]@{
                    Hostname = $system.hostname
                    DisplayName = $system.displayName
                    MacOSVersion = $system.version
                    SerialNumber = $system.serialNumber
                    PrimaryUsername = $primaryUsername
                    PrimaryUserID = $system.primaryUser
                    SystemID = $system._id
                    LastContact = $system.lastContact
                    Active = $system.active
                }
            }
        }
    }
}

Write-Progress -Activity "Processing systems" -Completed

if ($macSystemsBelowTarget.Count -gt 0) {
    # Export to CSV
    $macSystemsBelowTarget | Export-Csv -Path $OUTPUT_FILE -NoTypeInformation
    
    Write-Host "`nExport complete!" -ForegroundColor Green
    Write-Host "Found $($macSystemsBelowTarget.Count) Mac systems below macOS $targetVersion (active in last $days days)" -ForegroundColor Green
    Write-Host "Results saved to: $OUTPUT_FILE" -ForegroundColor Green
    
    # Display summary
    Write-Host "`nSummary of systems found:" -ForegroundColor Cyan
    $macSystemsBelowTarget | Format-Table -Property Hostname, MacOSVersion, PrimaryUsername, LastContact -AutoSize
}
else {
    Write-Host "`nNo Mac systems found below macOS $targetVersion that were active in the last $days days" -ForegroundColor Yellow
}

Write-Host "`nScript completed!" -ForegroundColor Green
