#Requires -Version 5.1
# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/

<#
.SYNOPSIS
    Network Configuration Audit Script
.DESCRIPTION
    Detects unusual network setups and reports on DNS, proxies, and VPN configurations
.EXAMPLE
    .\network-audit.ps1
.NOTES
    Requires MDM_API_KEY environment variable to be set
#>

[CmdletBinding()]
param()

# Color codes
$ColorSuccess = "Green"
$ColorError = "Red"
$ColorWarning = "Yellow"
$ColorInfo = "Cyan"

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$ForegroundColor = "White"
    )
    Write-Host $Message -ForegroundColor $ForegroundColor
}

function Get-APIKey {
    $apiKey = $env:JUMPCLOUD_API_KEY
    if (-not $apiKey) {
        Write-ColorOutput "Error: JUMPCLOUD_API_KEY environment variable is not set" $ColorError
        Write-ColorOutput "Please set it using: `$env:JUMPCLOUD_API_KEY = 'your_api_key'" $ColorInfo
        exit 1
    }
    return $apiKey
}

function Get-AllSystems {
    param([string]$APIKey)
    
    $headers = @{
        "x-api-key" = $APIKey
        "Content-Type" = "application/json"
    }
    
    $allSystems = @()
    $skip = 0
    $limit = 100
    
    while ($true) {
        $uri = "https://console.jumpcloud.com/api/systems?limit=$limit&skip=$skip"
        
        try {
            $response = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get -ErrorAction Stop
            
            if (-not $response.results) {
                break
            }
            
            $allSystems += $response.results
            $skip += $limit
            
            if ($skip -ge $response.totalCount) {
                break
            }
        }
        catch {
            Write-ColorOutput "Error fetching systems: $_" $ColorError
            break
        }
    }
    
    return $allSystems
}

function Get-SystemInsights {
    param(
        [string]$APIKey,
        [string]$SystemID
    )
    
    $headers = @{
        "x-api-key" = $APIKey
        "Content-Type" = "application/json"
    }
    
    $uri = "https://console.jumpcloud.com/api/systems/$SystemID/insights"
    
    try {
        $response = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get -ErrorAction Stop
        return $response
    }
    catch {
        Write-ColorOutput "Warning: Could not fetch insights for system $SystemID" $ColorWarning
        return @{}
    }
}

function Extract-NetworkInfo {
    param([hashtable]$Insights)
    
    $networkInfo = @{
        'dnsServers' = @()
        'proxyEnabled' = $false
        'proxyConfig' = ''
        'vpnConnections' = @()
        'networkInterfaces' = @()
    }
    
    # Extract network interfaces and DNS
    if ($Insights.networkInterfaces) {
        foreach ($iface in $Insights.networkInterfaces) {
            $networkInfo['networkInterfaces'] += @{
                'name' = $iface.name
                'type' = $iface.type
                'ipAddress' = $iface.ipAddress
                'status' = $iface.status
            }
            
            if ($iface.dnsServers) {
                $networkInfo['dnsServers'] += $iface.dnsServers
            }
        }
    }
    
    # Check proxy settings
    if ($Insights.proxySettings) {
        $networkInfo['proxyEnabled'] = $true
        $networkInfo['proxyConfig'] = $Insights.proxySettings | ConvertTo-Json -Compress
    }
    
    # Extract VPN connections
    if ($Insights.vpnConnections) {
        $networkInfo['vpnConnections'] = $Insights.vpnConnections
    }
    
    # Deduplicate DNS servers
    $networkInfo['dnsServers'] = @($networkInfo['dnsServers'] | Select-Object -Unique)
    
    return $networkInfo
}

function Test-CustomDNS {
    param([array]$DNSServers)
    
    $standardDNS = @('8.8.8.8', '8.8.4.4', '1.1.1.1', '1.0.0.1', '208.67.222.222', '208.67.220.220')
    
    foreach ($dns in $DNSServers) {
        if ($dns -and $standardDNS -notcontains $dns) {
            return $true
        }
    }
    
    return $false
}

function Analyze-NetworkConfig {
    param(
        [hashtable]$System,
        [string]$APIKey
    )
    
    $systemID = $System._id
    $hostname = $System.hostname
    
    $insights = Get-SystemInsights -APIKey $APIKey -SystemID $systemID
    $networkInfo = Extract-NetworkInfo -Insights $insights
    
    $issues = @()
    
    # Check for custom DNS
    if ($networkInfo['dnsServers'].Count -gt 0) {
        if (Test-CustomDNS -DNSServers $networkInfo['dnsServers']) {
            $issues += "Custom DNS configured: $($networkInfo['dnsServers'] -join ', ')"
        }
    }
    
    # Check for proxy
    if ($networkInfo['proxyEnabled']) {
        $issues += "Proxy enabled: $($networkInfo['proxyConfig'])"
    }
    
    # Check for VPN connections
    if ($networkInfo['vpnConnections'].Count -gt 0) {
        $vpnNames = $networkInfo['vpnConnections'] | ForEach-Object { $_.name }
        $issues += "VPN connections: $($vpnNames -join ', ')"
    }
    
    return @{
        'Hostname' = $hostname
        'SystemID' = $systemID
        'DNSServers' = if ($networkInfo['dnsServers'].Count -gt 0) { $networkInfo['dnsServers'] -join ', ' } else { 'Standard' }
        'ProxyEnabled' = if ($networkInfo['proxyEnabled']) { 'Yes' } else { 'No' }
        'VPNConnections' = if ($networkInfo['vpnConnections'].Count -gt 0) { ($networkInfo['vpnConnections'] | ForEach-Object { $_.name }) -join ', ' } else { 'None' }
        'NetworkInterfaces' = $networkInfo['networkInterfaces'].Count
        'Issues' = if ($issues.Count -gt 0) { $issues -join '; ' } else { 'None' }
    }
}

function Main {
    $apiKey = Get-APIKey
    
    Write-ColorOutput "🔍 Network Configuration Audit" $ColorInfo
    Write-ColorOutput "=" * 80 $ColorInfo
    Write-ColorOutput "`nFetching all systems from JumpCloud..." $ColorInfo
    
    $systems = Get-AllSystems -APIKey $apiKey
    
    if (-not $systems) {
        Write-ColorOutput "No systems found or error occurred" $ColorError
        exit 1
    }
    
    Write-ColorOutput "Found $($systems.Count) total systems" $ColorSuccess
    
    # Filter for Mac systems only
    $macSystems = @($systems | Where-Object { $_.os -eq 'Mac OS X' })
    Write-ColorOutput "Analyzing $($macSystems.Count) macOS systems...`n" $ColorInfo
    
    # Analyze each Mac system
    $auditResults = @()
    $systemsWithIssues = @()
    
    for ($i = 0; $i -lt $macSystems.Count; $i++) {
        $system = $macSystems[$i]
        $hostname = $system.hostname
        Write-Host -NoNewline "`rAnalyzing ($($i + 1)/$($macSystems.Count)) $($hostname.Substring(0, [Math]::Min(40, $hostname.Length)))" -ForegroundColor $ColorInfo
        
        $result = Analyze-NetworkConfig -System $system -APIKey $apiKey
        $auditResults += $result
        
        if ($result['Issues'] -ne 'None') {
            $systemsWithIssues += $result
        }
    }
    
    Write-Host "`n"
    
    # Generate output filename
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $outputFile = "network_audit_results_$timestamp.csv"
    
    # Export to CSV
    if ($auditResults.Count -gt 0) {
        $auditResults | Export-Csv -Path $outputFile -NoTypeInformation -Encoding UTF8
        
        Write-ColorOutput "`n✅ Network Configuration Audit Complete!" $ColorSuccess
        Write-ColorOutput "Results saved to: $outputFile" $ColorSuccess
        Write-ColorOutput "`nScanned $($macSystems.Count) macOS systems" $ColorInfo
        
        # Summary table
        Write-ColorOutput "`n" + "=" * 100 $ColorInfo
        Write-ColorOutput "SYSTEMS WITH UNUSUAL NETWORK CONFIGURATION" $ColorWarning
        Write-ColorOutput "=" * 100 $ColorInfo
        
        if ($systemsWithIssues.Count -gt 0) {
            Write-Host ("{0,-30} {1,-25} {2,-10} {3,-15} {4,-20}" -f "HOSTNAME", "DNS SERVERS", "PROXY", "VPN", "ISSUES")
            Write-Host "-" * 100
            
            foreach ($result in $systemsWithIssues) {
                Write-Host ("{0,-30} {1,-25} {2,-10} {3,-15} {4,-20}" -f `
                    $result['Hostname'].Substring(0, [Math]::Min(30, $result['Hostname'].Length)),
                    $result['DNSServers'].Substring(0, [Math]::Min(25, $result['DNSServers'].Length)),
                    $result['ProxyEnabled'].Substring(0, [Math]::Min(10, $result['ProxyEnabled'].Length)),
                    $result['VPNConnections'].Substring(0, [Math]::Min(15, $result['VPNConnections'].Length)),
                    $result['Issues'].Substring(0, [Math]::Min(20, $result['Issues'].Length)))
            }
        }
        else {
            Write-ColorOutput "✅ No unusual network configurations detected!" $ColorSuccess
        }
        
        Write-ColorOutput "=" * 100 $ColorInfo
        Write-ColorOutput "`nSummary: $($systemsWithIssues.Count) systems with unusual network configuration out of $($macSystems.Count) scanned" $ColorInfo
    }
    else {
        Write-ColorOutput "No results to export" $ColorError
    }
    
    Write-ColorOutput "`nScript completed!" $ColorSuccess
}

# Run main function
Main
