#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flexible hardware lock system - Auto-registers any device automatically
"""

import hashlib
import socket
import uuid
import json
import os
from datetime import datetime
from typing import Dict, Optional, Tuple

try:
    import netifaces
    NETIFACES_AVAILABLE = True
except ImportError:
    NETIFACES_AVAILABLE = False


class HardwareLock:
    """
    Hardware identification system with AUTO-REGISTRATION.
    - Automatically reads MAC and IP from current device
    - Creates license file automatically for ANY device
    - No need to manually enter MAC or IP
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.enforce_lock = self.config.get('enforce_lock', False)
        self.master_key_hash = self.config.get('emergency_master_key_hash', '')
        
        self.current_mac = self._get_mac_address()
        self.current_ip = self._get_ip_address()
        self.current_hostname = socket.gethostname()
        
        self.is_authorized = False
        self.license_data = None
        
        # Try to load existing license
        self._load_license()
        
    def _get_mac_address(self) -> str:
        """Extract real MAC address of the machine"""
        try:
            # Method 1: Using uuid.getnode()
            mac_int = uuid.getnode()
            mac_hex = ':'.join(['{:02x}'.format((mac_int >> ele) & 0xff) 
                                for ele in range(0, 8*6, 8)][::-1])
            
            if mac_hex and mac_hex != '00:00:00:00:00:00':
                return mac_hex.upper()
            
            # Method 2: Using netifaces
            if NETIFACES_AVAILABLE:
                interfaces = netifaces.interfaces()
                for iface in interfaces:
                    if iface.startswith(('eth', 'enp', 'ens', 'wlan', 'wlp', 'lo')):
                        addrs = netifaces.ifaddresses(iface)
                        if netifaces.AF_LINK in addrs:
                            mac = addrs[netifaces.AF_LINK][0].get('addr', '')
                            if mac and mac != '00:00:00:00:00:00':
                                return mac.upper()
            
            # Method 3: Windows-specific
            if os.name == 'nt':
                import subprocess
                result = subprocess.run(['getmac', '/fo', 'csv', '/nh'], 
                                    capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if lines:
                        mac = lines[0].split(',')[0].strip('"')
                        if mac and mac != '00:00:00:00:00:00':
                            return mac.upper()
            
            return mac_hex.upper() if mac_hex else "00:00:00:00:00:00"
            
        except Exception:
            return "00:00:00:00:00:00"
    
    def _get_ip_address(self) -> str:
        """Get primary IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            try:
                hostname = socket.gethostname()
                ip = socket.gethostbyname(hostname)
                return ip if ip and not ip.startswith('127.') else "0.0.0.0"
            except Exception:
                return "0.0.0.0"
    
    def _generate_fingerprint(self) -> str:
        """Generate unique hardware fingerprint"""
        fingerprint_data = f"{self.current_mac}|{self.current_hostname}"
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()
    
    def _load_license(self):
        """Load license file if exists"""
        license_paths = ["license.txt", "omega_license.json"]
        
        for path in license_paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        self.license_data = json.load(f)
                    
                    # Verify against current hardware
                    if self.license_data.get('mac_address') == self.current_mac:
                        self.is_authorized = True
                    else:
                        self.is_authorized = False
                    return
                except Exception:
                    pass
        
        self.is_authorized = False
    
    def register_current_machine(self, output_file: str = "license.txt") -> Dict:
        """Register current machine as authorized"""
        license_data = {
            'mac_address': self.current_mac,
            'ip_address': self.current_ip,
            'hostname': self.current_hostname,
            'fingerprint': self._generate_fingerprint(),
            'timestamp': datetime.now().isoformat(),
            'version': 2
        }
        
        with open(output_file, 'w') as f:
            json.dump(license_data, f, indent=4)
        
        self.license_data = license_data
        self.is_authorized = True
        
        return license_data
    
    def verify(self) -> Tuple[bool, str]:
        """Verify hardware authorization"""
        if self.is_authorized:
            return True, f"✅ Authorized - MAC: {self.current_mac}"
        
        if self.license_data:
            return False, f"⚠️ MAC mismatch! License: {self.license_data.get('mac_address')}, Current: {self.current_mac}"
        
        return False, f"⚠️ No license found. Run registration to authorize this machine.\n   Current MAC: {self.current_mac}"
    
    def emergency_unlock(self, master_key: str) -> bool:
        """Emergency unlock with master key"""
        if not self.master_key_hash:
            return False
        
        if hashlib.sha256(master_key.encode()).hexdigest() == self.master_key_hash:
            self.is_authorized = True
            return True
        
        return False
    
    def get_status(self) -> Dict:
        """Get current hardware status"""
        return {
            'mac_address': self.current_mac,
            'ip_address': self.current_ip,
            'hostname': self.current_hostname,
            'fingerprint': self._generate_fingerprint(),
            'is_authorized': self.is_authorized,
            'license_exists': self.license_data is not None
        }
    
    # ========== NEW AUTO-REGISTRATION METHODS ==========
    
    def auto_register_current_device(self, license_file: str = "license.txt") -> Dict:
        """
        Automatically registers the current device without needing any input.
        Reads real MAC and IP and saves them to license file.
        
        Args:
            license_file: Name of license file
        
        Returns:
            Dict: License data
        """
        # Refresh current MAC and IP
        self.current_mac = self._get_mac_address()
        self.current_ip = self._get_ip_address()
        self.current_hostname = socket.gethostname()
        
        # Create license data
        license_data = {
            'mac_address': self.current_mac,
            'ip_address': self.current_ip,
            'hostname': self.current_hostname,
            'fingerprint': self._generate_fingerprint(),
            'timestamp': datetime.now().isoformat(),
            'authorized': True,
            'device_id': str(uuid.uuid4())
        }
        
        # Save file
        with open(license_file, 'w') as f:
            json.dump(license_data, f, indent=4)
        
        self.license_data = license_data
        self.is_authorized = True
        
        print(f"\n✅ Device automatically registered!")
        print(f"   File: {license_file}")
        print(f"   Device: {self.current_hostname}")
        print(f"   MAC: {self.current_mac}")
        print(f"   IP: {self.current_ip}")
        
        return license_data
    
    def verify_current_device_against_license(self, license_file: str = "license.txt") -> tuple:
        """
        Checks if current device matches the license file
        
        Returns:
            (is_match, message, license_data)
        """
        if not os.path.exists(license_file):
            return (False, "❌ License file not found", None)
        
        try:
            with open(license_file, 'r') as f:
                license_data = json.load(f)
            
            saved_mac = license_data.get('mac_address', '')
            saved_ip = license_data.get('ip_address', '')
            
            # Refresh current MAC and IP
            self.current_mac = self._get_mac_address()
            self.current_ip = self._get_ip_address()
            
            if saved_mac == self.current_mac and saved_ip == self.current_ip:
                self.is_authorized = True
                self.license_data = license_data
                return (True, "✅ YES - Same registered device", license_data)
            else:
                return (False, f"❌ NO - Different device! (Registered: {saved_mac}, Current: {self.current_mac})", license_data)
                
        except Exception as e:
            return (False, f"❌ Error: {e}", None)
    
    def check_mac_ip_binding(self, expected_mac: str, expected_ip: str) -> bool:
        """
        Checks if current MAC and IP match expected values
        
        Args:
            expected_mac: Expected MAC address
            expected_ip: Expected IP address
        
        Returns:
            bool: True if match, False otherwise
        """
        expected_mac_clean = expected_mac.strip().upper()
        expected_ip_clean = expected_ip.strip()
        
        mac_matches = (self.current_mac == expected_mac_clean)
        ip_matches = (self.current_ip == expected_ip_clean)
        
        print("\n" + "="*50)
        print("🔍 MAC & IP BINDING CHECK:")
        print(f"   Expected MAC: {expected_mac_clean}")
        print(f"   Current MAC:  {self.current_mac}")
        print(f"   Expected IP:  {expected_ip_clean}")
        print(f"   Current IP:   {self.current_ip}")
        print("-"*50)
        
        if mac_matches and ip_matches:
            print(f"✅ RESULT: YES - Device is authorized")
            print("="*50 + "\n")
            return True
        else:
            print(f"❌ RESULT: NO - Device is NOT authorized")
            if not mac_matches:
                print(f"   → MAC mismatch")
            if not ip_matches:
                print(f"   → IP mismatch")
            print("="*50 + "\n")
            return False
    
    def quick_binding_check(self, expected_mac: str, expected_ip: str) -> str:
        """
        Simple function that returns "YES" or "NO" only
        
        Args:
            expected_mac: Expected MAC address
            expected_ip: Expected IP address
        
        Returns:
            str: "YES" or "NO"
        """
        expected_mac_clean = expected_mac.strip().upper()
        expected_ip_clean = expected_ip.strip()
        
        if self.current_mac == expected_mac_clean and self.current_ip == expected_ip_clean:
            return "YES"
        else:
            return "NO"
    
    def smart_license_check(self, license_file: str = "license.txt") -> bool:
        """
        SMART LICENSE CHECK - Fully automatic!
        - If license exists and matches current device → YES
        - If license exists but for different device → deletes old, registers new
        - If no license → registers current device automatically
        
        Returns:
            bool: True if license is OK, False on error
        """
        print("\n" + "="*60)
        print("🔐 OMEGA ENGINE - Smart License System")
        print("="*60)
        
        # Refresh current device info
        self.current_mac = self._get_mac_address()
        self.current_ip = self._get_ip_address()
        self.current_hostname = socket.gethostname()
        
        print(f"💻 Current Device Info:")
        print(f"   Hostname: {self.current_hostname}")
        print(f"   MAC:      {self.current_mac}")
        print(f"   IP:       {self.current_ip}")
        print("-"*40)
        
        if os.path.exists(license_file):
            # License file exists
            try:
                with open(license_file, 'r') as f:
                    old_license = json.load(f)
                
                saved_mac = old_license.get('mac_address', '')
                saved_ip = old_license.get('ip_address', '')
                
                if saved_mac == self.current_mac and saved_ip == self.current_ip:
                    # Same device
                    print(f"✅ License file exists and is valid for this device")
                    print(f"   Registration date: {old_license.get('timestamp', 'unknown')}")
                    self.is_authorized = True
                    self.license_data = old_license
                    print("="*60)
                    return True
                else:
                    # Different device - delete old and register new
                    print(f"⚠️ License file exists for a DIFFERENT device:")
                    print(f"   Registered MAC: {saved_mac}")
                    print(f"   Registered IP:  {saved_ip}")
                    print(f"🔄 Deleting old license and registering current device...")
                    os.remove(license_file)
                    print(f"🗑️ Old license deleted")
                    
                    # Register current device
                    self.auto_register_current_device(license_file)
                    print("="*60)
                    return True
                    
            except Exception as e:
                print(f"⚠️ Error reading license file: {e}")
                print(f"🔄 Creating new license file...")
                self.auto_register_current_device(license_file)
                print("="*60)
                return True
        else:
            # No license file - register this device
            print(f"📄 No license file found")
            print(f"🔄 Registering this device automatically...")
            self.auto_register_current_device(license_file)
            print("="*60)
            return True
