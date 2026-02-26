# JumpCloud Duplicate System Remover

Identifies and removes duplicate JumpCloud system entries based on serial numbers.

## Purpose

This script scans your JumpCloud environment for systems with duplicate serial numbers and removes the older entries, keeping only the most recently contacted device for each serial number.

## Features

- **Smart Duplicate Detection**: Groups systems by serial number to find duplicates
- **Intelligent Selection**: Keeps the system with the most recent lastContact timestamp
- **Safe by Default**: Runs in DRY_RUN mode to preview actions before execution
- **Colored Output**: Provides clear, color-coded feedback and progress indicators
- **Comprehensive Logging**: Logs all actions to both console and file (`duplicate-remover.log`)
- **Rate Limiting**: Implements delays to avoid API throttling
- **Progress Tracking**: Shows progress bars for system fetching and processing
- **Selection Logic**: Keeps the most recently contacted device for each serial number
- **Confirmation Required**: No automatic deletion in dry run mode

## Requirements

- Python 3.6+
- JumpCloud API key (set as environment variable `JUMPCLOUD_API_KEY`)
- Required Python packages: `requests`, `colorama` (optional, for colored output)

## Installation

```bash
pip install -r requirements.txt
```

*Note: `colorama` is optional. Script will work without colors if not installed.*

## Usage

### Dry Run (Recommended First)
```bash
export JUMPCLOUD_API_KEY='your_api_key_here'
python3 duplicate-remover.py
```

### Live Deletion (Enable Deletion)

**Python:**
Use the `--delete` flag:
```bash
python3 duplicate-remover.py --delete
```

**PowerShell:**
Use the `-Delete` switch:
```powershell
$env:JUMPCLOUD_API_KEY='your_api_key_here'
.\duplicate-remover.ps1 -Delete
```

## Configuration

- **Dry Run**: Enabled by default. Run without flags to preview actions.
- **RATE_LIMIT_DELAY**: Seconds between API calls (default: 0.1)
- **LOG_FILE**: Output file for detailed logging (default: `duplicate-remover.log`)

## What It Does

1. **Fetches All Systems**: Retrieves every system from your JumpCloud environment
2. **Groups by Serial Number**: Identifies systems sharing the same serial number
3. **Filters Valid Serials**: Skips systems with empty/invalid serial numbers
4. **Keeps Newest Entry**: For each duplicate group, keeps the system with most recent contact
5. **Removes Older Entries**: Deletes all other systems in each duplicate group

## Selection Logic

For systems with duplicate serial numbers:
- ✅ **KEEP**: System with the most recent `lastContact` timestamp
- ❌ **DELETE**: All other systems with the same serial number

## Output Examples

### Dry Run Mode:
```
*** STARTING DRY RUN MODE ***
The following actions would be taken:
[DRY RUN] Would delete: Old-MacBook (ID: 12345)
```

### Live Mode:
```
! STARTING DELETION RUN - PERMANENT ACTION !
WARNING: This is permanent. Deleting devices...
[ACTION] Deleting: Old-MacBook (ID: 12345)...
[SUCCESS] Deleted Old-MacBook.
```

## Safety Features

- **Dry Run Default**: Must explicitly enable deletion mode
- **Detailed Logging**: Every action logged to file
- **Progress Indicators**: Visual feedback for long operations
- **Error Handling**: Comprehensive error handling with detailed messages
- **Confirmation Required**: No automatic deletion in dry run mode

## Log File

All actions are logged to `duplicate-remover.log` with timestamps and detail levels:
- INFO: Normal operations
- WARNING: Important notices
- ERROR: Failed operations

## Troubleshooting

1. **API Key Not Set**: Ensure `JUMPCLOUD_API_KEY` environment variable is set
2. **Permissions**: Verify API key has delete permissions for systems
3. **Rate Limits**: Increase `RATE_LIMIT_DELAY` if encountering throttling
4. **Network Issues**: Check connectivity to `console.jumpcloud.com`

## Important Notes

⚠️ **WARNING**: When using the deletion flag, this script permanently deletes systems from JumpCloud. Always run in dry run mode first and review the output carefully.

💡 **Best Practice**: Run without the deletion flag first and review the log file to understand what will be deleted before enabling live mode.