#!/usr/bin/env python3
# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/

import os
import sys
import time
import logging
import requests
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Optional, Any
try:
    from colorama import init, Fore, Back, Style
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
    Back = _ColorFallback()
    Style = _StyleFallback()

# --- Configuration ---
# !! SET DRY_RUN TO False TO ENABLE DELETION !!
DRY_RUN = True
# Get your API key from the JumpCloud Admin Portal
# It's best practice to set this as an environment variable
API_KEY = os.environ.get("JUMPCLOUD_API_KEY")
BASE_URL = "https://console.jumpcloud.com/api"

# Rate limiting: seconds to wait between API calls
RATE_LIMIT_DELAY = 0.1

# --- End Configuration ---

# --- Color Constants ---
if HAS_COLOR:
    COLOR_SUCCESS = Fore.GREEN + Style.BRIGHT
    COLOR_ERROR = Fore.RED + Style.BRIGHT
    COLOR_WARNING = Fore.YELLOW + Style.BRIGHT
    COLOR_INFO = Fore.CYAN + Style.BRIGHT
    COLOR_PROGRESS = Fore.BLUE + Style.BRIGHT
    COLOR_RESET = Style.RESET_ALL
    COLOR_BAR_FILL = Fore.GREEN
    COLOR_BAR_EMPTY = Fore.WHITE
    COLOR_DRY_RUN = Fore.YELLOW + Back.BLUE
    COLOR_HIGHLIGHT = Fore.MAGENTA + Style.BRIGHT
    COLOR_DIM = Fore.WHITE + Style.DIM
    COLOR_HEADER = Fore.BLUE + Back.WHITE + Style.BRIGHT
    COLOR_BORDER = Fore.CYAN
else:
    COLOR_SUCCESS = COLOR_ERROR = COLOR_WARNING = COLOR_INFO = ""
    COLOR_PROGRESS = COLOR_RESET = COLOR_BAR_FILL = COLOR_BAR_EMPTY = ""
    COLOR_DRY_RUN = COLOR_HIGHLIGHT = COLOR_DIM = COLOR_HEADER = COLOR_BORDER = ""

def color_text(text: str, color: str) -> str:
    """Apply color to text if color support is available."""
    return f"{color}{text}{COLOR_RESET if HAS_COLOR else ''}"

# Custom colored logging formatter
class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors to log messages."""
    
    COLORS = {
        'DEBUG': COLOR_PROGRESS,
        'INFO': COLOR_INFO,
        'WARNING': COLOR_WARNING,
        'ERROR': COLOR_ERROR,
        'CRITICAL': COLOR_ERROR + Back.RED
    }
    
    def format(self, record):
        if HAS_COLOR:
            # Add color to the level name
            levelname = record.levelname
            if levelname in self.COLORS:
                record.levelname = f"{self.COLORS[levelname]}{levelname}{COLOR_RESET}"
        return super().format(record)

# Logging configuration
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(message)s'))

file_handler = logging.FileHandler('delete_dupes.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler]
)

def validate_configuration() -> bool:
    """Validate required configuration is present."""
    if not API_KEY:
        logging.error(color_text("JUMPCLOUD_API_KEY environment variable not set.", COLOR_ERROR))
        logging.error(color_text("Please set it before running the script:", COLOR_ERROR))
        logging.info(color_text("export JUMPCLOUD_API_KEY='your_api_key_here'", COLOR_INFO))
        return False
    return True

HEADERS = {
    "x-api-key": API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

def get_all_systems() -> Optional[List[Dict[str, Any]]]:
    """
    Fetches all systems from JumpCloud, handling pagination.
    Returns a list of system objects or None if error occurs.
    """
    print(color_text("[*] Fetching all systems from JumpCloud...", COLOR_INFO))
    systems = []
    limit = 100
    skip = 0
    total_count = None
    
    # First, get the total count to set up the progress bar
    try:
        url = f"{BASE_URL}/systems"
        params = {
            "fields": 'id serialNumber lastContact hostname os',
            "limit": limit,
            "skip": 0
        }
        res = requests.get(url, headers=HEADERS, params=params)
        res.raise_for_status()
        data = res.json()
        if isinstance(data, dict) and 'totalCount' in data:
            total_count = data['totalCount']
            print(color_text(f"Total systems in JumpCloud: {total_count}", COLOR_INFO))
    except:
        pass  # If we can't get total count, we'll use an indeterminate progress bar
    
    # Simple progress bar function
    def update_progress(current, total=None):
        if total:
            percentage = (current / total) * 100
            bar_length = 50
            filled_length = int(bar_length * current // total)
            bar = color_text('=' * filled_length, COLOR_BAR_FILL) + color_text('-' * (bar_length - filled_length), COLOR_BAR_EMPTY)
            sys.stdout.write(f'\r{color_text("Fetching systems:", COLOR_PROGRESS)} |{bar}| {current}/{total} ({percentage:.1f}%)')
        else:
            sys.stdout.write(f'\r{color_text("Fetching systems:", COLOR_PROGRESS)} {current} systems fetched...')
        sys.stdout.flush()
    
    while True:
        url = f"{BASE_URL}/systems"
        params = {
            # Select only the fields we need
            "fields": 'id serialNumber lastContact hostname os',
            "limit": limit,
            "skip": skip
        }
        
        try:
            res = requests.get(url, headers=HEADERS, params=params)
            res.raise_for_status()  # Raise an error for bad responses (4xx, 5xx)
            
            data = res.json()
            
            # V1 API returns results in a dict with 'results' key
            if isinstance(data, dict) and 'results' in data:
                results = data['results']
            else:
                results = data if isinstance(data, list) else []
                
            if not results:
                break  # No more results
                
            systems.extend(results)
            update_progress(len(systems), total_count)
            skip += limit
            
            # Rate limiting
            time.sleep(RATE_LIMIT_DELAY)
            
            if len(results) < limit:
                break # We've reached the last page
                
        except requests.exceptions.RequestException as e:
            print()  # New line after progress bar
            logging.error(color_text(f"Error fetching systems: {e}", COLOR_ERROR))
            if hasattr(e, 'response') and e.response:
                logging.error(color_text(f"Response body: {e.response.text}", COLOR_ERROR))
            return None
        except ValueError as e:
            print()  # New line after progress bar
            logging.error(color_text(f"Error parsing JSON response: {e}", COLOR_ERROR))
            return None

    print()  # New line after progress bar
    print(color_text(f"[+] Found {len(systems)} total systems.", COLOR_SUCCESS))
    return systems

def find_duplicates(systems_list: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Groups systems by serial number to find duplicates.
    Filters out empty or "None" serial numbers.
    """
    logging.info(color_text("[SCAN] Scanning for duplicate serial numbers...", COLOR_HIGHLIGHT))
    systems_by_serial = defaultdict(list)
    invalid_serials = 0
    
    for system in systems_list:
        serial = system.get("serialNumber")
        
        # Skip devices with no serial number
        if not serial or serial == "None" or not serial.strip():
            invalid_serials += 1
            continue
            
        systems_by_serial[serial].append(system)
    
    # Filter down to only serials with more than one entry
    duplicates = {
        serial: systems
        for serial, systems in systems_by_serial.items()
        if len(systems) > 1
    }
    
    logging.info(color_text(f"[!] Found {len(duplicates)} serial number(s) with duplicate entries.", COLOR_WARNING))
    logging.info(color_text(f"[i] Skipped {invalid_serials} systems with invalid serial numbers.", COLOR_INFO))
    return duplicates

def parse_iso_datetime(date_string: Optional[str]) -> datetime:
    """
    Parses JumpCloud's ISO 8601 timestamp into a datetime object.
    Handles the 'Z' (Zulu/UTC) suffix and various timestamp formats.
    """
    if not date_string:
        # If lastContact is None, treat it as the oldest possible date
        return datetime.min.replace(tzinfo=None)
    
    try:
        # datetime.fromisoformat() in older Python versions can't handle 'Z'
        if date_string.endswith('Z'):
            date_string = date_string[:-1] + '+00:00'
        return datetime.fromisoformat(date_string)
    except ValueError as e:
        logging.warning(color_text(f"Could not parse timestamp '{date_string}': {e}", COLOR_WARNING))
        # Return a very old date so it gets prioritized for deletion
        return datetime.min.replace(tzinfo=None)

def delete_system(system_id: str, hostname: str) -> bool:
    """
    Deletes a single system by its ID.
    Returns True if successful, False otherwise.
    """
    url = f"{BASE_URL}/systems/{system_id}"
    
    if DRY_RUN:
        logging.info(f"  {color_text('[DRY RUN]', COLOR_DRY_RUN)} Would delete: {color_text(hostname, COLOR_DIM)} (ID: {system_id})")
        return True
        
    try:
        logging.info(f"  {color_text('[ACTION]', COLOR_WARNING)} Deleting: {color_text(hostname, COLOR_DIM)} (ID: {system_id})...")
        res = requests.delete(url, headers=HEADERS)
        res.raise_for_status()
        
        if res.status_code in [200, 204]: # Both 200 OK and 204 No Content are success
            logging.info(f"  {color_text('[SUCCESS]', COLOR_SUCCESS)} Deleted {hostname}.")
            return True
        else:
            logging.error(f"  {color_text('[FAILED]', COLOR_ERROR)} Unexpected status code {res.status_code} for {hostname}.")
            return False
            
    except requests.exceptions.RequestException as e:
        logging.error(f"  {color_text('[ERROR]', COLOR_ERROR)} Failed to delete {hostname}: {e}")
        if hasattr(e, 'response') and e.response:
            logging.error(color_text(f"  Response body: {e.response.text}", COLOR_ERROR))
        return False
    finally:
        # Rate limiting
        if not DRY_RUN:
            time.sleep(RATE_LIMIT_DELAY)

def process_duplicates(duplicate_groups: Dict[str, List[Dict[str, Any]]]) -> None:
    """
    For each group of duplicates, finds the newest one and deletes the rest.
    """
    if not duplicate_groups:
        logging.info(color_text("No duplicates to process.", COLOR_INFO))
        return

    if DRY_RUN:
        print(color_text("\n" + "="*50, COLOR_BORDER))
        print(color_text("*** STARTING DRY RUN MODE ***", COLOR_DRY_RUN))
        print(color_text("="*50, COLOR_BORDER))
        logging.info(color_text("The following actions would be taken:", COLOR_INFO))
    else:
        print(color_text("\n" + "!"*50, COLOR_ERROR))
        print(color_text("! STARTING DELETION RUN - PERMANENT ACTION !", COLOR_ERROR + Back.RED))
        print(color_text("!"*50, COLOR_ERROR))
        logging.warning(color_text("WARNING: This is permanent. Deleting devices...", COLOR_WARNING + Back.RED))

    total_deleted = 0
    total_groups = len(duplicate_groups)
    processed_groups = 0
    
    for serial, systems in duplicate_groups.items():
        processed_groups += 1
        print(color_text(f"\n[PROC] Processing Serial Number: {serial} ({len(systems)} entries) - Group {processed_groups}/{total_groups}", COLOR_INFO))
        print(color_text("-" * 60, COLOR_BORDER))
        
        # Sort the systems by lastContact time, newest first
        # We use our custom parser to handle the timestamp format
        try:
            sorted_systems = sorted(
                systems,
                key=lambda s: parse_iso_datetime(s.get("lastContact")),
                reverse=True
            )
        except Exception as e:
            logging.error(f"  {color_text('[ERROR]', COLOR_ERROR)} Could not sort systems for serial {serial}: {e}")
            continue

        # The first item in the sorted list is the one we keep
        keep = sorted_systems[0]
        keep_hostname = keep.get('hostname', keep.get('displayName', 'Unknown'))
        logging.info(f"  {color_text('[KEEP] Keeping newest:', COLOR_SUCCESS)} {color_text(keep_hostname, COLOR_HIGHLIGHT)} (Last contact: {keep.get('lastContact')})")
        
        # All other items in the list are deleted
        to_delete = sorted_systems[1:]
        
        for system in to_delete:
            hostname = system.get('hostname', system.get('displayName', 'Unknown'))
            success = delete_system(system['id'], hostname)
            if success:
                total_deleted += 1

    print(color_text("\n" + "="*50, COLOR_BORDER))
    print(color_text("*** RUN COMPLETE ***", COLOR_SUCCESS))
    print(color_text("="*50, COLOR_BORDER))
    
    if DRY_RUN:
        logging.info(f"{color_text('[DRY] Dry run finished.', COLOR_DRY_RUN)} Would have deleted {color_text(str(total_deleted), COLOR_WARNING)} device(s).")
        logging.info(color_text("[INFO] To run for real, set DRY_RUN = False at the top of the script.", COLOR_INFO))
    else:
        logging.info(f"{color_text('[DONE] Deletion run finished.', COLOR_SUCCESS)} {color_text(str(total_deleted), COLOR_WARNING)} device(s) deleted.")
        print(color_text("\n*** All duplicates processed successfully! ***", COLOR_SUCCESS))

def main() -> None:
    """Main execution function."""
    # Print colorful header
    print(color_text("=" * 60, COLOR_BORDER))
    print(color_text("  JumpCloud Duplicate System Remover  ", COLOR_HEADER))
    print(color_text("=" * 60, COLOR_BORDER))
    print()
    
    if not validate_configuration():
        print(color_text("Configuration validation failed. Exiting.", COLOR_ERROR))
        sys.exit(1)
    
    try:
        all_systems = get_all_systems()
        if all_systems is None:
            logging.error(color_text("Failed to retrieve systems from JumpCloud.", COLOR_ERROR))
            sys.exit(1)
            
        duplicate_groups = find_duplicates(all_systems)
        process_duplicates(duplicate_groups)
        
    except KeyboardInterrupt:
        print(color_text("\n[!] Script interrupted by user.", COLOR_WARNING))
        logging.warning(color_text("\nScript interrupted by user.", COLOR_WARNING))
        sys.exit(1)
    except Exception as e:
        print(color_text(f"\n[ERROR] Unexpected error: {e}", COLOR_ERROR))
        logging.error(f"{color_text('Unexpected error:', COLOR_ERROR)} {e}")
        sys.exit(1)
    finally:
        print(color_text("\n[*] Goodbye!", COLOR_INFO))

# --- Main execution ---
if __name__ == "__main__":
    main()