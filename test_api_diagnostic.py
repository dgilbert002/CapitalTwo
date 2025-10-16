#!/usr/bin/env python3
"""
Diagnostic script to test Capital.com API connection and identify issues.
Run this on both working and non-working servers to compare.
"""

import sys
import os
import platform
import socket
import ssl
import importlib
from datetime import datetime
import urllib.request

print("=" * 80)
print("CAPITAL.COM API DIAGNOSTIC TOOL")
print("=" * 80)

# 1. System Information
print("\n1. SYSTEM INFORMATION:")
print(f"   Python Version: {sys.version}")
print(f"   Platform: {platform.platform()}")
print(f"   Hostname: {socket.gethostname()}")
print(f"   Current Time UTC: {datetime.utcnow()}")
print(f"   Current Time Local: {datetime.now()}")

# 2. Package Versions
print("\n2. PACKAGE VERSIONS:")
packages = ['capitalcom', 'capitalcom-python', 'requests', 'urllib3', 'certifi']
for pkg in packages:
    try:
        mod = importlib.import_module(pkg.replace('-', '_'))
        version = getattr(mod, '__version__', 'Unknown')
        # For capitalcom, try to get version from pip if __version__ not available
        if version == 'Unknown' and pkg == 'capitalcom':
            try:
                import subprocess
                result = subprocess.run([sys.executable, '-m', 'pip', 'show', 'capitalcom'], 
                                      capture_output=True, text=True)
                for line in result.stdout.split('\n'):
                    if line.startswith('Version:'):
                        version = line.split(':')[1].strip()
                        break
            except:
                pass
        print(f"   {pkg}: {version} (installed)")
    except ImportError:
        print(f"   {pkg}: NOT INSTALLED")

# 3. Network Connectivity
print("\n3. NETWORK CONNECTIVITY:")
hosts = [
    ('demo-api-capital.backend-capital.com', 443),
    ('api-capital.backend-capital.com', 443),
    ('google.com', 443)
]
for host, port in hosts:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            print(f"   ✓ {host}:{port} - REACHABLE")
        else:
            print(f"   ✗ {host}:{port} - UNREACHABLE (error code: {result})")
    except Exception as e:
        print(f"   ✗ {host}:{port} - ERROR: {e}")

# 4. SSL Certificate Check
print("\n4. SSL CERTIFICATE CHECK:")
for host, _ in hosts[:2]:  # Only check Capital.com hosts
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                print(f"   ✓ {host} - SSL OK (expires: {cert.get('notAfter', 'Unknown')})")
    except Exception as e:
        print(f"   ✗ {host} - SSL ERROR: {e}")

# 5. Capital.com SDK Import Test
print("\n5. CAPITAL.COM SDK IMPORT TEST:")
try:
    # Try different import patterns
    imports_to_test = [
        ("capitalcom.client", "Client"),
        ("capitalcom.client", "CapitalClient"),
        ("capitalcom.client_demo", "Client"),
        ("capitalcom.client_demo", "CapitalClient"),
        ("capitalcom_python", None),
    ]
    
    for module_name, class_name in imports_to_test:
        try:
            mod = importlib.import_module(module_name)
            if class_name:
                cls = getattr(mod, class_name, None)
                if cls:
                    print(f"   ✓ Found {module_name}.{class_name}")
                else:
                    print(f"   ✗ {module_name}.{class_name} - NOT FOUND")
            else:
                print(f"   ✓ Module {module_name} imported successfully")
        except ImportError as e:
            print(f"   ✗ Cannot import {module_name}: {e}")
except Exception as e:
    print(f"   ✗ SDK import test failed: {e}")

# 6. Test API Connection (if settings.txt exists)
print("\n6. API CONNECTION TEST:")
if os.path.exists('settings.txt'):
    try:
        import configparser
        config = configparser.ConfigParser()
        config.read('settings.txt')
        
        api_key = config.get('CREDENTIALS', 'api_key', fallback='')
        password = config.get('CREDENTIALS', 'password', fallback='')
        environment = config.get('API_CONFIG', 'environment', fallback='demo')
        
        if api_key and password:
            print(f"   Settings loaded - Environment: {environment}")
            print(f"   API Key: {api_key[:4]}...{api_key[-4:]} (masked)")
            
            # Try to authenticate
            try:
                if environment == 'demo':
                    from capitalcom import client_demo
                    ClientClass = getattr(client_demo, 'Client', None) or getattr(client_demo, 'CapitalClient', None)
                else:
                    from capitalcom import client
                    ClientClass = getattr(client, 'Client', None) or getattr(client, 'CapitalClient', None)
                
                if ClientClass:
                    print(f"   Using client class: {ClientClass.__name__}")
                    
                    # Try different initialization patterns based on package version
                    try:
                        # Try newer version with log_level
                        client_instance = ClientClass(log_level='ERROR')
                        print("   Using newer API (with log_level)")
                    except TypeError:
                        try:
                            # Try older version without any params
                            client_instance = ClientClass()
                            print("   Using older API (no params)")
                        except TypeError:
                            # Try with api_key and password directly
                            client_instance = ClientClass(api_key, password)
                            print("   Using legacy API (credentials in constructor)")
                    
                    # Test login
                    import asyncio
                    async def test_login():
                        try:
                            # Try different login patterns
                            try:
                                # Try named parameters
                                await client_instance.login(api_key=api_key, password=password)
                            except TypeError:
                                # Try positional parameters
                                await client_instance.login(api_key, password)
                            
                            print("   ✓ LOGIN SUCCESSFUL!")
                            
                            # Try to get accounts
                            accounts = await client_instance.get_accounts()
                            print(f"   ✓ Accounts fetched: {len(accounts)} account(s)")
                            for acc in accounts:
                                print(f"      - {acc.get('accountId')}: {acc.get('accountName')}")
                            
                            await client_instance.logout()
                            return True
                        except Exception as e:
                            print(f"   ✗ LOGIN FAILED: {e}")
                            import traceback
                            traceback.print_exc()
                            return False
                    
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    success = loop.run_until_complete(test_login())
                    loop.close()
                else:
                    print("   ✗ Could not find Client or CapitalClient class")
            except Exception as e:
                print(f"   ✗ API test failed: {e}")
        else:
            print("   ✗ API credentials not found in settings.txt")
    except Exception as e:
        print(f"   ✗ Could not read settings.txt: {e}")
else:
    print("   ✗ settings.txt not found")

# 7. Environment Variables
print("\n7. RELEVANT ENVIRONMENT VARIABLES:")
env_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE', 'SSL_CERT_FILE']
for var in env_vars:
    value = os.environ.get(var)
    if value:
        print(f"   {var}: {value}")
    else:
        print(f"   {var}: Not set")

print("\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)
print("\nRun this script on both working and non-working servers and compare the output.")
print("Common issues:")
print("  - Package version mismatch (capitalcom or capitalcom-python)")
print("  - Network/firewall blocking Capital.com API")
print("  - SSL certificate validation issues")
print("  - System time out of sync")
print("  - Proxy settings interfering")
