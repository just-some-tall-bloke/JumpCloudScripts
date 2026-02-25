# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/
# macOS MDM Scripts

## 📁 Project Organization

This repository has been organized into individual folders for each script/application with dedicated README files:

### 🔧 Management Scripts
- **`uptime-monitor/`** - JumpCloud High Uptime Monitor
- **`duplicate-remover/`** - JumpCloud Duplicate System Remover  
- **`version-compliance/`** - JumpCloud macOS Version Compliance
- **`macos-version-audit/`** - JumpCloud macOS Version Audit Exporter

Each folder contains:
- The main script/application
- Detailed README with usage instructions
- Configuration requirements
- Troubleshooting guide

---

## Table of Contents
- [Quick Overview](#quick-overview)
- [Requirements](#requirements)
- [Individual Script Details](#individual-script-details)

## Quick Overview

| Script | Purpose | Language | Folder |
|--------|---------|----------|---------|
| **uptime.py** | Monitors Mac uptime >14 days, manages device groups | Python | `uptime-monitor/` |
| **delete_dupes.py** | Removes duplicate JumpCloud devices by serial | Python | `duplicate-remover/` |
| **outdated-macs.py** | Manages macOS version compliance groups | Python | `version-compliance/` |
| **macos-version-audit.ps1** | Exports Mac systems below target version | PowerShell | `macos-version-audit/` |

## Requirements

### Python Scripts
- Python 3.7+
- JumpCloud API key (set as `JUMPCLOUD_API_KEY` environment variable)
- Required packages: See individual script folders for `requirements.txt` files and run `pip install -r requirements.txt`

### PowerShell Scripts
- PowerShell 5.1+ or PowerShell Core
- JumpCloud API key (set as environment variable)

## Individual Script Details

For detailed usage instructions, configuration, and troubleshooting for each script/application, please refer to the individual README files in each folder:

### 🔧 Management Scripts
- **[uptime-monitor/README.md](uptime-monitor/README.md)** - Complete uptime monitoring documentation
- **[duplicate-remover/README.md](duplicate-remover/README.md)** - Duplicate removal with safety guidelines  
- **[version-compliance/README.md](version-compliance/README.md)** - macOS compliance management
- **[macos-version-audit/README.md](macos-version-audit/README.md)** - Version export and audit reporting

Each folder contains:
- ✅ Main script/application
- ✅ Detailed installation instructions  
- ✅ Configuration requirements
- ✅ Usage examples
- ✅ Troubleshooting guide
- ✅ Safety features and best practices

---
A comprehensive collection of scripts and applications for enterprise macOS fleet management using JumpCloud MDM. This repository includes Python scripts, PowerShell utilities, and native macOS applications for compliance automation, device management, and system administration.

## 🚀 Quick Start

All scripts require a JumpCloud API key. Set it as an environment variable:

```bash
# For bash/zsh
export JUMPCLOUD_API_KEY='your_api_key_here'

# For PowerShell (Windows)
$env:JUMPCLOUD_API_KEY = 'your_api_key_here'

# For persistent PowerShell setting
[System.Environment]::SetEnvironmentVariable('JUMPCLOUD_API_KEY', 'your_api_key', 'User')
```

## 📋 Scripts & Applications

### 🐍 Python Scripts

#### 1. `outdated-macs.py` - macOS Version Compliance Management
**Purpose**: Automatically manage device groups for macOS version compliance

**Features**:
- Scans ALL Mac systems in your JumpCloud organization
- Adds non-compliant Macs (below target version) to specified device groups
- Removes compliant Macs that have been upgraded from compliance groups
- Automatically renames groups to match target version (e.g., "Macs below 15.7.1")
- Interactive confirmation before making changes

**Usage**:
```bash
python3 outdated-macs.py
```

**What it asks for**:
- **Target Group ID**: The alphanumeric ID from the JumpCloud web console URL
- **Target macOS version**: e.g., `15.7.1`

**Workflow**:
1. Validates current group name vs. suggested format
2. Offers to rename group if needed
3. Shows which Macs will be added/removed
4. Requires separate confirmation for additions and removals
5. Executes changes with detailed logging

#### 2. `delete_dupes.py` - Duplicate Device Cleanup
**Purpose**: Identifies and removes duplicate devices based on serial numbers

**Features**:
- Scans entire JumpCloud organization for duplicate serial numbers
- Keeps the most recently contacted device in each duplicate set
- Dry-run mode enabled by default for safety
- Real-time progress tracking with colored console output
- Comprehensive logging to `delete_dupes.log`
- Works with ALL device types (macOS, Windows, Linux, mobile)
- Built-in rate limiting to respect API limits
- Graceful handling of missing/invalid serial numbers and timestamps

**Safety Features**:
- **DRY_RUN = True** by default - no actual deletions occur
- Clear logging shows exactly which devices will be kept/deleted
- Rate limiting prevents API throttling
- Comprehensive error handling

**Usage**:
```bash
# Dry run (recommended first)
python3 delete_dupes.py

# Edit script to set DRY_RUN = False, then:
python3 delete_dupes.py
```

#### 3. `macos-version-audit.py` - macOS Version Audit Reporting
**Purpose**: Export detailed reports of Mac systems below specified macOS versions

**Features**:
- Interactive input for target version and days filter
- Fetches primary user information for each system
- CSV export with comprehensive system details
- Real-time progress tracking
- Filters by last contact date to ensure recent activity

**Usage**:
```bash
python3 macos-version-audit.py
```

**Output**: CSV file with columns:
- Hostname, DisplayName, MacOSVersion, SerialNumber
- PrimaryUsername, PrimaryUserID, SystemID
- LastContact, Active status

### 📟 PowerShell Script

#### `macos-version-audit.ps1` - Windows-Compatible Version Audit Reporting
**Purpose**: PowerShell equivalent of `macos-version-audit.py` for Windows environments

**Features**:
- Same functionality as Python version but native PowerShell
- Progress bar during system processing
- CSV export with formatted table display
- Compatible with Windows PowerShell and PowerShell Core

**Usage**:
```powershell
# Set API key first
$env:JUMPCLOUD_API_KEY = 'your_api_key_here'

# Run script
.\macos-version-audit.ps1
```

**Output**: Creates CSV file with same format as Python version

## 📊 Output Examples

### Compliance Management Output
```
✅ Group renamed to: Macs below 15.7.1
📊 Summary:
  Non-compliant Macs: 23
  Compliant Macs in group: 5
  Total systems currently in group: 18

📋 Actions needed:
  Systems to ADD to group: 18
  Systems to REMOVE from group: 5
```

### Duplicate Cleanup Output
```
=== JumpCloud Duplicate System Remover ===
[+] Found 1,247 total systems.
[!] Found 12 serial number(s) with duplicate entries.
[i] Skipped 3 systems with invalid serial numbers.

[PROC] Processing Serial Number: C02XYZ123 (2 entries) - Group 1/12
[KEEP] Keeping newest: MacBook-Pro-2021 (Last contact: 2024-01-15T10:30:00Z)
[DRY RUN] Would delete: MacBook-Pro-Old (ID: 5f8d9c3e2a1b4c5d)
```

### Version Report CSV
| Hostname | MacOSVersion | PrimaryUsername | LastContact |
|----------|--------------|-----------------|-------------|
| MBP-JDoe | 14.6.1       | john.doe        | 2024-01-15   |
| MBA-Smith| 15.0.1       | jane.smith      | 2024-01-14   |

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with appropriate documentation
4. Test thoroughly in a non-production environment
5. Submit a pull request with clear description

## 📄 License

This repository contains scripts and applications for JumpCloud MDM management. Please ensure compliance with:
- JumpCloud API terms of service
- Your organization's security policies
- Applicable data protection regulations

## 🔗 Related Resources

- [JumpCloud API Documentation](https://developer.jumpcloud.com/)
- [macOS Deployment Reference](https://developer.apple.com/business/)
- [MDM Best Practices](https://support.apple.com/guide/deployment/deploy-with-mdm-dep9c4092d3e/mac)

## 📞 Support

For issues with:
- **JumpCloud API**: Contact JumpCloud support
- **Script functionality**: Open an issue in this repository

---

⚡ **Pro Tip**: Start with `macos-version-audit.py` or `macos-version-audit.ps1` to understand your current fleet status before making changes with compliance or cleanup scripts.
