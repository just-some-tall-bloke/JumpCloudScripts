#!/usr/bin/env python3
# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/
"""
JumpCloud API Script to export Macs below a specified macOS version with primary user
Outputs CSV with system details and primary user username
"""

import os
import sys
import requests
import csv
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from tqdm import tqdm

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    COLOR_SUCCESS = Fore.GREEN + Style.BRIGHT
    COLOR_ERROR   = Fore.RED   + Style.BRIGHT
    COLOR_WARNING = Fore.YELLOW + Style.BRIGHT
    COLOR_INFO    = Fore.CYAN  + Style.BRIGHT
    COLOR_RESET   = Style.RESET_ALL
except ImportError:
    COLOR_SUCCESS = COLOR_ERROR = COLOR_WARNING = COLOR_INFO = COLOR_RESET = ""


def color_text(text, color):
    """Apply color to text if color support is available."""
    return f"{color}{text}{COLOR_RESET}"


def get_api_key() -> str:
    """Get API key from environment variable"""
    api_key = os.getenv('JUMPCLOUD_API_KEY')
    if not api_key:
        print(color_text("Error: JUMPCLOUD_API_KEY environment variable is not set", COLOR_ERROR))
        print(color_text("Please set it using: export JUMPCLOUD_API_KEY='your_api_key'", COLOR_INFO))
        print(color_text("Or add to your shell profile for persistent setting", COLOR_INFO))
        sys.exit(1)
    return api_key


def get_user_input() -> tuple[str, int]:
    """Get target macOS version and days filter from user"""
    target_version = input("Enter the macOS version to check against (e.g., 15.7.0): ").strip()
    if not target_version:
        target_version = "15.7.0"
        print(color_text(f"Using default version: {target_version}", COLOR_INFO))
    
    days_input = input("Enter number of days for last contact filter (e.g., 7): ").strip()
    if not days_input:
        days = 7
        print(color_text("Using default: 7 days", COLOR_INFO))
    else:
        try:
            days = int(days_input)
        except ValueError:
            print(color_text("Invalid days input, using default: 7 days", COLOR_ERROR))
            days = 7
    
    return target_version, days


def get_all_systems(api_key: str) -> List[Dict[str, Any]]:
    """Get all systems with pagination"""
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    
    all_systems = []
    skip = 0
    limit = 100
    
    while True:
        uri = f"https://console.jumpcloud.com/api/systems?limit={limit}&skip={skip}"
        
        try:
            response = requests.get(uri, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if not data.get('results'):
                break
            
            all_systems.extend(data['results'])
            skip += limit
            
            if skip >= data.get('totalCount', 0):
                break
                
        except requests.RequestException as e:
            print(color_text(f"Error fetching systems: {e}", COLOR_ERROR))
            break
    
    return all_systems


def get_user_by_id(api_key: str, user_id: str) -> str:
    """Get user details by ID"""
    if not user_id:
        return ""
    
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    
    uri = f"https://console.jumpcloud.com/api/systemusers/{user_id}"
    
    try:
        response = requests.get(uri, headers=headers)
        response.raise_for_status()
        user_data = response.json()
        return user_data.get('username', '')
    except requests.RequestException:
        print(color_text(f"Warning: Could not fetch user {user_id}", COLOR_WARNING))
        return ""


def compare_macos_version(version1: str, comparison_version: str) -> bool:
    """Compare version numbers - returns True if version1 is less than comparison_version"""
    try:
        v1_parts = [int(x) for x in version1.split('.')]
        v2_parts = [int(x) for x in comparison_version.split('.')]
        
        # Pad arrays to same length
        max_length = max(len(v1_parts), len(v2_parts))
        v1_parts.extend([0] * (max_length - len(v1_parts)))
        v2_parts.extend([0] * (max_length - len(v2_parts)))
        
        for v1_val, v2_val in zip(v1_parts, v2_parts):
            if v1_val < v2_val:
                return True  # version1 is less than target
            elif v1_val > v2_val:
                return False  # version1 is greater than target
        
        return False  # versions are equal
        
    except (ValueError, AttributeError):
        # If we can't parse the version, assume it doesn't meet criteria
        return False


def main():
    """Main function"""
    # Get API key
    api_key = get_api_key()
    
    # Get user input
    target_version, days = get_user_input()
    
    # Generate output filename
    output_file = f"mac_systems_below_{target_version.replace('.', '_')}_last_{days}_days.csv"
    
    print(color_text("Fetching all systems from JumpCloud...", COLOR_INFO))
    systems = get_all_systems(api_key)
    
    if not systems:
        print(color_text("No systems found or error occurred", COLOR_ERROR))
        sys.exit(1)
    
    print(color_text(f"Found {len(systems)} total systems", COLOR_SUCCESS))
    
    # Filter for Mac systems below target version
    mac_systems_below_target = []
    cutoff_date = datetime.now() - timedelta(days=days)
    
    for system in tqdm(systems, desc="Processing systems", unit="sys"):
        # Check if it's a Mac
        if system.get('os') == "Mac OS X":
            # Check version
            version = system.get('version', '')
            if version and compare_macos_version(version, target_version):
                # Check last contact date (within specified days)
                last_contact_date = None
                try:
                    last_contact_str = system.get('lastContact', '')
                    if last_contact_str:
                        last_contact_date = datetime.fromisoformat(last_contact_str.replace('Z', '+00:00'))
                        if last_contact_date < cutoff_date:
                            continue  # Skip systems not contacted within specified days
                except (ValueError, AttributeError):
                    continue  # Skip if we can't parse the date

                last_contact_display = last_contact_date.strftime('%Y-%m-%d') if last_contact_date else 'Unknown'
                tqdm.write(color_text(f"Found Mac below {target_version}: {system.get('hostname')} (v{version}) - Last seen: {last_contact_display}", COLOR_WARNING))

                # Get primary user username if exists
                primary_username = ""
                primary_user_id = system.get('primaryUser', '')
                if primary_user_id:
                    primary_username = get_user_by_id(api_key, primary_user_id)

                # Create dictionary for CSV
                system_data = {
                    'Hostname': system.get('hostname', ''),
                    'DisplayName': system.get('displayName', ''),
                    'MacOSVersion': version,
                    'SerialNumber': system.get('serialNumber', ''),
                    'PrimaryUsername': primary_username,
                    'PrimaryUserID': primary_user_id,
                    'SystemID': system.get('_id', ''),
                    'LastContact': system.get('lastContact', ''),
                    'Active': system.get('active', False)
                }
                mac_systems_below_target.append(system_data)
    
    if mac_systems_below_target:
        # Export to CSV
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            if mac_systems_below_target:
                fieldnames = mac_systems_below_target[0].keys()
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(mac_systems_below_target)
        
        print(color_text("\nExport complete!", COLOR_SUCCESS))
        print(color_text(f"Found {len(mac_systems_below_target)} Mac systems below macOS {target_version} (active in last {days} days)", COLOR_SUCCESS))
        print(color_text(f"Results saved to: {output_file}", COLOR_SUCCESS))
        
        # Display summary
        print(color_text("\nSummary of systems found:", COLOR_INFO))
        print(f"{'Hostname':<30} {'MacOSVersion':<15} {'PrimaryUsername':<20} {'LastContact'}")
        print("-" * 80)
        for system in mac_systems_below_target:
            last_contact_short = system['LastContact'][:10] if system['LastContact'] else 'N/A'
            print(f"{system['Hostname'][:30]:<30} {system['MacOSVersion']:<15} {system['PrimaryUsername'][:20]:<20} {last_contact_short}")
    else:
        print(color_text(f"\nNo Mac systems found below macOS {target_version} that were active in the last {days} days", COLOR_WARNING))
    
    print(color_text("\nScript completed!", COLOR_SUCCESS))


if __name__ == "__main__":
    main()