# JumpCloud Battery Health Auditor

Identifies MacBooks with degraded batteries using JumpCloud System Insights and provides options for group management and proactive user notifications.

## Purpose

MacBook batteries inevitably degrade over time. This script allows IT teams to proactively identify systems that need battery replacements before they cause performance issues or hardware damage (swelling).

## Features

- **Cycle Count Monitoring**: Primary indicator for battery degradation (default: 1000).
- **Secondary Insights**: Displays health percentage and OS reported condition (if available).
- **Group Management**: Automatically add high-cycle systems to a JumpCloud device group.
- **CSV Export**: Generate detailed reports for capacity planning.
- **User Alerts**: Integration with the **Broadcaster** system for hardware refresh alerts.
- **Safety First**: Runs in dry-run mode (read-only) by default.

## Requirements

### Python
- Python 3.6+
- JumpCloud API key
- Required packages (install via `pip install -r requirements.txt`)

### PowerShell
- PowerShell 5.1+
- JumpCloud API key

## Installation

```bash
cd battery-health
pip install -r requirements.txt
```

## Usage

### Dry Run (Default)
Run a scan and see which systems would be flagged:

**Python:**
```bash
export JUMPCLOUD_API_KEY='your_api_key_here'
python3 battery-health.py --health 75 --cycles 800
```

**PowerShell:**
```powershell
$env:JUMPCLOUD_API_KEY='your_api_key_here'
.\battery-health.ps1 -HealthThreshold 75 -CycleThreshold 800
```

### Applying Changes
To actually add systems to a group or send alerts, you must use the `--apply` flag (Python) or `-Apply` switch (PowerShell).

**Python (With Alerts and Grouping):**
```bash
python3 battery-health.py --group-id <GROUP_ID> --send-alerts --apply
```

**PowerShell (With Alerts and Grouping):**
```powershell
.\battery-health.ps1 -GroupId <GROUP_ID> -SendAlerts -Apply
```

### Exporting to CSV
You can export the results to a CSV file without applying any changes.

**Python:**
```bash
python3 battery-health.py --csv battery_report.csv
```

**PowerShell:**
```powershell
.\battery-health.ps1 -CsvPath battery_report.csv
```

## Arguments / Parameters

| Argument (Py) | Parameter (PS) | Default | Description |
|---|---|---|---|
| `--health` | `-HealthThreshold` | `80` | Health percentage threshold |
| `--cycles` | `-CycleThreshold` | `1000` | Max cycle count threshold |
| `--group-id` | `-GroupId` | `None` | JumpCloud ID of the group to add systems to |
| `--csv` | `-CsvPath` | `None` | Path to export results to CSV |
| `--send-alerts`| `-SendAlerts` | `False` | Trigger Broadcaster alert on failing systems |
| `--apply` | `-Apply` | `False` | Execute changes (otherwise runs as dry-run) |

## User Alert Integration

If `--send-alerts` is used, the script creates a JumpCloud command for each failing system that writes to `/Users/Shared/jc-alert.json`. This is designed to be picked up by the **JCAlertStatusApp**.

The alert message encourages the user to contact IT for a battery replacement.

## Important Notes

- **System Insights**: This script requires JumpCloud System Insights to be enabled for your organization.
- **Broadcaster System**: User alerts only work if the target systems have the `JCAlertStatusApp` installed.
