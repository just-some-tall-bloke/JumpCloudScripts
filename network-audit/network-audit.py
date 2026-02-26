#!/usr/bin/env python3
# Licensed under CC BY-NC-SA 4.0
# https://creativecommons.org/licenses/by-nc-sa/4.0/

"""
Network Configuration Audit Script
Detects unusual network setups and reports on DNS, proxies, and VPN configurations
"""

import os
import sys
import requests
import csv
from datetime import datetime
from typing import List, Dict, Optional, Any

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False
    # Fallback to manual ANSI codes if colorama is not available
    class _ColorFallback:
        def __init__(self):
            self.RED = '\033[91m'
            self.GREEN = '\033[92m'
            self.YELLOW = '\033[93m'
            self.BLUE = '\033[94m'
            self.MAGENTA = '\033[95m'
            self.CYAN = '\033[96m'
            self.WHITE = '\033[97m'
            self.RESET = '\033[0m'
    class _StyleFallback:
        def __init__(self):
            self.BRIGHT = '\033[1m'
            self.DIM = '\033[2m'
            self.NORMAL = '\033[22m'
            self.RESET_ALL = '\033[0m'
    Fore = _ColorFallback()
    Style = _StyleFallback()

# Color constants
COLOR_SUCCESS = Fore.GREEN + Style.BRIGHT if HAS_COLOR else Fore.GREEN
COLOR_ERROR = Fore.RED + Style.BRIGHT if HAS_COLOR else Fore.RED
COLOR_WARNING = Fore.YELLOW + Style.BRIGHT if HAS_COLOR else Fore.YELLOW
COLOR_INFO = Fore.CYAN + Style.BRIGHT if HAS_COLOR else Fore.CYAN
COLOR_RESET = Style.RESET_ALL if HAS_COLOR else Style.RESET_ALL

def color_text(text, color):
    """Apply color to text if color support is available."""
    return f"{color}{text}{COLOR_RESET if HAS_COLOR else Style.RESET_ALL}"


def get_api_key() -> str:
    """Get API key from environment variable"""
    api_key = os.getenv('JUMPCLOUD_API_KEY')
    if not api_key:
        print(color_text("Error: JUMPCLOUD_API_KEY environment variable is not set", COLOR_ERROR))
        print(color_text("Please set it using: export JUMPCLOUD_API_KEY='your_api_key'", COLOR_INFO))
        sys.exit(1)
    return api_key


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


def get_system_insights(api_key: str, system_id: str) -> Dict[str, Any]:
    """Get system insights data for network configuration"""
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    
    uri = f"https://console.jumpcloud.com/api/systems/{system_id}/insights"
    
    try:
        response = requests.get(uri, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(color_text(f"Warning: Could not fetch insights for system {system_id}: {e}", COLOR_WARNING))
        return {}


def extract_network_info(insights: Dict[str, Any]) -> Dict[str, Any]:
    """Extract network configuration information from system insights"""
    network_info = {
        'dns_servers': [],
        'proxy_enabled': False,
        'proxy_config': '',
        'vpn_connections': [],
        'network_interfaces': []
    }
    
    # Extract DNS servers from network preferences
    if 'networkInterfaces' in insights:
        for iface in insights.get('networkInterfaces', []):
            network_info['network_interfaces'].append({
                'name': iface.get('name', ''),
                'type': iface.get('type', ''),
                'ip_address': iface.get('ipAddress', ''),
                'status': iface.get('status', 'unknown')
            })
            
            # Collect DNS servers
            if 'dnsServers' in iface:
                network_info['dns_servers'].extend(iface.get('dnsServers', []))
    
    # Check for proxy configuration
    if 'proxySettings' in insights:
        proxy_settings = insights.get('proxySettings', {})
        if proxy_settings:
            network_info['proxy_enabled'] = True
            network_info['proxy_config'] = str(proxy_settings)
    
    # Extract VPN connections
    if 'vpnConnections' in insights:
        network_info['vpn_connections'] = insights.get('vpnConnections', [])
    
    # Deduplicate DNS servers
    network_info['dns_servers'] = list(set(network_info['dns_servers']))
    
    return network_info


def is_custom_dns(dns_servers: List[str]) -> bool:
    """Check if DNS servers are non-standard (custom configuration)"""
    standard_dns = {'8.8.8.8', '8.8.4.4', '1.1.1.1', '1.0.0.1', '208.67.222.222', '208.67.220.220'}
    
    for dns in dns_servers:
        if dns and dns not in standard_dns:
            return True
    
    return False


def analyze_network_config(system: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    """Analyze network configuration for a system"""
    system_id = system.get('_id', '')
    hostname = system.get('hostname', 'Unknown')
    
    insights = get_system_insights(api_key, system_id)
    network_info = extract_network_info(insights)
    
    issues = []
    
    # Check for custom DNS
    if network_info['dns_servers']:
        if is_custom_dns(network_info['dns_servers']):
            issues.append(f"Custom DNS configured: {', '.join(network_info['dns_servers'])}")
    
    # Check for proxy
    if network_info['proxy_enabled']:
        issues.append(f"Proxy enabled: {network_info['proxy_config']}")
    
    # Check for VPN connections
    if network_info['vpn_connections']:
        vpn_names = [vpn.get('name', 'Unknown') for vpn in network_info['vpn_connections']]
        issues.append(f"VPN connections: {', '.join(vpn_names)}")
    
    return {
        'hostname': hostname,
        'system_id': system_id,
        'dns_servers': ', '.join(network_info['dns_servers']) if network_info['dns_servers'] else 'Standard',
        'proxy_enabled': 'Yes' if network_info['proxy_enabled'] else 'No',
        'vpn_connections': ', '.join([v.get('name', 'Unknown') for v in network_info['vpn_connections']]) if network_info['vpn_connections'] else 'None',
        'network_interfaces': len(network_info['network_interfaces']),
        'issues': '; '.join(issues) if issues else 'None'
    }


def main():
    """Main function"""
    # Get API key
    api_key = get_api_key()
    
    print(color_text("🔍 Network Configuration Audit", COLOR_INFO))
    print(color_text("=" * 80, COLOR_INFO))
    print(color_text("\nFetching all systems from JumpCloud...", COLOR_INFO))
    
    systems = get_all_systems(api_key)
    
    if not systems:
        print(color_text("No systems found or error occurred", COLOR_ERROR))
        sys.exit(1)
    
    print(color_text(f"Found {len(systems)} total systems", COLOR_SUCCESS))
    
    # Filter for Mac systems only
    mac_systems = [s for s in systems if s.get('os') == 'Mac OS X']
    print(color_text(f"Analyzing {len(mac_systems)} macOS systems...\n", COLOR_INFO))
    
    # Analyze each Mac system
    audit_results = []
    systems_with_issues = []
    
    for idx, system in enumerate(mac_systems, 1):
        hostname = system.get('hostname', 'Unknown')
        print(f"\rAnalyzing ({idx}/{len(mac_systems)}) {hostname[:40]:<40}", end='', flush=True)
        
        result = analyze_network_config(system, api_key)
        audit_results.append(result)
        
        if result['issues'] != 'None':
            systems_with_issues.append(result)
    
    print()  # New line after progress
    
    # Generate output filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f"network_audit_results_{timestamp}.csv"
    
    # Export to CSV
    if audit_results:
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = audit_results[0].keys()
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(audit_results)
        
        print(color_text("\n✅ Network Configuration Audit Complete!", COLOR_SUCCESS))
        print(color_text(f"Results saved to: {output_file}", COLOR_SUCCESS))
        print(color_text(f"\nScanned {len(mac_systems)} macOS systems", COLOR_INFO))
        
        # Summary table header
        print(color_text("\n" + "=" * 100, COLOR_INFO))
        print(color_text("SYSTEMS WITH UNUSUAL NETWORK CONFIGURATION", COLOR_WARNING))
        print(color_text("=" * 100, COLOR_INFO))
        
        if systems_with_issues:
            print(f"{'HOSTNAME':<30} {'DNS SERVERS':<25} {'PROXY':<10} {'VPN':<15} {'ISSUES':<20}")
            print("-" * 100)
            
            for result in systems_with_issues:
                hostname = result['hostname'][:30]
                dns = result['dns_servers'][:25]
                proxy = result['proxy_enabled'][:10]
                vpn = result['vpn_connections'][:15]
                issues = result['issues'][:20]
                
                print(f"{hostname:<30} {dns:<25} {proxy:<10} {vpn:<15} {issues:<20}")
        else:
            print(color_text("✅ No unusual network configurations detected!", COLOR_SUCCESS))
        
        print(color_text("=" * 100, COLOR_INFO))
        print(color_text(f"\nSummary: {len(systems_with_issues)} systems with unusual network configuration out of {len(mac_systems)} scanned", COLOR_INFO))
    else:
        print(color_text("No results to export", COLOR_ERROR))
    
    print(color_text("\nScript completed!", COLOR_SUCCESS))


if __name__ == "__main__":
    main()
