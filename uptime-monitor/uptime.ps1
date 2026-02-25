# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/

<#
.SYNOPSIS
    JumpCloud High Uptime Group Management Script

.DESCRIPTION
    Adds Mac computers with uptime > N days to a specified device group.
    Removes systems from the group when they no longer meet the criteria:
      - Uptime has dropped below the threshold (rebooted)
      - System is not a Mac
      - System has not contacted JumpCloud within the contact window

.PARAMETER GroupId
    JumpCloud device group ID to manage. If not supplied, you will be prompted.

.PARAMETER GroupName
    Display name for the group. If the group's current name differs, you will be
    offered the option to rename it.

.PARAMETER UptimeThresholdDays
    Number of days of uptime that qualifies a system as "high uptime". Default: 14.

.PARAMETER ContactWindowDays
    Systems that have not contacted JumpCloud within this many days are treated as
    stale and excluded. Default: 7.

.PARAMETER DryRun
    Show what would be added/removed without making any changes.

.PARAMETER MaxWorkers
    Maximum number of parallel runspace threads for uptime lookups. Default: 10.

.EXAMPLE
    .\uptime.ps1

.EXAMPLE
    .\uptime.ps1 -GroupId "abc123" -GroupName "High Uptime Macs" -DryRun
#>

[CmdletBinding()]
param(
    [string]$GroupId,
    [string]$GroupName,
    [int]$UptimeThresholdDays = 14,
    [int]$ContactWindowDays = 7,
    [switch]$DryRun,
    [int]$MaxWorkers = 10
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------
$API_KEY = $env:JUMPCLOUD_API_KEY
if ([string]::IsNullOrEmpty($API_KEY)) {
    Write-Host "Error: JUMPCLOUD_API_KEY environment variable is not set." -ForegroundColor Red
    Write-Host "Set it with: `$env:JUMPCLOUD_API_KEY = 'your_api_key'" -ForegroundColor Yellow
    exit 1
}

$BASE_URL = "https://console.jumpcloud.com/api"
$HEADERS = @{
    "x-api-key"    = $API_KEY
    "Content-Type" = "application/json"
    "Accept"       = "application/json"
}

# ---------------------------------------------------------------------------
# Simple adaptive rate limiter (shared state via a synchronized hashtable)
# ---------------------------------------------------------------------------
$Script:RateLimiter = [hashtable]::Synchronized(@{
        BaseDelay    = 0.1
        CurrentDelay = 0.1
        LastCall     = [datetime]::MinValue
        ErrorCount   = 0
        SuccessCount = 0
    })

function Wait-RateLimit {
    $rl = $Script:RateLimiter
    $wait = $rl.CurrentDelay - ([datetime]::UtcNow - $rl.LastCall).TotalSeconds
    if ($wait -gt 0) { Start-Sleep -Seconds $wait }
    $rl.LastCall = [datetime]::UtcNow
}

function Update-RateLimit {
    param([double]$ResponseSeconds, [bool]$IsError)
    $rl = $Script:RateLimiter
    if ($IsError) {
        $rl.ErrorCount++
        $rl.CurrentDelay = [Math]::Min($rl.CurrentDelay * 1.5, 2.0)
    }
    else {
        $rl.SuccessCount++
        if ($rl.SuccessCount -gt 3 -and $ResponseSeconds -lt 0.5 -and
            $rl.ErrorCount -lt $rl.SuccessCount * 0.1) {
            $rl.CurrentDelay = [Math]::Max($rl.BaseDelay, $rl.CurrentDelay * 0.9)
        }
        elseif ($ResponseSeconds -gt 2.0) {
            $rl.CurrentDelay = [Math]::Min($rl.CurrentDelay * 1.2, 1.0)
        }
    }
}

# ---------------------------------------------------------------------------
# HTTP helper with 429 retry
# ---------------------------------------------------------------------------
function Invoke-JCApi {
    param(
        [string]$Method,
        [string]$Uri,
        [hashtable]$Body = $null
    )

    $invokeParams = @{
        Method      = $Method
        Uri         = $Uri
        Headers     = $HEADERS
        ContentType = "application/json"
        TimeoutSec  = 30
        ErrorAction = "Stop"
    }
    if ($null -ne $Body) {
        $invokeParams["Body"] = ($Body | ConvertTo-Json -Depth 5)
    }

    $attempts = 0
    while ($attempts -lt 3) {
        Wait-RateLimit
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        try {
            # Invoke-RestMethod throws on 4xx/5xx — capture via StatusCode where needed
            $response = Invoke-RestMethod @invokeParams
            $sw.Stop()
            Update-RateLimit -ResponseSeconds $sw.Elapsed.TotalSeconds -IsError $false
            return $response
        }
        catch {
            $sw.Stop()
            $statusCode = $_.Exception.Response?.StatusCode.value__
            if ($statusCode -eq 429) {
                $attempts++
                Update-RateLimit -ResponseSeconds $sw.Elapsed.TotalSeconds -IsError $true
                Write-Host "  Rate limited (429) — waiting before retry $attempts/3..." -ForegroundColor Yellow
                Start-Sleep -Seconds ([Math]::Pow(2, $attempts))
            }
            else {
                Update-RateLimit -ResponseSeconds $sw.Elapsed.TotalSeconds -IsError $true
                throw
            }
        }
    }
    throw "Max retries exceeded for $Method $Uri"
}

# ---------------------------------------------------------------------------
# Group helpers
# ---------------------------------------------------------------------------
function Get-GroupName {
    param([string]$GId)
    try {
        $data = Invoke-JCApi -Method GET -Uri "$BASE_URL/v2/systemgroups/$GId"
        return $data.name
    }
    catch {
        Write-Host "  Warning: Could not retrieve group name — $_" -ForegroundColor Yellow
        return $null
    }
}

function Set-GroupName {
    param([string]$GId, [string]$NewName)
    try {
        Invoke-JCApi -Method PUT -Uri "$BASE_URL/v2/systemgroups/$GId" -Body @{ name = $NewName } | Out-Null
        Write-Host "  Group renamed to: $NewName" -ForegroundColor Green
        return $true
    }
    catch {
        Write-Host "  Warning: Could not rename group — $_" -ForegroundColor Yellow
        return $false
    }
}

# ---------------------------------------------------------------------------
# System fetch (paginated)
# ---------------------------------------------------------------------------
function Get-AllSystems {
    $systems = [System.Collections.Generic.List[object]]::new()
    $skip = 0
    $limit = 100
    $page = 0

    Write-Host "Fetching systems from JumpCloud..." -ForegroundColor Cyan

    do {
        $page++
        $uri = "$BASE_URL/systems?limit=$limit&skip=$skip"
        $data = Invoke-JCApi -Method GET -Uri $uri

        if ($null -eq $data.results -or $data.results.Count -eq 0) { break }

        $systems.AddRange($data.results)
        Write-Progress -Activity "Fetching systems" `
            -Status "Page $page — $($systems.Count) systems retrieved" `
            -PercentComplete ([Math]::Min(100, ($systems.Count / [Math]::Max(1, $data.totalCount)) * 100))

        $skip += $limit
    } while ($data.results.Count -eq $limit)

    Write-Progress -Activity "Fetching systems" -Completed
    Write-Host "Found $($systems.Count) total systems." -ForegroundColor Green
    return $systems
}

# ---------------------------------------------------------------------------
# Group membership
# ---------------------------------------------------------------------------
function Get-GroupMembers {
    param([string]$GId)

    $members = [System.Collections.Generic.List[string]]::new()
    $skip = 0
    $limit = 100

    Write-Host "Fetching current group members..." -ForegroundColor Cyan

    do {
        $uri = "$BASE_URL/v2/systemgroups/$GId/members?limit=$limit&skip=$skip"
        $data = Invoke-JCApi -Method GET -Uri $uri

        if ($null -eq $data -or $data.Count -eq 0) { break }

        foreach ($item in $data) {
            $sysId = if ($item.id) { $item.id }
            elseif ($item._id) { $item._id }
            elseif ($item.to) { $item.to.id }
            else { $null }
            $sysType = if ($item.type) { $item.type }
            elseif ($item.to) { $item.to.type }
            else { $null }
            if ($sysId -and $sysType -eq "system") { $members.Add($sysId) }
        }

        $skip += $limit
    } while ($data.Count -eq $limit)

    Write-Host "Found $($members.Count) systems currently in group." -ForegroundColor Green
    return [string[]]$members
}

# ---------------------------------------------------------------------------
# Uptime lookup (System Insights)
# ---------------------------------------------------------------------------
function Get-SystemUptime {
    param([string]$SystemId)
    try {
        $data = Invoke-JCApi -Method GET -Uri "$BASE_URL/v2/systeminsights/$SystemId/uptime"
        if ($data -and $data.Count -gt 0) { return [int]$data[0].days }
    }
    catch { }
    return $null
}

# ---------------------------------------------------------------------------
# Contact check
# ---------------------------------------------------------------------------
function Test-ContactedRecently {
    param([object]$System, [int]$Days)
    $lc = $System.lastContact
    if ([string]::IsNullOrEmpty($lc)) { return $false }
    try {
        $lcDate = [datetime]::Parse($lc).ToUniversalTime()
        $cutoff = ([datetime]::UtcNow).AddDays(-$Days)
        return $lcDate -ge $cutoff
    }
    catch { return $false }
}

# ---------------------------------------------------------------------------
# Uptime categorisation (parallel via runspaces)
# ---------------------------------------------------------------------------
function Get-SystemsByUptime {
    param(
        [object[]]$Systems,
        [int]$UptimeDays,
        [int]$ContactDays
    )

    # Only Mac systems
    $macSystems = $Systems | Where-Object { $_.os -eq "Mac OS X" }
    $excludedOther = $Systems | Where-Object { $_.os -ne "Mac OS X" }

    Write-Host "`nFound $($macSystems.Count) Mac systems. Excluded $($excludedOther.Count) non-Mac." -ForegroundColor Cyan
    Write-Host "Checking uptimes (threshold: $UptimeDays days)..." -ForegroundColor Cyan
    Write-Host ("-" * 70) -ForegroundColor Cyan

    $highUptime = [System.Collections.Generic.List[object]]::new()
    $lowUptime = [System.Collections.Generic.List[object]]::new()
    $stale = [System.Collections.Generic.List[object]]::new()
    $noData = [System.Collections.Generic.List[object]]::new()

    if ($macSystems.Count -eq 0) {
        Write-Host "No Mac systems to check." -ForegroundColor Yellow
        return $highUptime, $lowUptime, $stale, $noData
    }

    # Build runspace pool for parallel uptime lookups
    $pool = [System.Management.Automation.Runspaces.RunspaceFactory]::CreateRunspacePool(1, $MaxWorkers)
    $pool.Open()

    $scriptBlock = {
        param($SystemObj, $ApiKey, $BaseUrl, $Headers, $UptimeDaysP, $ContactDaysP)

        function CallApi($Uri) {
            $p = @{ Method = "GET"; Uri = $Uri; Headers = $Headers; TimeoutSec = 30; ErrorAction = "Stop" }
            return Invoke-RestMethod @p
        }

        $sysId = $SystemObj._id
        $lcRaw = $SystemObj.lastContact

        # Contact check
        if ([string]::IsNullOrEmpty($lcRaw)) { return @{ System = $SystemObj; Result = "stale"; UptimeDays = $null } }
        try {
            $lcDate = [datetime]::Parse($lcRaw).ToUniversalTime()
            $cutoff = ([datetime]::UtcNow).AddDays(-$ContactDaysP)
            if ($lcDate -lt $cutoff) { return @{ System = $SystemObj; Result = "stale"; UptimeDays = $null } }
        }
        catch { return @{ System = $SystemObj; Result = "stale"; UptimeDays = $null } }

        # Uptime lookup
        try {
            $uptimeData = CallApi "$BaseUrl/v2/systeminsights/$sysId/uptime"
            if ($uptimeData -and $uptimeData.Count -gt 0) {
                $days = [int]$uptimeData[0].days
                if ($days -gt $UptimeDaysP) { return @{ System = $SystemObj; Result = "high_uptime"; UptimeDays = $days } }
                else { return @{ System = $SystemObj; Result = "low_uptime"; UptimeDays = $days } }
            }
        }
        catch { }
        return @{ System = $SystemObj; Result = "no_data"; UptimeDays = $null }
    }

    $jobs = foreach ($sys in $macSystems) {
        $ps = [System.Management.Automation.PowerShell]::Create()
        $ps.RunspacePool = $pool
        $ps.AddScript($scriptBlock) `
            .AddArgument($sys) `
            .AddArgument($API_KEY) `
            .AddArgument($BASE_URL) `
            .AddArgument($HEADERS) `
            .AddArgument($UptimeDays) `
            .AddArgument($ContactDays) | Out-Null
        [pscustomobject]@{ PS = $ps; Handle = $ps.BeginInvoke() }
    }

    $completed = 0
    $total = $macSystems.Count
    foreach ($job in $jobs) {
        $r = $job.PS.EndInvoke($job.Handle)[0]
        $job.PS.Dispose()
        $completed++

        $sys = $r.System
        $hostname = $sys.hostname ?? "Unknown"
        $lc = $sys.lastContact ?? "Never"

        Write-Progress -Activity "Checking uptimes" `
            -Status "$completed / $total — $hostname" `
            -PercentComplete ([Math]::Round(($completed / $total) * 100))

        switch ($r.Result) {
            "stale" { $stale.Add($sys); Write-Host "[$completed/$total] $hostname — STALE (last: $lc)" -ForegroundColor Yellow }
            "no_data" { $noData.Add($sys); Write-Host "[$completed/$total] $hostname — no uptime data" -ForegroundColor Yellow }
            "high_uptime" { $highUptime.Add($sys); Write-Host "[$completed/$total] $hostname — HIGH uptime: $($r.UptimeDays) days" -ForegroundColor Yellow; $sys | Add-Member -NotePropertyName uptime_days -NotePropertyValue $r.UptimeDays -Force }
            "low_uptime" { $lowUptime.Add($sys); Write-Host "[$completed/$total] $hostname — low uptime (good): $($r.UptimeDays) days" -ForegroundColor Green; $sys | Add-Member -NotePropertyName uptime_days -NotePropertyValue $r.UptimeDays -Force }
        }
    }

    Write-Progress -Activity "Checking uptimes" -Completed
    $pool.Close(); $pool.Dispose()

    Write-Host ("-" * 70) -ForegroundColor Cyan
    Write-Host "`nSummary:" -ForegroundColor Cyan
    Write-Host "  High uptime (>$UptimeDays days) : $($highUptime.Count)" -ForegroundColor Cyan
    Write-Host "  Low uptime  (<=$UptimeDays days): $($lowUptime.Count)"  -ForegroundColor Cyan
    Write-Host "  Stale (>$ContactDays days silent): $($stale.Count)"     -ForegroundColor Cyan
    Write-Host "  No uptime data                  : $($noData.Count)"     -ForegroundColor Cyan

    return $highUptime, $lowUptime, $stale, $noData
}

# ---------------------------------------------------------------------------
# Identify group members to remove (parallel)
# ---------------------------------------------------------------------------
function Get-SystemsToRemove {
    param(
        [object[]]$AllSystems,
        [string[]]$GroupMemberIds,
        [int]$UptimeDays,
        [int]$ContactDays
    )

    $byId = @{}; foreach ($s in $AllSystems) { $byId[$s._id] = $s }
    $groupSystems = foreach ($id in $GroupMemberIds) {
        if ($byId.ContainsKey($id)) { $byId[$id] }
        else { Write-Host "  Warning: system $id in group but not in master list" -ForegroundColor Yellow }
    }

    $lowUptimeList = [System.Collections.Generic.List[object]]::new()
    $staleList = [System.Collections.Generic.List[object]]::new()
    $nonMacList = [System.Collections.Generic.List[object]]::new()

    if (-not $groupSystems) {
        Write-Host "No systems to check in group." -ForegroundColor Yellow
        return $lowUptimeList, $staleList, $nonMacList
    }

    Write-Host "`nChecking group members for systems to remove..." -ForegroundColor Cyan
    Write-Host ("-" * 70) -ForegroundColor Cyan

    $pool = [System.Management.Automation.Runspaces.RunspaceFactory]::CreateRunspacePool(1, $MaxWorkers)
    $pool.Open()

    $scriptBlock = {
        param($SystemObj, $ApiKey, $BaseUrl, $Headers, $UptimeDaysP, $ContactDaysP)

        $sysId = $SystemObj._id
        $hostname = if ($SystemObj.hostname) { $SystemObj.hostname } else { "Unknown" }
        $displayName = if ($SystemObj.displayName) { $SystemObj.displayName } else { "Unknown" }
        $osName = if ($SystemObj.os) { $SystemObj.os } else { "Unknown" }
        $lc = if ($SystemObj.lastContact) { $SystemObj.lastContact } else { "Never" }

        # Not a Mac
        if ($osName -ne "Mac OS X") {
            return @{ System = $SystemObj; Result = "non_mac";
                Message = "Not a Mac ($osName) — will remove" 
            }
        }

        # Stale contact check
        $isStale = $true
        if (-not [string]::IsNullOrEmpty($lc)) {
            try {
                $lcDate = [datetime]::Parse($lc).ToUniversalTime()
                $cutoff = ([datetime]::UtcNow).AddDays(-$ContactDaysP)
                if ($lcDate -ge $cutoff) { $isStale = $false }
            }
            catch { }
        }
        if ($isStale) {
            return @{ System = $SystemObj; Result = "stale";
                Message = "Stale (last: $lc) — will remove" 
            }
        }

        # Uptime check
        try {
            $p = @{ Method = "GET"; Uri = "$BaseUrl/v2/systeminsights/$sysId/uptime"; Headers = $Headers; TimeoutSec = 30; ErrorAction = "Stop" }
            $ud = Invoke-RestMethod @p
            if ($ud -and $ud.Count -gt 0) {
                $days = [int]$ud[0].days
                if ($days -le $UptimeDaysP) {
                    return @{ System = $SystemObj; Result = "low_uptime"; UptimeDays = $days;
                        Message = "Rebooted ($days days) — will remove" 
                    }
                }
                return @{ System = $SystemObj; Result = "keep"; UptimeDays = $days;
                    Message = "High uptime ($days days) — keep" 
                }
            }
        }
        catch { }

        return @{ System = $SystemObj; Result = "keep"; Message = "No uptime data — keep" }
    }

    $jobs = foreach ($sys in $groupSystems) {
        $ps = [System.Management.Automation.PowerShell]::Create()
        $ps.RunspacePool = $pool
        $ps.AddScript($scriptBlock) `
            .AddArgument($sys) `
            .AddArgument($API_KEY) `
            .AddArgument($BASE_URL) `
            .AddArgument($HEADERS) `
            .AddArgument($UptimeDays) `
            .AddArgument($ContactDays) | Out-Null
        [pscustomobject]@{ PS = $ps; Handle = $ps.BeginInvoke() }
    }

    $completed = 0
    $total = @($groupSystems).Count
    foreach ($job in $jobs) {
        $r = $job.PS.EndInvoke($job.Handle)[0]
        $job.PS.Dispose()
        $completed++

        $hostname = $r.System.hostname ?? "Unknown"
        Write-Progress -Activity "Checking group members" `
            -Status "$completed / $total — $hostname" `
            -PercentComplete ([Math]::Round(($completed / $total) * 100))

        $color = switch ($r.Result) {
            "keep" { "Green" }
            "low_uptime" { "Cyan" }
            default { "Yellow" }
        }
        Write-Host "  $hostname — $($r.Message)" -ForegroundColor $color

        if ($r.UptimeDays -ne $null) {
            $r.System | Add-Member -NotePropertyName uptime_days -NotePropertyValue $r.UptimeDays -Force
        }

        switch ($r.Result) {
            "low_uptime" { $lowUptimeList.Add($r.System) }
            "stale" { $staleList.Add($r.System) }
            "non_mac" { $nonMacList.Add($r.System) }
        }
    }

    Write-Progress -Activity "Checking group members" -Completed
    $pool.Close(); $pool.Dispose()

    return $lowUptimeList, $staleList, $nonMacList
}

# ---------------------------------------------------------------------------
# Add / Remove group members
# ---------------------------------------------------------------------------
function Add-SystemsToGroup {
    param([string[]]$SystemIds, [string]$GId, [System.Collections.Generic.HashSet[string]]$AlreadyIn)

    $added = 0
    $skipped = 0
    $errors = 0
    $i = 0

    foreach ($sysId in $SystemIds) {
        $i++
        Write-Progress -Activity "Adding systems" `
            -Status "$i / $($SystemIds.Count)" `
            -PercentComplete ([Math]::Round(($i / $SystemIds.Count) * 100))

        if ($AlreadyIn.Contains($sysId)) {
            Write-Host "  Skipping $sysId (already in group)" -ForegroundColor Cyan
            $skipped++
            continue
        }

        $payload = @{ op = "add"; type = "system"; id = $sysId }
        try {
            Invoke-JCApi -Method POST -Uri "$BASE_URL/v2/systemgroups/$GId/members" -Body $payload | Out-Null
            Write-Host "  Added $sysId" -ForegroundColor Green
            $added++
        }
        catch {
            Write-Host "  Failed to add $sysId — $_" -ForegroundColor Red
            $errors++
        }
    }

    Write-Progress -Activity "Adding systems" -Completed
    return $added, $skipped, $errors
}

function Remove-SystemsFromGroup {
    param([string[]]$SystemIds, [string]$GId)

    $removed = 0
    $errors = 0
    $i = 0

    foreach ($sysId in $SystemIds) {
        $i++
        Write-Progress -Activity "Removing systems" `
            -Status "$i / $($SystemIds.Count)" `
            -PercentComplete ([Math]::Round(($i / $SystemIds.Count) * 100))

        $payload = @{ op = "remove"; type = "system"; id = $sysId }
        try {
            Invoke-JCApi -Method POST -Uri "$BASE_URL/v2/systemgroups/$GId/members" -Body $payload | Out-Null
            Write-Host "  Removed $sysId" -ForegroundColor Green
            $removed++
        }
        catch {
            Write-Host "  Failed to remove $sysId — $_" -ForegroundColor Red
            $errors++
        }
    }

    Write-Progress -Activity "Removing systems" -Completed
    return $removed, $errors
}

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
$scriptStart = [datetime]::UtcNow

Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "JumpCloud High Uptime Group Management" -ForegroundColor Cyan
Write-Host "  Uptime threshold : $UptimeThresholdDays days" -ForegroundColor Cyan
Write-Host "  Contact window   : $ContactWindowDays days" -ForegroundColor Cyan
Write-Host "  Parallel workers : $MaxWorkers" -ForegroundColor Cyan
if ($DryRun) { Write-Host "  *** DRY RUN — no changes will be made ***" -ForegroundColor Yellow }
Write-Host ("=" * 70) -ForegroundColor Cyan

# Resolve group ID
if (-not $GroupId) {
    while ($true) {
        $GroupId = Read-Host "`nEnter the JumpCloud device group ID"
        if (-not [string]::IsNullOrWhiteSpace($GroupId)) {
            $confirm = Read-Host "Group ID: $GroupId — correct? (y/n)"
            if ($confirm.ToLower() -eq "y") { break }
        }
        else { Write-Host "Group ID cannot be empty." -ForegroundColor Red }
    }
}

# Fetch current group name
Write-Host "`nFetching group info..." -ForegroundColor Cyan
$currentGroupName = Get-GroupName -GId $GroupId
if ($currentGroupName) {
    Write-Host "  Current group name: $currentGroupName" -ForegroundColor Cyan
}
else {
    Write-Host "  Could not retrieve group name. Continuing..." -ForegroundColor Yellow
    $currentGroupName = "Unknown"
}

# Optionally rename the group
if ($GroupName -and $currentGroupName -ne $GroupName) {
    Write-Host "  Target group name : $GroupName" -ForegroundColor Cyan
    $renameChoice = Read-Host "Rename group from '$currentGroupName' to '$GroupName'? (y/n)"
    if ($renameChoice.ToLower() -eq "y" -and -not $DryRun) {
        Set-GroupName -GId $GroupId -NewName $GroupName
    }
    elseif ($DryRun) {
        Write-Host "  [DRY RUN] Would rename group to: $GroupName" -ForegroundColor Yellow
    }
}
elseif ($GroupName -eq $currentGroupName) {
    Write-Host "  Group name is already correct: $currentGroupName" -ForegroundColor Green
}

Write-Host ("=" * 70) -ForegroundColor Cyan

# Fetch all systems and group members
$allSystems = Get-AllSystems
$groupMembers = Get-GroupMembers -GId $GroupId
$groupMemberSet = [System.Collections.Generic.HashSet[string]]::new($groupMembers)

# Categorise systems by uptime
$highUptime, $lowUptime, $stale, $noData = Get-SystemsByUptime `
    -Systems $allSystems -UptimeDays $UptimeThresholdDays -ContactDays $ContactWindowDays

# Identify group members that should be removed
$lowUptimeInGroup, $staleInGroup, $nonMacInGroup = Get-SystemsToRemove `
    -AllSystems $allSystems -GroupMemberIds $groupMembers `
    -UptimeDays $UptimeThresholdDays -ContactDays $ContactWindowDays

# Compute add / remove sets
$highUptimeIds = [System.Collections.Generic.HashSet[string]]($highUptime | ForEach-Object { $_._id })
$lowUptimeInGroupIds = [System.Collections.Generic.HashSet[string]]($lowUptimeInGroup | ForEach-Object { $_._id })
$staleInGroupIds = [System.Collections.Generic.HashSet[string]]($staleInGroup | ForEach-Object { $_._id })
$nonMacInGroupIds = [System.Collections.Generic.HashSet[string]]($nonMacInGroup | ForEach-Object { $_._id })

$toAdd = [System.Collections.Generic.HashSet[string]]::new($highUptimeIds)
$toAdd.ExceptWith($groupMemberSet)

$toRemove = [System.Collections.Generic.HashSet[string]]::new($lowUptimeInGroupIds)
$toRemove.UnionWith($staleInGroupIds)
$toRemove.UnionWith($nonMacInGroupIds)

# Show action plan
Write-Host "`nActions needed:" -ForegroundColor Cyan
Write-Host "  Add    : $($toAdd.Count) system(s)" -ForegroundColor Cyan
Write-Host "  Remove : $($toRemove.Count) system(s)" -ForegroundColor Cyan
if ($toRemove.Count -gt 0) {
    Write-Host "    - Rebooted (low uptime) : $($lowUptimeInGroupIds.Count)" -ForegroundColor Cyan
    Write-Host "    - Non-Mac               : $($nonMacInGroupIds.Count)"    -ForegroundColor Cyan
    Write-Host "    - Stale                 : $($staleInGroupIds.Count)"     -ForegroundColor Cyan
}

if ($toAdd.Count -eq 0 -and $toRemove.Count -eq 0) {
    Write-Host "`nGroup is already up to date. No changes needed." -ForegroundColor Green
    exit 0
}

# Detail: systems to add
if ($toAdd.Count -gt 0) {
    Write-Host "`nSystems to ADD (high uptime, contacted recently, not in group):" -ForegroundColor Cyan
    foreach ($sys in $highUptime) {
        if ($toAdd.Contains($sys._id)) {
            Write-Host "  - $($sys.hostname ?? $sys._id) — $($sys.uptime_days) days uptime" -ForegroundColor Cyan
        }
    }
}

# Detail: systems to remove
if ($toRemove.Count -gt 0) {
    Write-Host "`nSystems to REMOVE:" -ForegroundColor Cyan
    if ($lowUptimeInGroup.Count -gt 0) {
        Write-Host "  Rebooted ($($lowUptimeInGroup.Count)):" -ForegroundColor Cyan
        foreach ($sys in $lowUptimeInGroup) {
            Write-Host "    - $($sys.hostname ?? $sys._id) — $($sys.uptime_days) days" -ForegroundColor Cyan
        }
    }
    if ($nonMacInGroup.Count -gt 0) {
        Write-Host "  Non-Mac ($($nonMacInGroup.Count)):" -ForegroundColor Cyan
        foreach ($sys in $nonMacInGroup) {
            Write-Host "    - $($sys.hostname ?? $sys._id) ($($sys.os))" -ForegroundColor Cyan
        }
    }
    if ($staleInGroup.Count -gt 0) {
        Write-Host "  Stale ($($staleInGroup.Count)):" -ForegroundColor Cyan
        foreach ($sys in $staleInGroup) {
            Write-Host "    - $($sys.hostname ?? $sys._id) (last: $($sys.lastContact))" -ForegroundColor Cyan
        }
    }
}

# ---------------------------------------------------------------------------
# Perform additions
# ---------------------------------------------------------------------------
$addedCount = 0
$skippedCount = 0
if ($toAdd.Count -gt 0) {
    Write-Host ("`n" + "=" * 70) -ForegroundColor Cyan
    Write-Host "Ready to ADD $($toAdd.Count) system(s)" -ForegroundColor Cyan

    if ($DryRun) {
        Write-Host "[DRY RUN] Skipping additions." -ForegroundColor Yellow
    }
    else {
        $confirmAdd = Read-Host "Add these systems? (y/n)"
        if ($confirmAdd.ToLower() -eq "y") {
            $addedCount, $skippedCount, $addErrors = Add-SystemsToGroup `
                -SystemIds ([string[]]$toAdd) -GId $GroupId -AlreadyIn $groupMemberSet
            Write-Host "Added $addedCount / $($toAdd.Count) (skipped $skippedCount, errors $addErrors)" -ForegroundColor Green
        }
        else { Write-Host "Skipped additions." -ForegroundColor Yellow }
    }
}

# ---------------------------------------------------------------------------
# Perform removals
# ---------------------------------------------------------------------------
$removedCount = 0
if ($toRemove.Count -gt 0) {
    Write-Host ("`n" + "=" * 70) -ForegroundColor Cyan
    Write-Host "Ready to REMOVE $($toRemove.Count) system(s)" -ForegroundColor Cyan

    if ($DryRun) {
        Write-Host "[DRY RUN] Skipping removals." -ForegroundColor Yellow
    }
    else {
        $confirmRemove = Read-Host "Remove these systems? (y/n)"
        if ($confirmRemove.ToLower() -eq "y") {
            $removedCount, $removeErrors = Remove-SystemsFromGroup `
                -SystemIds ([string[]]$toRemove) -GId $GroupId
            Write-Host "Removed $removedCount / $($toRemove.Count) (errors $removeErrors)" -ForegroundColor Green
        }
        else { Write-Host "Skipped removals." -ForegroundColor Yellow }
    }
}

# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------
$elapsed = ([datetime]::UtcNow - $scriptStart).TotalSeconds
Write-Host ("`n" + "=" * 70) -ForegroundColor Cyan
Write-Host "Operation complete!" -ForegroundColor Green
Write-Host "  Added       : $addedCount"   -ForegroundColor Cyan
Write-Host "  Skipped     : $skippedCount" -ForegroundColor Cyan
Write-Host "  Removed     : $removedCount" -ForegroundColor Cyan
Write-Host "  Total time  : $([Math]::Round($elapsed, 1))s" -ForegroundColor Cyan
Write-Host "  Rate limiter: $([Math]::Round($Script:RateLimiter.CurrentDelay * 1000))ms delay" -ForegroundColor Cyan
Write-Host "  API success : $($Script:RateLimiter.SuccessCount) / $($Script:RateLimiter.SuccessCount + $Script:RateLimiter.ErrorCount)" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
