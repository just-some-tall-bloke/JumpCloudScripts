# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/
# JumpCloud macOS Version Audit

Exports Mac systems below a specified macOS version to CSV format with primary user information.

## Purpose

This PowerShell script exports all Mac systems running below a specified macOS version to a CSV file, including system details and primary user information for compliance tracking and reporting.

## Features

- **Version Filtering**: Filters Mac systems below target macOS version
- **Primary User Resolution**: Fetches primary user usernames for each system
- **Recent Activity Filter**: Optionally filters by last contact date
- **CSV Export**: Exports to formatted CSV with comprehensive system details
- **Progress Tracking**: Shows real-time progress during system processing
- **Interactive Input**: Prompts for version and date filtering parameters

## Requirements

- PowerShell 5.1+ (Windows PowerShell or PowerShell Core)
- JumpCloud API key (set as environment variable `JUMPCLOUD_API_KEY`)
- Network connectivity to JumpCloud API

## Usage

### Method 1: Set API Key Environment Variable
```powershell
$env:JUMPCLOUD_API_KEY = 'your_api_key_here'
.\macos-version-audit.ps1
```

### Method 2: Persistent Environment Variable
```powershell
[System.Environment]::SetEnvironmentVariable('JUMPCLOUD_API_KEY', 'your_api_key', 'User')
# Restart PowerShell, then run:
.\macos-version-audit.ps1
```

## Interactive Prompts

When run, the script will prompt for:

1. **Target macOS Version**: Default is "15.7.0"
2. **Last Contact Days**: Default is 7 days (only systems active within this period)

## CSV Output

The script generates a CSV file with the following columns:
- `Hostname`: System hostname
- `DisplayName`: Display name in JumpCloud
- `MacOSVersion`: Current macOS version
- `SerialNumber`: Device serial number
- `PrimaryUsername`: Primary user's username (if available)
- `PrimaryUserID`: JumpCloud user ID (if available)
- `SystemID`: JumpCloud system ID
- `LastContact`: Last contact timestamp
- `Active`: Active status in JumpCloud

### Output File Naming
Format: `mac_systems_below_{version}_last_{days}_days.csv`

Example: `mac_systems_below_15_7_0_last_7_days.csv`

## Version Comparison Logic

The script uses semantic version comparison:
- Compares major, minor, and patch versions sequentially
- Returns `true` if system version < target version

Examples:
- 14.5.0 < 15.7.0 → Included
- 15.6.1 < 15.7.0 → Included  
- 15.7.0 = 15.7.0 → Not included
- 15.8.2 > 15.7.0 → Not included

## Example Output

```
Fetching all systems from JumpCloud...
Found 1250 total systems

Found Mac below 15.7.0: MacBook-Pro-01 (v14.6.1) - Last seen: 2024-01-15
Found Mac below 15.7.0: iMac-Dept-05 (v14.5.0) - Last seen: 2024-01-14
...

Export complete!
Found 45 Mac systems below macOS 15.7.0 (active in last 7 days)
Results saved to: mac_systems_below_15_7_0_last_7_days.csv

Summary of systems found:

Hostname       MacOSVersion PrimaryUsername LastContact
----------       ------------- --------------- -----------
MacBook-Pro-01  14.6.1       john.doe        2024-01-15
iMac-Dept-05    14.5.0       jane.smith      2024-01-14
```

## Use Cases

### Compliance Reporting
- Generate reports for security audits
- Track macOS version compliance across the fleet
- Identify systems needing OS upgrades

### User Communication
- Export lists for targeted user notifications
- Create reports for department heads
- Support IT planning and budgeting

### Migration Planning
- Identify systems for phased OS upgrades
- Track upgrade progress over time
- Plan hardware refresh cycles

## Error Handling

- **Missing API Key**: Clear error message with setup instructions
- **Network Issues**: Graceful handling of API timeouts
- **Missing Users**: Handles cases where primary user lookup fails
- **Version Parsing**: Robust version comparison logic

## Performance Considerations

- **Pagination**: Automatically handles large device fleets via pagination
- **Rate Limiting**: Built-in delays to avoid API throttling  
- **Progress Display**: Real-time progress bars for long operations
- **User Lookup**: Caches user data to minimize redundant API calls

## Troubleshooting

1. **API Key Issues**:
   ```powershell
   # Check if environment variable is set
   $env:JUMPCLOUD_API_KEY
   ```

2. **Permission Errors**: Verify API key has read permissions for systems and users

3. **Network Connectivity**: Test connectivity to `console.jumpcloud.com`

4. **Version Format**: Use semantic versioning (e.g., 15.7.0, not just 15)

## Customization

You can modify the script to:
- Change default version thresholds
- Add additional filtering criteria
- Include extra system properties
- Modify output file format
- Add email notification functionality
