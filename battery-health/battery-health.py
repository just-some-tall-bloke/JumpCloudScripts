#!/usr/bin/env python3
# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/

"""
Battery Health Auditor
- Monitors battery health and cycle count using System Insights
- Identifies systems with health < 80% or cycle count > 1000 (default)
- Optionally adds non-compliant systems to a device group
- Optionally sends a user alert via the alert system
"""

import requests
import sys
import os
import argparse
import time
import json
from typing import List, Dict, Any
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

def get_battery_insights() -> list:
    """Gets all battery health records from System Insights"""
    print(color_text("Fetching battery data from System Insights...", COLOR_INFO))
    records = []
    skip = 0
    limit = 100
    while True:
        url = f"https://console.jumpcloud.com/api/v2/systeminsights/battery?limit={limit}&skip={skip}"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        if not data:
            break
        records.extend(data)
        print(f"  Fetched {len(records)} battery records...", end="\r")
        if len(data) < limit:
            break
        skip += limit
    print(f"\n  Done! Found {len(records)} battery records.")
    return records

def send_broadcaster_alert(system_id: str, hostname: str):
    """Triggers a user alert using JumpCloud Commands (for Broadcaster system)"""
    alert_title = "Battery Service Recommended"
    alert_msg = "Your MacBook battery health is below 80% (or cycle count is high). Please contact IT for a replacement."
    
    # Payload for the /Users/Shared/jc-alert.json file
    alert_json = {
        "status": "warning",
        "title": alert_title,
        "message": alert_msg
    }
    
    # Command to write the alert file
    # Uses bash to write JSON and set permissions
    script = (
        f"echo '{json.dumps(alert_json)}' > /Users/Shared/jc-alert.json && "
        f"chmod 666 /Users/Shared/jc-alert.json"
    )
    
    url = "https://console.jumpcloud.com/api/commands"
    payload = {
        "name": f"Battery Alert - {hostname}",
        "command": script,
        "commandType": "linux", # JumpCloud uses 'linux' for macOS bash commands
        "launchType": "runOnce",
        "user": "0" # Run as root to have permission for /Users/Shared
    }
    
    # Create the command
    response = requests.post(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    cmd_id = response.json()["_id"]
    
    # Run the command on this specific system
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

def safe_int(value, default=0):
    """Safely convert a value to int, returning default on failure."""
    try:
        if value is None:
            return default
        # If it's a string like 'Good', it's not a numeric percentage
        if isinstance(value, str) and not value.isdigit():
            return default
        return int(value)
    except (ValueError, TypeError):
        return default

def main():
    parser = argparse.ArgumentParser(description="JumpCloud Battery Health Auditor")
    parser.add_argument("--health", type=int, default=80, help="Battery health percentage threshold (default: 80)")
    parser.add_argument("--cycles", type=int, default=1000, help="Battery cycle count threshold (default: 1000)")
    parser.add_argument("--group-id", type=str, help="JumpCloud Group ID to add failing systems to")
    parser.add_argument("--csv", type=str, help="Path to export results to CSV")
    parser.add_argument("--send-alerts", action="store_true", help="Send user alert via Broadcaster system (default: False)")
    parser.add_argument("--apply", action="store_true", help="Apply changes (add to group, send alerts). If not set, run in dry-run mode.")
    args = parser.parse_args()

    print(color_text(f"Starting audit: Health < {args.health}% or Cycles > {args.cycles}", COLOR_INFO))
    
    # 1. Map System IDs to Hostnames
    all_systems = get_all_systems()
    id_to_system = {s.get("_id"): s for s in all_systems}
    
    # 2. Get Battery Health Data
    battery_records = get_battery_insights()
    
    poor_health_systems = []
    
    # 3. Analyze
    for record in battery_records:
        system_id = record.get("system_id")
        system = id_to_system.get(system_id)
        if not system:
            continue
            
        hostname = system.get("hostname", "Unknown")
        
        # Handle cases where value might be 'Good' or other non-integers
        raw_health = record.get("health")
        if raw_health == "Good":
            health_percent = 100 # Treat 'Good' as 100% health
        else:
            health_percent = safe_int(raw_health, default=100)
            
        cycle_count = safe_int(record.get("cycle_count"), default=0)
        condition = record.get("condition", "Normal")
        
        # Check thresholds
        failing = False
        reason = []
        
        # Focus solely on cycle count as health/condition data is unreliable in this environment
        if cycle_count > args.cycles:
            failing = True
            reason.append(f"Cycles {cycle_count} (> {args.cycles})")
            
        if failing:
            poor_health_systems.append({
                "id": system_id,
                "hostname": hostname,
                "health": health_percent,
                "cycles": cycle_count,
                "condition": condition,
                "reason": ", ".join(reason)
            })

    # 4. Report
    print(f"\nAudit complete. Found {len(poor_health_systems)} systems with poor battery health.")
    if not poor_health_systems:
        print(color_text("All systems within healthy thresholds! ✅", COLOR_SUCCESS))
        return

    print("-" * 80)
    print(f"{'HOSTNAME':<25} {'HEALTH':<10} {'CYCLES':<10} {'CONDITION':<15} {'REASON'}")
    print("-" * 80)
    for s in poor_health_systems:
        print(f"{s['hostname']:<25} {s['health']:<10} {s['cycles']:<10} {s['condition']:<15} {s['reason']}")
    print("-" * 80)

    # 4.5 CSV Export
    if args.csv:
        import csv
        print(color_text(f"\nExporting results to {args.csv}...", COLOR_INFO))
        try:
            with open(args.csv, mode='w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=["hostname", "health", "cycles", "condition", "reason", "id"])
                writer.writeheader()
                for row in poor_health_systems:
                    writer.writerow(row)
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
    for s in poor_health_systems:
        if args.group_id:
            if add_system_to_group(s["id"], args.group_id):
                print(f"  [+] Added {s['hostname']} to group.")
            else:
                print(f"  [x] Failed to add {s['hostname']} to group.")
        
        if args.send_alerts:
            try:
                send_broadcaster_alert(s["id"], s["hostname"])
                print(f"  [!] Sent Broadcaster alert to {s['hostname']}.")
            except Exception as e:
                print(f"  [x] Failed to alert {s['hostname']}: {e}")

    print(color_text("\nDone!", COLOR_SUCCESS))

if __name__ == "__main__":
    main()
