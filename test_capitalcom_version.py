#!/usr/bin/env python3
"""
Quick test to check capitalcom package version and Client class compatibility
"""
import sys
import subprocess

print("Checking capitalcom package...")

# Get exact version
result = subprocess.run([sys.executable, '-m', 'pip', 'show', 'capitalcom'], 
                      capture_output=True, text=True)
version = None
for line in result.stdout.split('\n'):
    if line.startswith('Version:'):
        version = line.split(':')[1].strip()
        print(f"✓ capitalcom version: {version}")
        break

if not version:
    print("✗ capitalcom package not installed")
    sys.exit(1)

# Test import patterns
print("\nTesting import patterns...")
try:
    from capitalcom import client, client_demo
    
    # Check what classes are available
    demo_client = getattr(client_demo, 'Client', None)
    demo_capital = getattr(client_demo, 'CapitalClient', None)
    live_client = getattr(client, 'Client', None) 
    live_capital = getattr(client, 'CapitalClient', None)
    
    print(f"  client_demo.Client: {'✓ Found' if demo_client else '✗ Not found'}")
    print(f"  client_demo.CapitalClient: {'✓ Found' if demo_capital else '✗ Not found'}")
    print(f"  client.Client: {'✓ Found' if live_client else '✗ Not found'}")
    print(f"  client.CapitalClient: {'✓ Found' if live_capital else '✗ Not found'}")
    
    # Test initialization signature
    ClientClass = demo_client or demo_capital
    if ClientClass:
        print(f"\nTesting {ClientClass.__name__} initialization...")
        
        # Try different patterns
        tests = [
            ("No params", lambda: ClientClass()),
            ("With log_level", lambda: ClientClass(log_level='ERROR')),
            ("With credentials", lambda: ClientClass("dummy_key", "dummy_pass")),
        ]
        
        for desc, test_func in tests:
            try:
                instance = test_func()
                print(f"  ✓ {desc}: SUCCESS")
                del instance
            except TypeError as e:
                print(f"  ✗ {desc}: {str(e)}")
            except Exception as e:
                print(f"  ✓ {desc}: Initialized (error expected: {e})")
    
    print("\n" + "="*60)
    print("COMPATIBILITY CHECK:")
    print("="*60)
    
    if version == "1.0.4":
        print("✓ You have the CORRECT version (1.0.4) that works on your laptop")
    else:
        print(f"✗ You have version {version}, but working laptop has 1.0.4")
        print("  Run fix_deployment.bat to install the correct version")
        
except ImportError as e:
    print(f"✗ Cannot import capitalcom: {e}")
