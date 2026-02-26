#!/usr/bin/env python3
# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/

"""
Device High Uptime Grouping Script
- Adds systems with uptime > 14 days to a device group
- Only adds systems that have contacted the MDM in the last 7 days
- Removes systems that have rebooted (uptime <= 14 days)
- Removes systems that haven't contacted the MDM in the last 7 days
"""

import requests
import sys
import os
import time
from datetime import datetime, timedelta, timezone
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import multiprocessing
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
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
JUMPCLOUD_API_KEY = os.environ.get("JUMPCLOUD_API_KEY")

if not JUMPCLOUD_API_KEY:
    print(color_text("Error: JUMPCLOUD_API_KEY environment variable is not set", COLOR_ERROR))
    print(color_text("Please set it using: export JUMPCLOUD_API_KEY='your_api_key'", COLOR_INFO))
    sys.exit(1)

# JumpCloud API Configuration
BASE_URL = "https://console.jumpcloud.com/api"
HEADERS = {
    "x-api-key": JUMPCLOUD_API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Configuration
UPTIME_THRESHOLD_DAYS = 14
CONTACT_WINDOW_DAYS = 7

# Parallel processing configuration
DEFAULT_MAX_WORKERS = min(20, multiprocessing.cpu_count() * 2)
RATE_LIMIT_DELAY = 0.1  # 100ms delay between requests to avoid rate limiting
BATCH_SIZE = 50  # Process devices in batches for better memory management


class RateLimiter:
    """Adaptive rate limiter to control request frequency"""

    def __init__(self, base_delay=RATE_LIMIT_DELAY):
        self.base_delay = base_delay
        self.current_delay = base_delay
        self.last_call = 0
        self.lock = threading.Lock()
        self.response_times = []
        self.error_count = 0
        self.success_count = 0

    def update_delay(self, response_time, is_error=False):
        """Adjust delay based on response time and error rate"""
        with self.lock:
            if is_error:
                self.error_count += 1
                # Increase delay on errors
                self.current_delay = min(self.current_delay * 1.5, 2.0)
            else:
                self.success_count += 1
                self.response_times.append(response_time)

                # Keep only recent response times
                if len(self.response_times) > 10:
                    self.response_times.pop(0)

                # Adjust delay based on average response time
                if len(self.response_times) >= 3:
                    avg_response_time = sum(self.response_times) / len(
                        self.response_times
                    )

                    # If responses are fast, we can reduce delay
                    if (
                        avg_response_time < 0.5
                        and self.error_count < self.success_count * 0.1
                    ):
                        self.current_delay = max(
                            self.base_delay, self.current_delay * 0.9
                        )
                    # If responses are slow, increase delay
                    elif avg_response_time > 2.0:
                        self.current_delay = min(self.current_delay * 1.2, 1.0)

    def wait(self):
        """Wait if necessary to respect rate limit"""
        with self.lock:
            current_time = time.time()
            time_since_last = current_time - self.last_call

            if time_since_last < self.current_delay:
                time.sleep(self.current_delay - time_since_last)

            self.last_call = time.time()


# Global rate limiter instance
rate_limiter = RateLimiter()


# Create a session with connection pooling and retry strategy
def create_optimized_session():
    """Create an optimized requests session with connection pooling and retries"""
    session = requests.Session()

    # Configure retry strategy
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PUT"],
    )

    # Configure HTTP adapter with connection pooling
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=DEFAULT_MAX_WORKERS,
        pool_maxsize=DEFAULT_MAX_WORKERS * 2,
        pool_block=False,
    )

    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(HEADERS)

    return session


# Global optimized session
optimized_session = create_optimized_session()


def get_target_group_id():
    """Prompt user for target group ID"""
    print(color_text("=" * 60, COLOR_INFO))
    print(color_text("JumpCloud High Uptime Management", COLOR_INFO))
    print(color_text(f"Systems with uptime > {UPTIME_THRESHOLD_DAYS} days", COLOR_INFO))
    print(color_text("=" * 60, COLOR_INFO))

    while True:
        group_id = input("\nEnter target JumpCloud group ID: ").strip()

        if group_id:
            confirm = input(f"Group ID: {group_id} - Is this correct? (y/n): ")
            if confirm.lower() == "y":
                return group_id
        else:
            print(color_text("Group ID cannot be empty.", COLOR_ERROR))


def get_group_name(group_id):
    """Get the current name of a JumpCloud device group"""
    url = f"{BASE_URL}/v2/systemgroups/{group_id}"

    response = optimized_session.get(url, timeout=30)

    if response.status_code == 200:
        data = response.json()
        return data.get("name", "Unknown")
    else:
        print(color_text(f"⚠️  Failed to get group name: {response.status_code}", COLOR_WARNING))
        return None


def rename_group(group_id, new_name):
    """Rename a JumpCloud device group"""
    url = f"{BASE_URL}/v2/systemgroups/{group_id}"

    payload = {"name": new_name}

    response = optimized_session.put(url, json=payload, timeout=30)

    if response.status_code == 200:
        print(color_text(f"✅ Group renamed to: {new_name}", COLOR_SUCCESS))
        return True
    else:
        print(color_text(f"⚠️  Failed to rename group: {response.status_code}", COLOR_WARNING))
        print(color_text(f"   {response.text}", COLOR_ERROR))
        return False


def has_contacted_recently(system, days=7):
    """Check if system has contacted JumpCloud within the last N days"""
    last_contact = system.get("lastContact")

    if not last_contact:
        return False

    try:
        last_contact_dt = datetime.fromisoformat(last_contact.replace("Z", "+00:00"))
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        return last_contact_dt >= cutoff_date
    except Exception as e:
        print(color_text(f"  ⚠️  Error parsing lastContact date: {e}", COLOR_WARNING))
        return False


def get_all_systems():
    """Fetch all systems from JumpCloud"""
    systems = []
    skip = 0
    limit = 100
    page = 1

    print(color_text("Fetching systems from JumpCloud...", COLOR_INFO))

    # Create progress bar for fetching pages
    with tqdm(desc="Fetching systems from JumpCloud", unit="pages") as pbar:
        while True:
            url = f"{BASE_URL}/systems"
            params = {"skip": skip, "limit": limit}

            response = optimized_session.get(url, params=params, timeout=30)

            if response.status_code != 200:
                print(color_text(f"Error fetching systems: {response.status_code}", COLOR_ERROR))
                print(color_text(response.text, COLOR_ERROR))
                sys.exit(1)

            data = response.json()

            if not data.get("results"):
                break

            systems.extend(data["results"])

            # Update progress bar with current page
            pbar.set_description("Fetching systems from JumpCloud")
            pbar.update(1)
            pbar.set_postfix_str(f"page {page}, {len(systems)} systems")
            page += 1

            if len(data["results"]) < limit:
                break

            skip += limit

    print(color_text(f"Found {len(systems)} total systems", COLOR_SUCCESS))
    return systems


def get_system_uptime(system_id):
    """Get uptime for a specific system using System Insights API"""
    url = f"{BASE_URL}/v2/systeminsights/{system_id}/uptime"

    try:
        start_time = time.time()
        response = optimized_session.get(url, timeout=30)
        response_time = time.time() - start_time

        if response.status_code == 200:
            rate_limiter.update_delay(response_time, False)
            data = response.json()
            if data and len(data) > 0:
                uptime_data = data[0]
                days = uptime_data.get("days", 0)
                return days
            return None
        else:
            rate_limiter.update_delay(response_time, True)
            return None
    except Exception as e:
        rate_limiter.update_delay(1.0, True)  # Assume 1s response time for errors
        return None


def get_group_members(group_id):
    """Get all system members of a device group"""
    members = []
    skip = 0
    limit = 100

    print(color_text(f"Fetching current group members for group {group_id}...", COLOR_INFO))

    while True:
        url = f"{BASE_URL}/v2/systemgroups/{group_id}/members"
        params = {"skip": skip, "limit": limit}

        response = optimized_session.get(url, params=params, timeout=30)

        if response.status_code != 200:
            print(color_text(f"Error fetching group members: {response.status_code}", COLOR_ERROR))
            print(color_text(response.text, COLOR_ERROR))
            return []

        data = response.json()

        if not data:
            break

        for item in data:
            system_id = (
                item.get("id") or item.get("_id") or item.get("to", {}).get("id")
            )
            item_type = item.get("type") or item.get("to", {}).get("type")

            if system_id and item_type == "system":
                members.append(system_id)

        if len(data) < limit:
            break

        skip += limit

    print(color_text(f"Found {len(members)} systems currently in group", COLOR_SUCCESS))
    return members


def get_system_uptime_with_contact_check(system):
    """Get uptime for a system and check contact status - used for parallel processing"""
    system_id = system.get("_id")

    # Check if contacted recently
    if not has_contacted_recently(system, CONTACT_WINDOW_DAYS):
        return system, "stale", None

    # Apply rate limiting
    rate_limiter.wait()

    # Get uptime
    uptime_days = get_system_uptime(system_id)

    if uptime_days is None:
        return system, "no_uptime_data", None

    # Store uptime in system dict for later use
    system["uptime_days"] = uptime_days

    if uptime_days > UPTIME_THRESHOLD_DAYS:
        return system, "high_uptime", uptime_days
    else:
        return system, "low_uptime", uptime_days


def categorize_systems_by_uptime(systems, uptime_threshold, contact_window_days=7):
    """
    Categorize systems based on uptime using parallel processing
    Only includes Mac systems with hostname starting with "MAC"
    Only includes systems that have contacted JumpCloud recently
    """
    high_uptime_eligible = []
    low_uptime = []
    stale_systems = []
    no_uptime_data = []
    excluded_not_mac = []
    excluded_bad_hostname = []

    # Filter to only Mac systems with hostname starting with "MAC"
    mac_systems = [
        system
        for system in systems
        if system.get("os") == "Mac OS X"
        and system.get("hostname", "").upper().startswith("MAC")
    ]

    # Count excluded systems
    for system in systems:
        if system.get("os") != "Mac OS X":
            excluded_not_mac.append(system)
        elif not system.get("hostname", "").upper().startswith("MAC"):
            excluded_bad_hostname.append(system)

    print(color_text(f"\nFound {len(mac_systems)} Mac systems with hostname starting with MAC", COLOR_INFO))
    print(
        color_text(
            f"Excluded: {len(excluded_not_mac)} non-Mac systems, {len(excluded_bad_hostname)} Macs without MAC* hostname",
            COLOR_INFO
        )
    )
    print(color_text(f"\nChecking system uptimes (threshold: {uptime_threshold} days)...", COLOR_INFO))
    print(color_text("-" * 80, COLOR_INFO))

    if not mac_systems:
        print(color_text("No Mac systems to check", COLOR_WARNING))
        return high_uptime_eligible, low_uptime, stale_systems, no_uptime_data

    # Use parallel processing for uptime checks
    with ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_system = {
            executor.submit(get_system_uptime_with_contact_check, system): system
            for system in mac_systems
        }

        # Process completed tasks as they finish
        completed_count = 0
        for future in as_completed(future_to_system):
            system, result_type, uptime_days = future.result()
            completed_count += 1

            hostname = system.get("hostname", "Unknown")
            display_name = system.get("displayName", "Unknown")
            os = system.get("os", "Unknown")
            last_contact = system.get("lastContact", "Never")

            print(
                f"[{completed_count}/{len(mac_systems)}] Checking {hostname} ({os})...",
                end=" ",
            )

            if result_type == "stale":
                stale_systems.append(system)
                print(color_text(f"⏸️  STALE (last: {last_contact})", COLOR_WARNING))
            elif result_type == "no_uptime_data":
                no_uptime_data.append(system)
                print(color_text(f"⚠️  No uptime data", COLOR_WARNING))
            elif result_type == "high_uptime":
                high_uptime_eligible.append(system)
                print(color_text(f"⚠️  HIGH uptime: {uptime_days} days", COLOR_WARNING))
            elif result_type == "low_uptime":
                low_uptime.append(system)
                print(color_text(f"✅ Low uptime (good): {uptime_days} days", COLOR_SUCCESS))

    print(color_text("-" * 80, COLOR_INFO))
    print(color_text(f"\n📊 Summary:", COLOR_INFO))
    print(color_text(f"  High uptime (>{uptime_threshold} days): {len(high_uptime_eligible)}", COLOR_INFO))
    print(color_text(f"  Low uptime (≤{uptime_threshold} days): {len(low_uptime)}", COLOR_INFO))
    print(color_text(f"  Stale (>{contact_window_days} days no contact): {len(stale_systems)}", COLOR_INFO))
    print(color_text(f"  No uptime data: {len(no_uptime_data)}", COLOR_INFO))

    return high_uptime_eligible, low_uptime, stale_systems, no_uptime_data


def check_system_for_removal(system, uptime_threshold, contact_window_days):
    """Check if a system should be removed from the group - used for parallel processing"""
    system_id = system.get("_id")
    hostname = system.get("hostname", "Unknown")
    display_name = system.get("displayName", "Unknown")
    os = system.get("os", "Unknown")
    last_contact = system.get("lastContact", "Never")

    # Check if it's a Mac
    if os != "Mac OS X":
        return (
            system,
            "non_mac",
            f"🚫 {hostname} ({display_name}): Not a Mac ({os}) - will remove",
        )

    # Check if hostname starts with MAC
    if not hostname.upper().startswith("MAC"):
        return (
            system,
            "bad_hostname",
            f"🚫 {hostname} ({display_name}): Bad hostname (doesn't start with MAC) - will remove",
        )

    # Check if stale
    if not has_contacted_recently(system, contact_window_days):
        return (
            system,
            "stale",
            f"⏸️  {hostname} ({display_name}): Stale (last: {last_contact}) - will remove",
        )

    # Apply rate limiting
    rate_limiter.wait()

    # Get current uptime
    uptime_days = get_system_uptime(system_id)

    if uptime_days is None:
        return (
            system,
            "keep",
            f"⚠️  {hostname} ({display_name}): No uptime data - will keep",
        )

    # Store for later
    system["uptime_days"] = uptime_days

    # Check if uptime is now low (system was rebooted)
    if uptime_days <= uptime_threshold:
        return (
            system,
            "low_uptime",
            f"✅ {hostname} ({display_name}): Rebooted ({uptime_days} days) - will remove",
        )

    # System should stay in group
    return (
        system,
        "keep",
        f"⭐ {hostname} ({display_name}): High uptime ({uptime_days} days) - already in group, matches criteria",
    )


def identify_systems_to_remove_from_group(
    all_systems, group_member_ids, uptime_threshold, contact_window_days=7
):
    """
    Identify systems in the group that should be removed using parallel processing:
    1. Non-Mac systems
    2. Macs without hostname starting with "MAC"
    3. Systems with low uptime (rebooted)
    4. Stale systems (not contacted recently)
    """
    systems_by_id = {s.get("_id"): s for s in all_systems}

    low_uptime_in_group = []
    stale_in_group = []
    non_mac_in_group = []
    bad_hostname_in_group = []

    print(color_text(f"\nChecking group members for systems to remove...", COLOR_INFO))
    print(color_text("-" * 80, COLOR_INFO))

    # Get systems that exist in the group
    group_systems = []
    for system_id in group_member_ids:
        system = systems_by_id.get(system_id)
        if system:
            group_systems.append(system)
        else:
            print(color_text(f"⚠️  System {system_id} in group but not found in system list", COLOR_WARNING))

    if not group_systems:
        print(color_text("No systems to check in group", COLOR_WARNING))
        return (
            low_uptime_in_group,
            stale_in_group,
            non_mac_in_group,
            bad_hostname_in_group,
        )

    # Use parallel processing for removal checks
    with ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_system = {
            executor.submit(
                check_system_for_removal, system, uptime_threshold, contact_window_days
            ): system
            for system in group_systems
        }

        # Process completed tasks as they finish
        for future in as_completed(future_to_system):
            system, result_type, message = future.result()
            print(color_text(f"  {message}", COLOR_INFO))

            if result_type == "low_uptime":
                low_uptime_in_group.append(system)
            elif result_type == "stale":
                stale_in_group.append(system)
            elif result_type == "non_mac":
                non_mac_in_group.append(system)
            elif result_type == "bad_hostname":
                bad_hostname_in_group.append(system)

    return low_uptime_in_group, stale_in_group, non_mac_in_group, bad_hostname_in_group


def add_single_system_to_group(system_id, group_id, already_in_group):
    """Add a single system to a device group - used for parallel processing"""
    if system_id in already_in_group:
        return system_id, "skipped", f"⭐️ Skipping {system_id} (already in group)"

    # Apply rate limiting
    rate_limiter.wait()

    url = f"{BASE_URL}/v2/systemgroups/{group_id}/members"
    payload = {"op": "add", "type": "system", "id": system_id}

    try:
        start_time = time.time()
        response = optimized_session.post(url, json=payload, timeout=30)
        response_time = time.time() - start_time

        if response.status_code in [200, 204]:
            rate_limiter.update_delay(response_time, False)
            return system_id, "success", f"✅ Added {system_id} to group"
        elif response.status_code == 409:
            rate_limiter.update_delay(response_time, False)
            return system_id, "skipped", f"⭐️ {system_id} already in group (409)"
        elif response.status_code == 429:
            rate_limiter.update_delay(response_time, True)
            # Rate limited - wait longer and retry once
            time.sleep(1)
            try:
                start_time = time.time()
                response = optimized_session.post(url, json=payload, timeout=30)
                response_time = time.time() - start_time

                if response.status_code in [200, 204]:
                    rate_limiter.update_delay(response_time, False)
                    return (
                        system_id,
                        "success",
                        f"✅ Added {system_id} to group (after retry)",
                    )
                else:
                    rate_limiter.update_delay(response_time, True)
                    return (
                        system_id,
                        "error",
                        f"❌ Failed to add {system_id} after retry: {response.status_code}",
                    )
            except Exception as retry_e:
                rate_limiter.update_delay(1.0, True)
                return (
                    system_id,
                    "error",
                    f"❌ Exception adding {system_id} after retry: {str(retry_e)}",
                )
        else:
            rate_limiter.update_delay(response_time, True)
            return (
                system_id,
                "error",
                f"❌ Failed to add {system_id}: {response.status_code} - {response.text}",
            )
    except requests.exceptions.Timeout:
        rate_limiter.update_delay(30.0, True)
        return system_id, "error", f"❌ Timeout adding {system_id}"
    except requests.exceptions.ConnectionError:
        rate_limiter.update_delay(5.0, True)
        return system_id, "error", f"❌ Connection error adding {system_id}"
    except Exception as e:
        rate_limiter.update_delay(1.0, True)
        return system_id, "error", f"❌ Exception adding {system_id}: {str(e)}"


def add_systems_to_group(system_ids, group_id, already_in_group, max_workers=None):
    """Add systems to a device group using parallel processing with batch optimization"""
    if not system_ids:
        return 0, 0

    if max_workers is None:
        max_workers = DEFAULT_MAX_WORKERS

    print(color_text(f"  Adding {len(system_ids)} systems using {max_workers} parallel workers...", COLOR_INFO))

    success_count = 0
    skipped_count = 0
    error_count = 0

    # Process in batches for better memory management
    for i in range(0, len(system_ids), BATCH_SIZE):
        batch = system_ids[i : i + BATCH_SIZE]
        print(
            color_text(
                f"  Processing batch {i // BATCH_SIZE + 1}/{(len(system_ids) + BATCH_SIZE - 1) // BATCH_SIZE} ({len(batch)} systems)...",
                COLOR_INFO
            )
        )

        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks for this batch
            future_to_system = {
                executor.submit(
                    add_single_system_to_group, system_id, group_id, already_in_group
                ): system_id
                for system_id in batch
            }

            # Process completed tasks as they finish
            for future in as_completed(future_to_system):
                system_id, result_type, message = future.result()

                if result_type == "success":
                    success_count += 1
                elif result_type == "skipped":
                    skipped_count += 1
                else:
                    error_count += 1

                print(f"  {message}")

    return success_count, skipped_count


def remove_single_system_from_group(system_id, group_id):
    """Remove a single system from a device group - used for parallel processing"""
    # Apply rate limiting
    rate_limiter.wait()

    url = f"{BASE_URL}/v2/systemgroups/{group_id}/members"
    payload = {"op": "remove", "type": "system", "id": system_id}

    try:
        start_time = time.time()
        response = optimized_session.post(url, json=payload, timeout=30)
        response_time = time.time() - start_time

        if response.status_code in [200, 204]:
            rate_limiter.update_delay(response_time, False)
            return system_id, "success", f"✅ Removed {system_id} from group"
        elif response.status_code == 404:
            rate_limiter.update_delay(response_time, False)
            return system_id, "success", f"⭐️ {system_id} not in group (404)"
        elif response.status_code == 429:
            rate_limiter.update_delay(response_time, True)
            # Rate limited - wait longer and retry once
            time.sleep(1)
            try:
                start_time = time.time()
                response = optimized_session.post(url, json=payload, timeout=30)
                response_time = time.time() - start_time

                if response.status_code in [200, 204]:
                    rate_limiter.update_delay(response_time, False)
                    return (
                        system_id,
                        "success",
                        f"✅ Removed {system_id} from group (after retry)",
                    )
                elif response.status_code == 404:
                    rate_limiter.update_delay(response_time, False)
                    return system_id, "success", f"⭐️ {system_id} not in group (404)"
                else:
                    rate_limiter.update_delay(response_time, True)
                    return (
                        system_id,
                        "error",
                        f"❌ Failed to remove {system_id} after retry: {response.status_code}",
                    )
            except Exception as retry_e:
                rate_limiter.update_delay(1.0, True)
                return (
                    system_id,
                    "error",
                    f"❌ Exception removing {system_id} after retry: {str(retry_e)}",
                )
        else:
            rate_limiter.update_delay(response_time, True)
            return (
                system_id,
                "error",
                f"❌ Failed to remove {system_id}: {response.status_code} - {response.text}",
            )
    except requests.exceptions.Timeout:
        rate_limiter.update_delay(30.0, True)
        return system_id, "error", f"❌ Timeout removing {system_id}"
    except requests.exceptions.ConnectionError:
        rate_limiter.update_delay(5.0, True)
        return system_id, "error", f"❌ Connection error removing {system_id}"
    except Exception as e:
        rate_limiter.update_delay(1.0, True)
        return system_id, "error", f"❌ Exception removing {system_id}: {str(e)}"


def remove_systems_from_group(system_ids, group_id, max_workers=None):
    """Remove systems from a device group using parallel processing with batch optimization"""
    if not system_ids:
        return 0

    if max_workers is None:
        max_workers = DEFAULT_MAX_WORKERS

    print(
        color_text(
            f"  Removing {len(system_ids)} systems using {max_workers} parallel workers...",
            COLOR_INFO
        )
    )

    success_count = 0
    error_count = 0

    # Process in batches for better memory management
    for i in range(0, len(system_ids), BATCH_SIZE):
        batch = system_ids[i : i + BATCH_SIZE]
        print(
            color_text(
                f"  Processing batch {i // BATCH_SIZE + 1}/{(len(system_ids) + BATCH_SIZE - 1) // BATCH_SIZE} ({len(batch)} systems)...",
                COLOR_INFO
            )
        )

        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks for this batch
            future_to_system = {
                executor.submit(
                    remove_single_system_from_group, system_id, group_id
                ): system_id
                for system_id in batch
            }

            # Process completed tasks as they finish
            for future in as_completed(future_to_system):
                system_id, result_type, message = future.result()

                if result_type == "success":
                    success_count += 1
                else:
                    error_count += 1

                print(color_text(f"  {message}", COLOR_INFO))

    return success_count


def main():
    """Main execution function"""
    # Start performance monitoring
    start_time = time.time()
    print(
        color_text(
            f"🚀 Starting with {DEFAULT_MAX_WORKERS} parallel workers and batch size {BATCH_SIZE}",
            COLOR_INFO
        )
    )

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

    # Generate suggested group name
    suggested_group_name = (
        f"Accolade Macs (MAC*) with uptime > {UPTIME_THRESHOLD_DAYS} days"
    )

    print(color_text("\n" + "=" * 60, COLOR_INFO))
    print(color_text(f"Target: Accolade Mac systems with hostname starting with MAC", COLOR_INFO))
    print(color_text(f"Criteria: uptime > {UPTIME_THRESHOLD_DAYS} days", COLOR_INFO))
    print(color_text(f"Filter: Only systems contacted in last {CONTACT_WINDOW_DAYS} days", COLOR_INFO))
    print(color_text("=" * 60, COLOR_INFO))

    # Ask if user wants to rename the group
    if current_group_name != suggested_group_name:
        print(color_text(f"\nCurrent group name: {current_group_name}", COLOR_INFO))
        print(color_text(f"Suggested group name: {suggested_group_name}", COLOR_INFO))
        rename_choice = input("Do you want to rename the group? (y/n): ")

        if rename_choice.lower() == "y":
            print(color_text(f"\nRenaming group...", COLOR_INFO))
            rename_group(target_group_id, suggested_group_name)
    else:
        print(color_text(f"\nGroup name is already correct: {current_group_name}", COLOR_SUCCESS))

    # Fetch all systems
    all_systems = get_all_systems()

    # Get current group members
    group_member_list = get_group_members(target_group_id)
    group_member_ids = set(group_member_list)

    # ADDITION LOGIC: Find systems with high uptime
    high_uptime, low_uptime, stale, no_data = categorize_systems_by_uptime(
        all_systems, UPTIME_THRESHOLD_DAYS, CONTACT_WINDOW_DAYS
    )

    # REMOVAL LOGIC: Find systems in group that should be removed
    low_uptime_in_group, stale_in_group, non_mac_in_group, bad_hostname_in_group = (
        identify_systems_to_remove_from_group(
            all_systems, group_member_ids, UPTIME_THRESHOLD_DAYS, CONTACT_WINDOW_DAYS
        )
    )

    # Determine what needs to be added and removed
    high_uptime_ids = {s["_id"] for s in high_uptime}
    low_uptime_ids_in_group = {s["_id"] for s in low_uptime_in_group}
    stale_ids_in_group = {s["_id"] for s in stale_in_group}
    non_mac_ids_in_group = {s["_id"] for s in non_mac_in_group}
    bad_hostname_ids_in_group = {s["_id"] for s in bad_hostname_in_group}

    to_add = high_uptime_ids - group_member_ids
    to_remove = (
        low_uptime_ids_in_group
        | stale_ids_in_group
        | non_mac_ids_in_group
        | bad_hostname_ids_in_group
    )

    print(color_text(f"\n📋 Actions needed:", COLOR_INFO))
    print(color_text(f"  Systems to ADD to group: {len(to_add)}", COLOR_INFO))
    print(color_text(f"  Systems to REMOVE from group: {len(to_remove)}", COLOR_INFO))
    if to_remove:
        print(color_text(f"    - Rebooted (low uptime): {len(low_uptime_ids_in_group)}", COLOR_INFO))
        print(color_text(f"    - Non-Mac systems: {len(non_mac_ids_in_group)}", COLOR_INFO))
        print(color_text(f"    - Bad hostname: {len(bad_hostname_ids_in_group)}", COLOR_INFO))
        print(color_text(f"    - Stale: {len(stale_ids_in_group)}", COLOR_INFO))

    if not to_add and not to_remove:
        print(color_text("\n✅ Group is already up to date! No changes needed.", COLOR_SUCCESS))
        return

    # Show details
    if to_add:
        print(color_text(f"\n➕ Systems to ADD (high uptime, contacted recently, not in group):", COLOR_INFO))
        for system in high_uptime:
            if system["_id"] in to_add:
                hostname = system.get("hostname", "Unknown")
                display_name = system.get("displayName", "Unknown")
                os = system.get("os", "Unknown")
                uptime_days = system.get("uptime_days", "Unknown")
                print(
                    color_text(
                        f"  - {hostname} ({display_name}) - {os} - {uptime_days} days uptime",
                        COLOR_INFO
                    )
                )

    if to_remove:
        print(color_text(f"\n➖ Systems to REMOVE:", COLOR_INFO))

        if low_uptime_in_group:
            print(color_text(f"\n  Rebooted ({len(low_uptime_in_group)}):", COLOR_INFO))
            for system in low_uptime_in_group:
                hostname = system.get("hostname", "Unknown")
                display_name = system.get("displayName", "Unknown")
                uptime_days = system.get("uptime_days", "Unknown")
                print(color_text(f"    - {hostname} ({display_name}) - {uptime_days} days", COLOR_INFO))

        if non_mac_in_group:
            print(color_text(f"\n  Non-Mac systems ({len(non_mac_in_group)}):", COLOR_INFO))
            for system in non_mac_in_group:
                hostname = system.get("hostname", "Unknown")
                display_name = system.get("displayName", "Unknown")
                os = system.get("os", "Unknown")
                print(color_text(f"    - {hostname} ({display_name}) - {os}", COLOR_INFO))

        if bad_hostname_in_group:
            print(
                color_text(
                    f"\n  Bad hostname - doesn't start with MAC ({len(bad_hostname_in_group)}):",
                    COLOR_INFO
                )
            )
            for system in bad_hostname_in_group:
                hostname = system.get("hostname", "Unknown")
                display_name = system.get("displayName", "Unknown")
                print(color_text(f"    - {hostname} ({display_name})", COLOR_INFO))

        if stale_in_group:
            print(
                color_text(
                    f"\n  Stale - no contact in {CONTACT_WINDOW_DAYS}+ days ({len(stale_in_group)}):",
                    COLOR_INFO
                )
            )
            for system in stale_in_group:
                hostname = system.get("hostname", "Unknown")
                display_name = system.get("displayName", "Unknown")
                last_contact = system.get("lastContact", "Unknown")
                print(color_text(f"    - {hostname} ({display_name}) - Last: {last_contact}", COLOR_INFO))

    # Perform additions
    added_count = 0
    skipped_count = 0
    if to_add:
        print(color_text("\n" + "=" * 60, COLOR_INFO))
        print(color_text(f"➕ Ready to ADD {len(to_add)} system(s) to group", COLOR_INFO))
        confirm_add = input("Add these systems? (y/n): ")

        if confirm_add.lower() == "y":
            print(color_text(f"\nAdding {len(to_add)} system(s) to group...", COLOR_INFO))
            added_count, skipped_count = add_systems_to_group(
                list(to_add),
                target_group_id,
                group_member_ids,
                max_workers=DEFAULT_MAX_WORKERS,
            )
            print(
                color_text(
                    f"✅ Successfully added {added_count}/{len(to_add)} systems (skipped {skipped_count})",
                    COLOR_SUCCESS
                )
            )
        else:
            print(color_text("Skipped adding systems", COLOR_WARNING))

    # Perform removals
    removed_count = 0
    if to_remove:
        print(color_text("\n" + "=" * 60, COLOR_INFO))
        print(color_text(f"➖ Ready to REMOVE {len(to_remove)} system(s) from group", COLOR_INFO))
        confirm_remove = input("Remove these systems? (y/n): ")

        if confirm_remove.lower() == "y":
            print(color_text(f"\nRemoving {len(to_remove)} system(s) from group...", COLOR_INFO))
            removed_count = remove_systems_from_group(
                list(to_remove), target_group_id, max_workers=DEFAULT_MAX_WORKERS
            )
            print(color_text(f"✅ Successfully removed {removed_count}/{len(to_remove)} systems", COLOR_SUCCESS))
        else:
            print(color_text("❌ Skipped removing systems", COLOR_WARNING))

    # Final summary
    end_time = time.time()
    total_time = end_time - start_time

    print(color_text("\n" + "=" * 60, COLOR_INFO))
    print(color_text("✅ Operation complete!", COLOR_SUCCESS))
    print(color_text(f"   Added: {added_count}", COLOR_INFO))
    print(color_text(f"   Skipped: {skipped_count}", COLOR_INFO))
    print(color_text(f"   Removed: {removed_count}", COLOR_INFO))
    print(color_text(f"   Total time: {total_time:.2f} seconds", COLOR_INFO))
    print(color_text(f"   Rate limiter delay: {rate_limiter.current_delay:.3f}s", COLOR_INFO))
    print(
        color_text(
            f"   Success rate: {rate_limiter.success_count}/{rate_limiter.success_count + rate_limiter.error_count}",
            COLOR_INFO
        )
    )
    print(color_text("=" * 60, COLOR_INFO))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(color_text("\n\nOperation cancelled by user", COLOR_WARNING))
        sys.exit(0)
    except Exception as e:
        print(color_text(f"\n❌ Unexpected error: {e}", COLOR_ERROR))
        import traceback

        traceback.print_exc()
        sys.exit(1)
