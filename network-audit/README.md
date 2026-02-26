# Network Configuration Audit

A JumpCloud management script that detects unusual network setups and reports on DNS, proxy, and VPN configurations.

## Purpose

This script helps monitor network configurations across your macOS fleet by:
- Reporting on custom DNS settings or unauthorized proxy configurations
- Listing active network interfaces and their status
- Detecting VPN connections
- Identifying systems with non-standard network setup
- Exporting detailed audit results to CSV for reporting and analysis

## Key Features

- **DNS Audit**: Detects custom/non-standard DNS configurations
- **Proxy Detection**: Identifies systems with proxy settings enabled
- **VPN Monitoring**: Lists active VPN connections on systems
- **Network Interface Listing**: Shows all active network interfaces
- **CSV Export**: Comprehensive audit results for reporting
- **Colorized Output**: Easy-to-read console output with status indicators
- **Progress Tracking**: Real-time progress updates during scanning

## Requirements

### Python Script
- Python 3.7+
- JumpCloud API key (set as `JUMPCLOUD_API_KEY` environment variable)
- `requests` library
- `colorama` library (optional, for colored output)

### PowerShell Script
- PowerShell 5.1+ or PowerShell Core
- JumpCloud API key (set as `JUMPCLOUD_API_KEY` environment variable)

## Installation

### Python

```bash
pip install -r requirements.txt
```

## Usage

### Python Script

```bash
python3 network-audit.py
```

### PowerShell Script

```powershell
$env:JUMPCLOUD_API_KEY = 'your_api_key_here'
.\network-audit.ps1
```

## How It Works

1. **Fetches all systems** from the JumpCloud API
2. **Filters for macOS systems** only (OS = "Mac OS X")
3. **Retrieves system insights** for each Mac including network configuration
4. **Analyzes network settings** for:
   - DNS servers (identifies custom vs. standard DNS)
   - Proxy configurations
   - Active VPN connections
   - Network interfaces
5. **Generates reports** with detailed findings
6. **Exports results** to CSV with timestamp in filename

## Understanding the Output

### Console Output

The script displays:
- Total systems found
- Number of macOS systems analyzed
- Real-time progress during scanning
- Summary table of systems with unusual network configurations
- Count of systems with issues vs. total scanned

### CSV Output File

The generated `network_audit_results_YYYYMMDD_HHMMSS.csv` contains:

| Column | Description |
|--------|-------------|
| Hostname | System hostname |
| SystemID | JumpCloud system ID |
| DNSServers | Configured DNS servers or "Standard" |
| ProxyEnabled | Yes/No indicator for proxy configuration |
| VPNConnections | List of VPN connections or "None" |
| NetworkInterfaces | Count of network interfaces |
| Issues | Summary of detected issues or "None" |

### Issue Detection

The script flags the following as unusual configurations:
- **Custom DNS**: Any DNS server not in the standard list (Google, Cloudflare, OpenDNS)
- **Proxy Enabled**: Any system with proxy settings configured
- **VPN Connections**: Any active VPN connections

## Standard DNS Servers (Not Flagged)

- 8.8.8.8, 8.8.4.4 (Google)
- 1.1.1.1, 1.0.0.1 (Cloudflare)
- 208.67.222.222, 208.67.220.220 (OpenDNS)

## Notes

- This script queries the JumpCloud System Insights API
- Network configuration data is aggregated from managed systems
- The script only analyzes macOS systems (filtering by OS = "Mac OS X")
- In production, consider scheduling this script to run regularly (daily/weekly) via cron or Task Scheduler
- CSV export includes all systems, even those with no unusual configurations

## Environment Variables

- `JUMPCLOUD_API_KEY` - **Required**. Your JumpCloud API key for authentication

## Troubleshooting

### "Error: JUMPCLOUD_API_KEY environment variable is not set"
Set your API key:
```bash
export JUMPCLOUD_API_KEY='your_api_key_here'
```

### "No systems found or error occurred"
- Verify your API key is correct and has sufficient permissions
- Check your JumpCloud API key has Systems API access
- Ensure at least one macOS system is enrolled in JumpCloud

### "Warning: Could not fetch insights for system"
This is non-fatal. The script will continue and mark that system with minimal data. This can occur if:
- The system recently enrolled and hasn't sent insights yet
- Network connectivity issues with the managed system
- System insights not available for that system type

## Example Output

```
🔍 Network Configuration Audit
================================================================================

Fetching all systems from JumpCloud...
Found 125 total systems
Analyzing 95 macOS systems...

Analyzing (95/95) MacBook-Pro-Employee-50

✅ Network Configuration Audit Complete!
Results saved to: network_audit_results_20240115_143022.csv

Scanned 95 macOS systems

====================================================================================================
SYSTEMS WITH UNUSUAL NETWORK CONFIGURATION
====================================================================================================
HOSTNAME                       DNS SERVERS               PROXY      VPN             ISSUES
----------------------------------------------------------------------------------------------------
MacBook-Pro-01                 192.168.1.1              Yes        Cisco AnyConnect Custom DNS configured: 192.168.1.1; Proxy enabled: {...}; VPN connections: Cisco AnyConnect
iMac-Engineering-02            10.0.0.1                 No         None            Custom DNS configured: 10.0.0.1
====================================================================================================

Summary: 2 systems with unusual network configuration out of 95 scanned

Script completed!
```

## License

This script is provided for JumpCloud MDM management. Ensure compliance with:
- JumpCloud API terms of service
- Your organization's security policies
- Applicable data protection regulations
