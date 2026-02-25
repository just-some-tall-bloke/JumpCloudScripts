#!/usr/bin/env python3
# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/
"""
JumpCloud macOS Version Compliance Script
- Adds ALL Mac computers running below a specified macOS version to a device group
- Removes Mac computers that have upgraded and are now compliant
- Renames the group to match the target version
"""

import requests
import sys
import os
from packaging import version
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False
    # Fallback color classes if colorama is not available
    class _ColorFallback:
        def __init__(self):
            self.RED = self.GREEN = self.YELLOW = self.BLUE = ""
            self.MAGENTA = self.CYAN = self.WHITE = self.RESET = ""
    class _StyleFallback:
        def __init__(self):
            self.BRIGHT = self.DIM = self.NORMAL = self.RESET_ALL = ""
    Fore = _ColorFallback()
    Style = _StyleFallback()

# Color constants
COLOR_SUCCESS = Fore.GREEN + Style.BRIGHT if HAS_COLOR else ""
COLOR_ERROR = Fore.RED + Style.BRIGHT if HAS_COLOR else ""
COLOR_WARNING = Fore.YELLOW + Style.BRIGHT if HAS_COLOR else ""
COLOR_INFO = Fore.CYAN + Style.BRIGHT if HAS_COLOR else ""
COLOR_RESET = Style.RESET_ALL if HAS_COLOR else ""

def color_text(text, color):
    """Apply color to text if color support is available."""
    return f"{color}{text}{COLOR_RESET if HAS_COLOR else ''}"

# Configuration
JUMPCLOUD_API_KEY = os.environ.get('JUMPCLOUD_API_KEY')

if not JUMPCLOUD_API_KEY:
    print(color_text("Error: JUMPCLOUD_API_KEY environment variable is not set", COLOR_ERROR))
    print(color_text("Please set it using: export JUMPCLOUD_API_KEY='your_api_key'", COLOR_INFO))
    sys.exit(1)

# JumpCloud API Configuration
BASE_URL = "https://console.jumpcloud.com/api"
HEADERS = {
    "x-api-key": JUMPCLOUD_API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json"
}


def get_target_group_id():
    """Prompt user for target group ID"""
    print(color_text("=" * 60, COLOR_INFO))
    print(color_text("JumpCloud macOS Compliance Management", COLOR_INFO))
    print(color_text("=" * 60, COLOR_INFO))
    
    while True:
        group_id = input("\nEnter target JumpCloud group ID: ").strip()
        
        if group_id:
            confirm = input(f"Group ID: {group_id} - Is this correct? (yes/no): ")
            if confirm.lower() == "yes":
                return group_id
        else:
            print(color_text("Group ID cannot be empty.", COLOR_ERROR))


def get_group_name(group_id):
    """Get the current name of a JumpCloud device group"""
    url = f"{BASE_URL}/v2/systemgroups/{group_id}"
    
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        data = response.json()
        return data.get("name", "Unknown")
    else:
        print(color_text(f"⚠️  Failed to get group name: {response.status_code}", COLOR_WARNING))
        return None


def get_target_version():
    """Prompt user for target macOS version"""
    while True:
        target_version = input("\nEnter target macOS version (e.g., 15.7.1): ").strip()
        
        # Validate version format
        try:
            version.parse(target_version)
            confirm = input(f"Target version: {target_version} - Is this correct? (yes/no): ")
            if confirm.lower() == "yes":
                return target_version
        except Exception as e:
            print(color_text("Invalid version format. Please use format like '15.7.1'", COLOR_ERROR))


def rename_group(group_id, new_name):
    """Rename a JumpCloud device group"""
    url = f"{BASE_URL}/v2/systemgroups/{group_id}"
    
    payload = {
        "name": new_name
    }
    
    response = requests.put(url, headers=HEADERS, json=payload)
    
    if response.status_code == 200:
        print(color_text(f"✅ Group renamed to: {new_name}", COLOR_SUCCESS))
        return True
    else:
        print(color_text(f"⚠️  Failed to rename group: {response.status_code}", COLOR_WARNING))
        print(color_text(f"   {response.text}", COLOR_ERROR))
        return False


def get_all_systems():
    """Fetch all systems from JumpCloud"""
    systems = []
    skip = 0
    limit = 100
    
    print(color_text("Fetching systems from JumpCloud...", COLOR_INFO))
    
    while True:
        url = f"{BASE_URL}/systems"
        params = {
            "skip": skip,
            "limit": limit
        }
        
        response = requests.get(url, headers=HEADERS, params=params)
        
        if response.status_code != 200:
            print(color_text(f"Error fetching systems: {response.status_code}", COLOR_ERROR))
            print(color_text(response.text, COLOR_ERROR))
            sys.exit(1)
        
        data = response.json()
        
        if not data.get("results"):
            break
            
        systems.extend(data["results"])
        
        if len(data["results"]) < limit:
            break
            
        skip += limit
    
    print(color_text(f"Found {len(systems)} total systems", COLOR_SUCCESS))
    return systems


def get_group_members(group_id):
    """Get all system members of a device group"""
    members = []
    skip = 0
    limit = 100
    
    print(color_text(f"Fetching current group members for group {group_id}...", COLOR_INFO))
    
    while True:
        url = f"{BASE_URL}/v2/systemgroups/{group_id}/members"
        params = {
            "skip": skip,
            "limit": limit
        }
        
        response = requests.get(url, headers=HEADERS, params=params)
        
        if response.status_code != 200:
            print(color_text(f"Error fetching group members: {response.status_code}", COLOR_ERROR))
            print(color_text(response.text, COLOR_ERROR))
            return []
        
        data = response.json()
        
        if not data:
            break
        
        # Extract system IDs - handle different possible response structures
        for item in data:
            # Try different possible field names for the ID
            system_id = item.get("id") or item.get("_id") or item.get("to", {}).get("id")
            item_type = item.get("type") or item.get("to", {}).get("type")
            
            if system_id and item_type == "system":
                members.append(system_id)
        
        if len(data) < limit:
            break
            
        skip += limit
    
    print(color_text(f"Found {len(members)} systems currently in group", COLOR_SUCCESS))
    return members


def compare_versions(current_version, target_version):
    """Compare macOS versions. Returns True if current is below target"""
    try:
        return version.parse(current_version) < version.parse(target_version)
    except Exception as e:
        print(color_text(f"Error comparing versions: {e}", COLOR_ERROR))
        return False


def categorize_macs_for_addition(systems, min_version):
    """
    Categorize ALL Macs into compliant and non-compliant
    This is used for determining which systems to ADD to the group
    """
    mac_systems = [
        system for system in systems 
        if system.get("os") == "Mac OS X"
    ]
    
    print(color_text(f"Found {len(mac_systems)} Mac systems", COLOR_INFO))
    
    compliant = []
    non_compliant = []
    
    for system in mac_systems:
        os_version = system.get("version")
        system_id = system.get("_id")
        hostname = system.get("hostname", "Unknown")
        
        if not os_version:
            print(color_text(f"⚠️  {hostname} ({system_id}): No OS version found", COLOR_WARNING))
            continue
        
        if compare_versions(os_version, min_version):
            non_compliant.append(system)
            print(color_text(f"❌ {hostname} ({system_id}): {os_version} < {min_version}", COLOR_ERROR))
        else:
            compliant.append(system)
            print(color_text(f"✅ {hostname} ({system_id}): {os_version} >= {min_version}", COLOR_SUCCESS))
    
    return non_compliant


def identify_compliant_macs_in_group(all_systems, group_member_ids, min_version):
    """
    Identify Mac systems in the group that are compliant
    This is used for determining which systems to REMOVE from the group
    """
    # Create a lookup dict for all systems by ID
    systems_by_id = {s.get("_id"): s for s in all_systems}
    
    compliant_in_group = []
    
    print(color_text(f"\nChecking group members for compliant Macs...", COLOR_INFO))
    print(color_text("-" * 60, COLOR_INFO))
    
    for system_id in group_member_ids:
        system = systems_by_id.get(system_id)
        
        if not system:
            print(color_text(f"⚠️  System {system_id} in group but not found in system list", COLOR_WARNING))
            continue
        
        # Check if it's a Mac
        if system.get("os") != "Mac OS X":
            continue
        
        os_version = system.get("version")
        hostname = system.get("hostname", "Unknown")
        
        if not os_version:
            print(color_text(f"⚠️  {hostname} ({system_id}): No OS version found", COLOR_WARNING))
            continue
        
        # Check if compliant
        if not compare_versions(os_version, min_version):
            compliant_in_group.append(system)
            print(color_text(f"✅ {hostname} ({system_id}): {os_version} >= {min_version} (in group, will remove)", COLOR_SUCCESS))
    
    return compliant_in_group


def add_systems_to_group(system_ids, group_id, already_in_group):
    """Add systems to a device group, skipping those already in the group"""
    url = f"{BASE_URL}/v2/systemgroups/{group_id}/members"
    
    success_count = 0
    skipped_count = 0
    
    for system_id in system_ids:
        # Double-check if already in group
        if system_id in already_in_group:
            print(color_text(f"  ⭐️  Skipping {system_id} (already in group)", COLOR_INFO))
            skipped_count += 1
            continue
        
        payload = {
            "op": "add",
            "type": "system",
            "id": system_id
        }
        
        response = requests.post(url, headers=HEADERS, json=payload)
        
        if response.status_code in [200, 204]:
            print(color_text(f"  ✅ Added {system_id} to group", COLOR_SUCCESS))
            success_count += 1
        elif response.status_code == 409:
            # Already exists - treat as success since end result is the same
            print(color_text(f"  ⭐️  {system_id} already in group (409)", COLOR_INFO))
            skipped_count += 1
        else:
            print(color_text(f"  ❌ Failed to add {system_id}: {response.status_code}", COLOR_ERROR))
            print(color_text(f"     {response.text}", COLOR_ERROR))
    
    return success_count, skipped_count


def remove_systems_from_group(system_ids, group_id):
    """Remove systems from a device group"""
    url = f"{BASE_URL}/v2/systemgroups/{group_id}/members"
    
    success_count = 0
    for system_id in system_ids:
        payload = {
            "op": "remove",
            "type": "system",
            "id": system_id
        }
        
        response = requests.post(url, headers=HEADERS, json=payload)
        
        if response.status_code in [200, 204]:
            print(color_text(f"  ✅ Removed {system_id} from group", COLOR_SUCCESS))
            success_count += 1
        elif response.status_code == 404:
            # Not found in group - treat as success since end result is the same
            print(color_text(f"  ⭐️  {system_id} not in group (404)", COLOR_INFO))
            success_count += 1
        else:
            print(color_text(f"  ❌ Failed to remove {system_id}: {response.status_code}", COLOR_ERROR))
            print(color_text(f"     {response.text}", COLOR_ERROR))
    
    return success_count


def main():
    """Main execution function"""
    # Get target group ID from user
    target_group_id = get_target_group_id()
    
    # Get current group name
    print(color_text(f"\nFetching group information...", COLOR_INFO))
    current_group_name = get_group_name(target_group_id)
    
    if current_group_name:
        print(color_text(f"Current group name: {current_group_name}", COLOR_INFO))
    else:
        print(color_text("⚠️  Could not retrieve group name. Continuing anyway...", COLOR_WARNING))
        current_group_name = "Unknown"
    
    # Get target version from user
    min_macos_version = get_target_version()
    
    # Generate suggested group name based on target version
    suggested_group_name = f"Macs below {min_macos_version}"
    
    print(color_text("\n" + "=" * 60, COLOR_INFO))
    print(color_text(f"Target: Sync group with ALL Macs below {min_macos_version}", COLOR_INFO))
    print(color_text("=" * 60, COLOR_INFO))
    
    # Ask if user wants to rename the group
    if current_group_name != suggested_group_name:
        print(color_text(f"\nCurrent group name: {current_group_name}", COLOR_INFO))
        print(color_text(f"Suggested group name: {suggested_group_name}", COLOR_INFO))
        rename_choice = input("Do you want to rename the group? (yes/no): ")
        
        if rename_choice.lower() == "yes":
            print(color_text(f"\nRenaming group...", COLOR_INFO))
            rename_group(target_group_id, suggested_group_name)
    else:
        print(color_text(f"\nGroup name is already correct: {current_group_name}", COLOR_SUCCESS))
    
    # Fetch all systems
    all_systems = get_all_systems()
    
    # Get current group members
    group_member_list = get_group_members(target_group_id)
    group_member_ids = set(group_member_list)
    
    # ADDITION LOGIC: Find non-compliant Macs (all hostnames)
    print(color_text(f"\nChecking ALL Macs for non-compliance...", COLOR_INFO))
    print(color_text("-" * 60, COLOR_INFO))
    non_compliant = categorize_macs_for_addition(all_systems, min_macos_version)
    
    # REMOVAL LOGIC: Find compliant Macs currently in the group
    compliant_in_group = identify_compliant_macs_in_group(
        all_systems, group_member_ids, min_macos_version
    )
    
    print(color_text("-" * 60, COLOR_INFO))
    print(color_text(f"\n📊 Summary:", COLOR_INFO))
    print(color_text(f"  Non-compliant Macs: {len(non_compliant)}", COLOR_INFO))
    print(color_text(f"  Compliant Macs in group: {len(compliant_in_group)}", COLOR_INFO))
    print(color_text(f"  Total systems currently in group: {len(group_member_ids)}", COLOR_INFO))
    
    # Determine what needs to be added and removed
    non_compliant_ids = {s["_id"] for s in non_compliant}
    compliant_ids_in_group = {s["_id"] for s in compliant_in_group}
    
    # Systems to add: non-compliant but not in group
    to_add = non_compliant_ids - group_member_ids
    
    # Systems to remove: compliant Macs that are in group
    to_remove = compliant_ids_in_group
    
    # Debug output
    already_in_group = non_compliant_ids & group_member_ids
    if already_in_group:
        print(color_text(f"\nℹ️  Note: {len(already_in_group)} non-compliant system(s) already in group (will skip)", COLOR_INFO))
    
    print(color_text(f"\n📋 Actions needed:", COLOR_INFO))
    print(color_text(f"  Systems to ADD to group: {len(to_add)}", COLOR_INFO))
    print(color_text(f"  Systems to REMOVE from group: {len(to_remove)}", COLOR_INFO))
    
    if not to_add and not to_remove:
        print(color_text("\n✅ Group is already up to date! No changes needed.", COLOR_SUCCESS))
        return
    
    # Show details of systems to be changed
    if to_add:
        print(color_text(f"\n➕ Systems to ADD (non-compliant, not in group):", COLOR_INFO))
        for system in non_compliant:
            if system["_id"] in to_add:
                hostname = system.get("hostname", "Unknown")
                os_version = system.get("version", "Unknown")
                print(color_text(f"  - {hostname} ({os_version})", COLOR_INFO))
    
    if to_remove:
        print(color_text(f"\n➖ Systems to REMOVE (compliant Macs in group):", COLOR_INFO))
        for system in compliant_in_group:
            if system["_id"] in to_remove:
                hostname = system.get("hostname", "Unknown")
                os_version = system.get("version", "Unknown")
                print(color_text(f"  - {hostname} ({os_version})", COLOR_INFO))
    
    # Perform additions (with separate confirmation)
    added_count = 0
    skipped_count = 0
    if to_add:
        print(color_text("\n" + "=" * 60, COLOR_INFO))
        print(color_text(f"➕ Ready to ADD {len(to_add)} system(s) to group", COLOR_INFO))
        confirm_add = input("Add these systems? (yes/no): ")
        
        if confirm_add.lower() == "yes":
            print(color_text(f"\nAdding {len(to_add)} system(s) to group...", COLOR_INFO))
            added_count, skipped_count = add_systems_to_group(list(to_add), target_group_id, group_member_ids)
            print(color_text(f"✅ Successfully added {added_count}/{len(to_add)} systems (skipped {skipped_count})", COLOR_SUCCESS))
        else:
            print(color_text("❌ Skipped adding systems", COLOR_WARNING))
    
    # Perform removals (with separate confirmation)
    removed_count = 0
    if to_remove:
        print(color_text("\n" + "=" * 60, COLOR_INFO))
        print(color_text(f"➖ Ready to REMOVE {len(to_remove)} system(s) from group", COLOR_INFO))
        confirm_remove = input("Remove these systems? (yes/no): ")
        
        if confirm_remove.lower() == "yes":
            print(color_text(f"\nRemoving {len(to_remove)} system(s) from group...", COLOR_INFO))
            removed_count = remove_systems_from_group(list(to_remove), target_group_id)
            print(color_text(f"✅ Successfully removed {removed_count}/{len(to_remove)} systems", COLOR_SUCCESS))
        else:
            print(color_text("❌ Skipped removing systems", COLOR_WARNING))
    
    # Final summary
    print(color_text("\n" + "=" * 60, COLOR_INFO))
    print(color_text("✅ Operation complete!", COLOR_SUCCESS))
    print(color_text(f"   Added: {added_count}", COLOR_INFO))
    print(color_text(f"   Skipped: {skipped_count}", COLOR_INFO))
    print(color_text(f"   Removed: {removed_count}", COLOR_INFO))
    print(color_text("=" * 60, COLOR_INFO))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(color_text("\n\nOperation cancelled by user", COLOR_WARNING))
        sys.exit(0)
    except Exception as e:
        print(color_text(f"\n❌ Unexpected error: {e}", COLOR_ERROR))
        sys.exit(1)
