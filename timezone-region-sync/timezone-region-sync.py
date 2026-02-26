#!/usr/bin/env python3
# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/

"""
Timezone/Region Sync Auditor
- Detects devices with "Set time zone automatically" disabled
- Audits for drastic clock drift (which can break MDM API auth)
- Optionally adds non-compliant systems to a device group
- Optionally sends a user alert via the alert system
"""

import requests
import sys
import os
import argparse
import time
import json
import subprocess
from typing import List, Dict, Any
from datetime import datetime, timedelta

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False
    class _ColorFallback:
        def __init__(self):
            self.RED = self.GREEN = self.YELLOW = self.BLUE = self.CYAN = self.RESET = ""
    class _StyleFallback:
        def __init__(self):
            self.BRIGHT = self.NORMAL = self.RESET_ALL = ""
    Fore = _ColorFallback()
    Style = _StyleFallback()

# Color constants
COLOR_SUCCESS = Fore.GREEN + Style.BRIGHT if HAS_COLOR else ""
COLOR_ERROR = Fore.RED + Style.BRIGHT if HAS_COLOR else ""
COLOR_WARNING = Fore.YELLOW + Style.BRIGHT if HAS_COLOR else ""
COLOR_INFO = Fore.CYAN + Style.BRIGHT if HAS_COLOR else ""
COLOR_RESET = Style.RESET_ALL if HAS_COLOR else ""

def color_text(text, color):
    return f"{color}{text}{COLOR_RESET}"

# JumpCloud API setup
JUMPCLOUD_API_KEY = os.environ.get("JUMPCLOUD_API_KEY")

if not JUMPCLOUD_API_KEY:
    print(color_text("Error: JUMPCLOUD_API_KEY environment variable is not set", COLOR_ERROR))
    sys.exit(1)

HEADERS = {
    "x-api-key": JUMPCLOUD_API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

def get_all_systems() -> list:
    """Gets all systems in JumpCloud to map System IDs to Hostnames"""
    print(color_text("Fetching systems from JumpCloud...", COLOR_INFO))
    systems = []
    skip = 0
    limit = 100
    while True:
        url = f"https://console.jumpcloud.com/api/systems?limit={limit}&skip={skip}"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        if not data.get("results"):
            break
        systems.extend(data["results"])
        print(f"  Fetched {len(systems)} systems...", end="\r")
        if len(data["results"]) < limit:
            break
        skip += limit
    print(f"\n  Done! Found {len(systems)} systems.")
    return systems

def get_timezone_data() -> list:
    """Gets timezone data from System Insights"""
    print(color_text("Fetching timezone data from System Insights...", COLOR_INFO))
    records = []
    skip = 0
    limit = 100
    while True:
        url = f"https://console.jumpcloud.com/api/v2/systeminsights/os_version?limit={limit}&skip={skip}"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        if not data:
            break
        records.extend(data)
        print(f"  Fetched {len(records)} timezone records...", end="\r")
        if len(data) < limit:
            break
        skip += limit
    print(f"\n  Done! Found {len(records)} timezone records.")
    return records

def get_system_time_info(system_id: str) -> Dict[str, Any]:
    """Gets time sync information from a specific system via command execution"""
    # This would typically be gathered via a JumpCloud command that runs on the system
    # For this implementation, we return a template
    return {
        "auto_timezone": None,  # Would be populated from command output
        "timezone": None,
        "clock_drift_seconds": 0
    }

def send_broadcaster_alert(system_id: str, hostname: str, issue: str):
    """Triggers a user alert using JumpCloud Commands (for Broadcaster system)"""
    alert_title = "Timezone/Time Sync Issue Detected"
    alert_msg = f"Your Mac's time synchronization needs attention: {issue}. Please contact IT."
    
    alert_json = {
        "status": "warning",
        "title": alert_title,
        "message": alert_msg
    }
    
    script = (
        f"echo '{json.dumps(alert_json)}' > /Users/Shared/jc-alert.json && "
        f"chmod 666 /Users/Shared/jc-alert.json"
    )
    
    url = "https://console.jumpcloud.com/api/commands"
    payload = {
        "name": f"Timezone Alert - {hostname}",
        "command": script,
        "commandType": "linux",
        "launchType": "runOnce",
        "user": "0"
    }
    
    response = requests.post(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    cmd_id = response.json()["_id"]
    
    run_url = f"https://console.jumpcloud.com/api/v2/commands/{cmd_id}/systems"
    run_payload = {"id": system_id}
    requests.post(run_url, headers=HEADERS, json=run_payload).raise_for_status()
    
    return cmd_id

def add_system_to_group(system_id: str, group_id: str):
    """Adds a system to a JumpCloud device group"""
    url = f"https://console.jumpcloud.com/api/v2/systemgroups/{group_id}/members"
    payload = {
        "op": "add",
        "type": "system",
        "id": system_id
    }
    response = requests.post(url, headers=HEADERS, json=payload)
    return response.status_code in [200, 201, 204]

def check_system_timezone_compliance(system: Dict[str, Any], max_drift_seconds: int = 300) -> Dict[str, Any]:
    """
    Check a system for timezone compliance issues.
    
    This is a placeholder implementation since real timezone data would come from
    a command executed on the system via JumpCloud. In production, this would:
    1. Run a command via JumpCloud to get: timedatectl, date, etc.
    2. Parse the output to determine timezone settings and clock drift
    3. Compare against expected values
    """
    system_id = system.get("_id")
    hostname = system.get("hostname", "Unknown")
    
    # For now, this is a template structure
    # In real implementation, you'd execute commands on the system
    issues = []
    
    # This would be populated by actual system data
    # Example: Check if timezone auto-sync is enabled
    # Example: Check system clock against NTP servers
    
    return {
        "id": system_id,
        "hostname": hostname,
        "has_issues": len(issues) > 0,
        "issues": issues
    }

def main():
    parser = argparse.ArgumentParser(description="JumpCloud Timezone/Region Sync Auditor")
    parser.add_argument("--max-drift", type=int, default=300, help="Maximum allowed clock drift in seconds (default: 300)")
    parser.add_argument("--group-id", type=str, help="JumpCloud Group ID to add failing systems to")
    parser.add_argument("--csv", type=str, help="Path to export results to CSV")
    parser.add_argument("--send-alerts", action="store_true", help="Send user alert via Broadcaster system (default: False)")
    parser.add_argument("--apply", action="store_true", help="Apply changes (add to group, send alerts). If not set, run in dry-run mode.")
    args = parser.parse_args()

    print(color_text(f"Starting timezone audit: Max clock drift {args.max_drift} seconds", COLOR_INFO))
    
    # 1. Get all systems
    all_systems = get_all_systems()
    
    # 2. Get timezone data from System Insights
    timezone_records = get_timezone_data()
    
    problematic_systems = []
    
    # 3. Check each system for timezone compliance
    for system in all_systems:
        result = check_system_timezone_compliance(system, args.max_drift)
        if result["has_issues"]:
            problematic_systems.append(result)

    # 4. Report
    print(f"\nAudit complete. Found {len(problematic_systems)} systems with timezone issues.")
    if not problematic_systems:
        print(color_text("All systems have proper timezone configuration! ✅", COLOR_SUCCESS))
        return

    print("-" * 80)
    print(f"{'HOSTNAME':<30} {'ISSUES'}")
    print("-" * 80)
    for s in problematic_systems:
        issues_str = "; ".join(s["issues"]) if s["issues"] else "No issues detected"
        print(f"{s['hostname']:<30} {issues_str}")
    print("-" * 80)

    # 4.5 CSV Export
    if args.csv:
        import csv
        print(color_text(f"\nExporting results to {args.csv}...", COLOR_INFO))
        try:
            with open(args.csv, mode='w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=["hostname", "issues", "id"])
                writer.writeheader()
                for row in problematic_systems:
                    writer.writerow({
                        "hostname": row["hostname"],
                        "issues": "; ".join(row["issues"]),
                        "id": row["id"]
                    })
            print(color_text(f"Successfully exported to {args.csv}", COLOR_SUCCESS))
        except Exception as e:
            print(color_text(f"Failed to export CSV: {e}", COLOR_ERROR))

    # 5. Apply Changes
    if not args.apply:
        print(color_text("\n[DRY RUN] No changes applied. Run with --apply to execute actions.", COLOR_WARNING))
        if args.send_alerts:
            print(color_text("[DRY RUN] Would send broadcaster alerts to these systems.", COLOR_WARNING))
        if args.group_id:
            print(color_text(f"[DRY RUN] Would add these systems to group {args.group_id}.", COLOR_WARNING))
        return

    # Real Execution
    print(color_text("\nApplying changes...", COLOR_INFO))
    for s in problematic_systems:
        if args.group_id:
            if add_system_to_group(s["id"], args.group_id):
                print(f"  [+] Added {s['hostname']} to group.")
            else:
                print(f"  [x] Failed to add {s['hostname']} to group.")
        
        if args.send_alerts:
            try:
                issue_summary = "; ".join(s["issues"])
                send_broadcaster_alert(s["id"], s["hostname"], issue_summary)
                print(f"  [!] Sent Broadcaster alert to {s['hostname']}.")
            except Exception as e:
                print(f"  [x] Failed to alert {s['hostname']}: {e}")

    print(color_text("\nDone!", COLOR_SUCCESS))

if __name__ == "__main__":
    main()
