# macOS MDM Scripts

## 📁 Project Organization

This repository has been organized into individual folders for each script with dedicated README files:

### 🔧 Management Scripts
- **`uptime-monitor/`** - Device Uptime Monitor
- **`duplicate-remover/`** - Duplicate System Remover  
- **`version-compliance/`** - macOS Version Compliance
- **`version-check/`** - Version Check Exporter
- **`battery-health/`** - Battery Health Auditor
- **`network-audit/`** - Network Configuration Audit
- **`timezone-region-sync/`** - Timezone/Region Sync Auditor

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
| **uptime-monitor.py** / **.ps1** | Monitors device uptime >14 days, manages device groups | Python/PS | `uptime-monitor/` |
| **duplicate-remover.py** / **.ps1** | Removes duplicate devices by serial | Python/PS | `duplicate-remover/` |
| **version-compliance.py** / **.ps1** | Manages macOS version compliance groups | Python/PS | `version-compliance/` |
| **battery-health.py** / **.ps1** | Monitors battery health and cycle count | Python/PS | `battery-health/` |
| **version-check.py** / **.ps1** | Exports systems below target version | Python/PS | `version-check/` |
| **network-audit.py** / **.ps1** | Audits network configuration and DNS/proxy settings | Python/PS | `network-audit/` |
| **timezone-region-sync.py** / **.ps1** | Detects timezone and time sync issues | Python/PS | `timezone-region-sync/` |

## Requirements

### Python Scripts
- Python 3.7+
- API key (set as `MDM_API_KEY` environment variable)
- Required packages (shared): `requests`, `colorama`
- Additional per-script packages: `tqdm` (uptime-monitor), `packaging` (version-compliance)
- Install via: `pip install -r requirements.txt` in the specific script folder

### PowerShell Scripts
- PowerShell 5.1+ or PowerShell Core
- API key (set as environment variable)

## Individual Script Details

For detailed usage instructions, configuration, and troubleshooting for each script/application, please refer to the individual README files in each folder:

### 🔧 Management Scripts
- **[uptime-monitor/README.md](uptime-monitor/README.md)** - Complete uptime monitoring documentation
- **[duplicate-remover/README.md](duplicate-remover/README.md)** - Duplicate removal with safety guidelines  
- **[version-compliance/README.md](version-compliance/README.md)** - macOS compliance management
- **[version-check/README.md](version-check/README.md)** - Version export and reporting
- **[battery-health/README.md](battery-health/README.md)** - Battery health monitoring and alerts
- **[network-audit/README.md](network-audit/README.md)** - Network configuration auditing
- **[timezone-region-sync/README.md](timezone-region-sync/README.md)** - Timezone and NTP synchronization

### 📱 Alert Broadcaster System
- **[Broadcaster/Broadcaster-Apps-README.md](Broadcaster/Broadcaster-Apps-README.md)** - Complete alert system documentation
- **[Broadcaster/Alert/](Broadcaster/Alert/)** - Alert sender application (see folder for project files)
- **[Broadcaster/StatusApp/](Broadcaster/StatusApp/)** - Alert display application (see folder for project files)

Each folder contains:
- ✅ Main script/application
- ✅ Detailed installation instructions  
- ✅ Configuration requirements
- ✅ Usage examples
- ✅ Troubleshooting guide
- ✅ Safety features and best practices

---
A comprehensive collection of scripts and applications for enterprise macOS fleet management using MDM. This repository includes Python scripts, PowerShell utilities, and native macOS applications for compliance automation, device management, and system administration.

## 🚀 Quick Start

All scripts require an MDM API key. Set it as an environment variable:

```bash
# For bash/zsh
export MDM_API_KEY='your_api_key_here'

# For PowerShell (Windows)
$env:MDM_API_KEY = 'your_api_key_here'

# For persistent PowerShell setting
[System.Environment]::SetEnvironmentVariable('MDM_API_KEY', 'your_api_key', 'User')
```

## 📋 Scripts & Applications

### 🐍 Python Scripts

#### 1. `version-compliance.py` - macOS Version Compliance Management
**Purpose**: Automatically manage device groups for macOS version compliance

**Features**:
- Scans ALL systems in your MDM organization
- Adds non-compliant systems (below target version) to specified device groups
- Removes compliant systems that have been upgraded from compliance groups
- Automatically renames groups to match target version (e.g., "Systems below 15.7.1")
- Interactive confirmation before making changes

**Usage**:
```bash
python3 version-compliance.py
```

**What it asks for**:
- **Target Group ID**: The alphanumeric ID from the MDM web console URL
- **Target macOS version**: e.g., `15.7.1`

**Workflow**:
1. Validates current group name vs. suggested format
2. Offers to rename group if needed
3. Shows which systems will be added/removed
4. Requires separate confirmation for additions and removals
5. Executes changes with detailed logging

#### 2. `duplicate-remover.py` - Duplicate Device Cleanup
**Purpose**: Identifies and removes duplicate devices based on serial numbers

**Features**:
- Scans entire MDM organization for duplicate serial numbers
- Keeps the most recently contacted device in each duplicate set
- Dry-run mode enabled by default for safety
- Real-time progress tracking with colored console output
- Comprehensive logging to `duplicate-remover.log`
- Works with ALL device types (macOS, Windows, Linux, mobile)
- Built-in rate limiting to respect API limits
- Graceful handling of missing/invalid serial numbers and timestamps

**Safety Features**:
- **Dry-run by default**: No deletions occur unless explicitly requested
- **Manual confirmation**: Required even when deletion is enabled
- **Clear logging**: Shows exactly which devices would be kept/deleted
- **Rate limiting**: Prevents API throttling

**Usage**:
```bash
# Dry run (default)
python3 duplicate-remover.py

# Live deletion
python3 duplicate-remover.py --delete
```

#### 3. `version-check.py` - macOS Version Reporting
**Purpose**: Export detailed reports of Mac systems below specified macOS versions

**Features**:
- Interactive input for target version and days filter
- Fetches primary user information for each system
- CSV export with comprehensive system details
- Real-time progress tracking
- Filters by last contact date to ensure recent activity

**Usage**:
```bash
python3 version-check.py
```

**Output**: CSV file with columns:
- Hostname, DisplayName, MacOSVersion, SerialNumber
- PrimaryUsername, PrimaryUserID, SystemID
- LastContact, Active status

#### 4. `battery-health.py` - MacBook Battery Health Auditor
**Purpose**: Identify MacBooks with degraded batteries and manage hardware refresh

**Features**:
- Cycle count monitoring (default threshold: 1000)
- Health percentage and OS-reported battery condition
- Automatic group management for high-cycle systems
- CSV export for capacity planning
- Broadcaster integration for user alerts
- Dry-run mode by default (read-only)

**Usage**:
```bash
# Dry run (preview only)
python3 battery-health.py

# With group management
python3 battery-health.py --group <group_id>
```

#### 5. `network-audit.py` - Network Configuration Audit
**Purpose**: Detect unusual network setups and audit DNS, proxy, and VPN configurations

**Features**:
- DNS configuration auditing (detects custom/non-standard settings)
- Proxy detection and reporting
- VPN connection monitoring
- Network interface listing
- CSV export for comprehensive reporting
- Colorized console output with status indicators
- Real-time progress tracking

**Usage**:
```bash
python3 network-audit.py
```

#### 6. `timezone-region-sync.py` - Timezone/Region Sync Auditor
**Purpose**: Ensure fleet consistency by auditing timezone and NTP synchronization settings

**Features**:
- Automatic timezone detection
- Clock drift analysis against NTP servers
- Identification of non-compliant systems
- Dry-run mode for preview
- Group management for systems with issues
- Broadcaster integration for user alerts
- CSV export for auditing

**Usage**:
```bash
# Dry run (preview only)
python3 timezone-region-sync.py

# With group management
python3 timezone-region-sync.py --group <group_id>
```

### 📟 PowerShell Script

#### `version-check.ps1` - Windows-Compatible Version Reporting
**Purpose**: PowerShell equivalent of `version-check.py` for Windows environments

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
.\version-check.ps1
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
- **macOS applications**: Check Xcode build logs and console output

---

⚡ **Pro Tip**: Start with `version-check.py` or `version-check.ps1` to understand your current fleet status before making changes with compliance or cleanup scripts.
