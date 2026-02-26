# Timezone/Region Sync Auditor

A JumpCloud management script that ensures fleet consistency for calendaring and logs by auditing timezone and time synchronization settings.

## Purpose

This script helps maintain a compliant macOS fleet by:
- Detecting devices with "Set time zone automatically" disabled
- Auditing for drastic clock drift (which can break JumpCloud API authentication)
- Identifying systems that need time synchronization attention
- Optionally sending alerts to users via the Broadcaster system

## Key Features

- **Timezone Auto-Sync Detection**: Identifies systems that don't use automatic timezone setting
- **Clock Drift Analysis**: Detects systems with excessive time drift from NTP servers
- **Dry-Run Mode**: Preview changes before applying them
- **Broadcaster Integration**: Send alerts to users about timezone issues
- **Group Management**: Automatically add non-compliant systems to a JumpCloud device group
- **CSV Export**: Export audit results for reporting and analysis

## Requirements

- Python 3.x
- JumpCloud API key (set as `JUMPCLOUD_API_KEY` environment variable)
- `requests` library

### Installation

```bash
pip install -r requirements.txt
```

## Usage

### Basic Audit (Dry-Run)

```bash
python3 timezone-region-sync.py
```

This will audit all systems for timezone issues without making any changes.

### Apply Changes

Add the `--apply` flag to actually make changes:

```bash
python3 timezone-region-sync.py --apply
```

### Common Options

```bash
# Set maximum allowed clock drift (in seconds, default: 300)
python3 timezone-region-sync.py --max-drift 600

# Add non-compliant systems to a JumpCloud group
python3 timezone-region-sync.py --group-id <GROUP_ID> --apply

# Send Broadcaster alerts to affected systems
python3 timezone-region-sync.py --send-alerts --apply

# Export results to CSV
python3 timezone-region-sync.py --csv results.csv

# Combine multiple options
python3 timezone-region-sync.py --max-drift 600 --group-id <GROUP_ID> --send-alerts --csv report.csv --apply
```

## How It Works

1. **Fetches all systems** from the JumpCloud API
2. **Retrieves timezone/time data** from System Insights
3. **Analyzes each system** for:
   - Automatic timezone synchronization status
   - Current system timezone configuration
   - Clock drift against NTP time servers
4. **Reports findings** with a summary table
5. **Optionally applies actions**:
   - Adds non-compliant systems to a specified group
   - Sends Broadcaster alerts to affected systems
   - Exports results to CSV

## Clock Drift Threshold

The `--max-drift` parameter (default: 300 seconds / 5 minutes) controls how much time drift is acceptable. Systems exceeding this threshold will be flagged for attention.

## Example Output

```
Starting timezone audit: Max clock drift 300 seconds
Fetching systems from JumpCloud...
  Done! Found 125 systems.
Fetching timezone data from System Insights...
  Done! Found 125 timezone records.

Audit complete. Found 3 systems with timezone issues.
--------------------------------------------------------------------------------
HOSTNAME                   ISSUES
--------------------------------------------------------------------------------
MacBook-Pro-01             Automatic timezone disabled; Clock drift: 450 seconds
MacBook-Air-02             Clock drift: 1200 seconds
iMac-03                    Timezone mismatch: America/Chicago vs America/Denver
--------------------------------------------------------------------------------

[DRY RUN] No changes applied. Run with --apply to execute actions.
[DRY RUN] Would send broadcaster alerts to these systems.
[DRY RUN] Would add these systems to group <GROUP_ID>.
```

## Notes

- This script queries the JumpCloud System Insights API, which aggregates data from managed systems
- Real-time timezone and clock synchronization data is best gathered by running system commands directly on target machines
- In a production environment, consider scheduling this script to run regularly (e.g., hourly or daily) via a management command
- The script uses colorized output for better readability; this can be disabled if needed

## Environment Variables

- `JUMPCLOUD_API_KEY` - **Required**. Your JumpCloud API key for authentication
