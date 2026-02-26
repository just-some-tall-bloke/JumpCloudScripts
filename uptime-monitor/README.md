# JumpCloud High Uptime Monitor

Automatically manages JumpCloud device groups for Mac systems with high uptime.

## Purpose

This script monitors Mac systems in JumpCloud and automatically adds devices with uptime exceeding 14 days to a specified device group. It also removes devices that no longer meet the criteria.

## Features

- **Automatic Uptime Monitoring**: Monitors Mac systems and identifies those with uptime > 14 days
- **Smart Filtering**: Only processes Mac systems with hostnames starting with "MAC"
- **Recent Contact Check**: Only includes systems that have contacted JumpCloud within the last 7 days
- **Group Management**: Automatically adds eligible systems and removes ineligible ones
- **Parallel Processing**: Uses multi-threading for efficient processing of large device fleets
- **Rate Limiting**: Implements adaptive rate limiting to avoid API throttling
- **Detailed Logging**: Provides comprehensive output of all actions taken

## Requirements

- Python 3.6+
- JumpCloud API key (set as environment variable `JUMPCLOUD_API_KEY`)
- Required Python packages: `requests`, `tqdm`

## Installation

```bash
pip install -r requirements.txt
```

## Usage

1. Set your JumpCloud API key:
```bash
export JUMPCLOUD_API_KEY='your_api_key_here'
```

2. Run the script:

**Python:**
```bash
python3 uptime-monitor.py
```

**PowerShell:**
```powershell
$env:JUMPCLOUD_API_KEY='your_api_key_here'
.\uptime-monitor.ps1
```

3. Follow the prompts to:
   - Enter the target JumpCloud group ID
   - Optionally rename the group
   - Confirm additions and removals

## Configuration

- **UPTIME_THRESHOLD_DAYS**: Default 14 days (configurable in script)
- **CONTACT_WINDOW_DAYS**: Default 7 days (configurable in script)
- **DEFAULT_MAX_WORKERS**: Auto-calculated based on CPU cores
- **BATCH_SIZE**: 50 systems per batch (configurable)

## What It Does

### Systems Added to Group:
- Mac OS X systems
- Hostname starts with "MAC"
- Uptime > 14 days
- Last contact within 7 days

### Systems Removed from Group:
- Non-Mac systems
- Macs without MAC* hostname
- Systems with uptime ≤ 14 days (rebooted)
- Systems with no recent contact

## Output

The script provides detailed output including:
- System status updates during processing
- Summary of systems to add/remove
- Confirmation prompts before changes
- Final operation summary with statistics

## Safety Features

- Dry-run preview of all changes
- Explicit confirmation required for additions/removals
- Comprehensive error handling and logging
- Graceful handling of API rate limits
- Progress bars for long operations

## Troubleshooting

- Ensure `JUMPCLOUD_API_KEY` is properly set
- Verify the target group ID exists
- Check network connectivity to JumpCloud API
- Review logs for detailed error information