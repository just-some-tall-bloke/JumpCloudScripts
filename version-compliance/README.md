# JumpCloud macOS Version Compliance

Manages JumpCloud device groups for macOS version compliance tracking.

## Purpose

This script helps maintain macOS compliance by automatically managing device groups containing Mac systems running below a specified macOS version.

## Features

- **Version Checking**: Identifies Mac systems running below target macOS version
- **Automatic Group Management**: Adds non-compliant systems to compliance groups
- **Dynamic Group Updates**: Removes systems that have been upgraded to compliant versions
- **Group Renaming**: Automatically renames groups to match target version
- **Comprehensive Coverage**: Processes ALL Mac systems (no hostname filtering)
- **Detailed Reporting**: Shows exactly which systems are being added/removed

## Requirements

- Python 3.6+
- JumpCloud API key (set as environment variable `JUMPCLOUD_API_KEY`)
- Required Python packages: `requests`, `packaging`

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
python3 version-compliance.py
```

**PowerShell:**
```powershell
$env:JUMPCLOUD_API_KEY='your_api_key_here'
.\version-compliance.ps1
```

3. Follow the prompts to:
   - Enter the target JumpCloud group ID
   - Specify the target macOS version (e.g., 15.7.1)
   - Optionally rename the group
   - Confirm additions and removals

## Configuration

- **Target macOS Version**: User-specified during execution
- **Group Management**: Fully automated based on version comparison
- **System Scope**: ALL Mac OS X systems (no hostname filtering)

## What It Does

### Systems Added to Group:
- All Mac OS X systems (any hostname)
- macOS version BELOW target version
- Active systems in JumpCloud

### Systems Removed from Group:
- Mac systems that are NOW compliant (version >= target)
- Non-Mac systems (if somehow added)

## Version Comparison Logic

Uses semantic version comparison:
- ✅ **Non-compliant**: macOS 14.5.0 < 15.7.1 (added to group)
- ✅ **Compliant**: macOS 15.8.0 >= 15.7.1 (removed from group)
- ✅ **Compliant**: macOS 15.7.1 >= 15.7.1 (removed from group)

## Example Workflow

1. **Initial Setup**: Target group named "Macs below 15.7.1"
2. **Script Execution**: Finds all Mac systems with versions < 15.7.1
3. **Group Population**: Adds non-compliant systems to the group
4. **Ongoing Maintenance**: 
   - New systems below 15.7.1 are automatically added
   - Systems upgraded to 15.7.1+ are automatically removed

## Output Information

The script provides detailed output showing:
- All Mac systems and their compliance status
- Systems to be added to the group
- Systems to be removed from the group
- Current vs. target macOS versions
- Confirmation prompts before changes
- Final summary of actions taken

## Group Naming Convention

Suggested group name format: `Macs below {target_version}`

Example: `Macs below 15.7.1`

## Safety Features

- **Preview Mode**: Shows exactly what will be changed before execution
- **Separate Confirmations**: Separate confirmations for additions and removals
- **Detailed Logging**: Comprehensive output of all system checks
- **Error Handling**: Graceful handling of API errors and missing data
- **Version Validation**: Validates version format input before proceeding

## Use Cases

### Compliance Tracking
- Track all Mac systems below a security-required version
- Monitor upgrade progress over time
- Create targeted groups for patch deployment

### Version Migration
- Identify systems needing OS upgrades
- Manage phased rollouts
- Track compliance percentages

### Reporting
- Generate compliance reports
- Monitor fleet-wide version distribution
- Identify stragglers in upgrade cycles

## Troubleshooting

1. **API Key Issues**: Ensure `JUMPCLOUD_API_KEY` has proper permissions
2. **Version Format**: Use semantic versioning (e.g., 15.7.1, not 15.7)
3. **Group ID**: Verify the target group exists and is accessible
4. **Network**: Check connectivity to JumpCloud API endpoints

## Best Practices

- Run this script regularly to maintain accurate compliance groups
- Use descriptive group names that clearly indicate the target version
- Test with a small group first before applying to production
- Keep the script updated for new macOS releases