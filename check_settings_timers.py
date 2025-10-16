#!/usr/bin/env python3
"""
Check settings.txt for empty or invalid timer values
"""
import configparser
import os

if not os.path.exists('settings.txt'):
    print("ERROR: settings.txt not found!")
    exit(1)

config = configparser.ConfigParser()
config.read('settings.txt')

print("Checking TIMERS section in settings.txt...")
print("=" * 60)

if not config.has_section('TIMERS'):
    print("ERROR: No [TIMERS] section found!")
    exit(1)

# Expected timer settings
expected_timers = [
    ('keepalive_minutes', 8),
    ('auth_retry_wait_sec', 30),
    ('auth_max_retry_wait_sec', 60),
    ('error_retry_wait_sec', 5),
    ('websocket_update_sec', 5),
    ('positions_update_market_open_sec', 5),
    ('positions_update_market_closed_sec', 10),
    ('accounts_update_market_open_sec', 5),
    ('accounts_update_market_closed_sec', 10),
    ('market_info_update_sec', 30),
    ('near_close_threshold_sec', 150),
    ('near_close_check_sec', 1),
    ('near_close_data_threshold_sec', 300),
    ('near_close_data_update_sec', 5),
    ('normal_loop_sec', 1),
    ('alpha_vantage_cache_sec', 300),
]

# Check each timer
issues = []
for key, default in expected_timers:
    if config.has_option('TIMERS', key):
        value = config.get('TIMERS', key)
        if value == '' or value is None:
            issues.append(f"  ✗ {key} = EMPTY (should be {default})")
            print(f"  ✗ {key} = EMPTY (should be {default})")
        else:
            try:
                if '.' in str(default):
                    float(value)
                else:
                    int(value)
                print(f"  ✓ {key} = {value}")
            except ValueError:
                issues.append(f"  ✗ {key} = '{value}' (invalid, should be {default})")
                print(f"  ✗ {key} = '{value}' (invalid, should be {default})")
    else:
        issues.append(f"  ✗ {key} = MISSING (should be {default})")
        print(f"  ✗ {key} = MISSING (should be {default})")

# Check BOT_CONFIG timers
print("\nChecking BOT_CONFIG section timers...")
bot_timers = [
    ('seconds_before_close_to_exit', 30),
    ('seconds_before_close_to_trade', 15),
]

for key, default in bot_timers:
    if config.has_option('BOT_CONFIG', key):
        value = config.get('BOT_CONFIG', key)
        if value == '' or value is None:
            issues.append(f"  ✗ {key} = EMPTY (should be {default})")
            print(f"  ✗ {key} = EMPTY (should be {default})")
        else:
            try:
                int(value)
                print(f"  ✓ {key} = {value}")
            except ValueError:
                issues.append(f"  ✗ {key} = '{value}' (invalid, should be {default})")
                print(f"  ✗ {key} = '{value}' (invalid, should be {default})")
    else:
        issues.append(f"  ✗ {key} = MISSING (should be {default})")
        print(f"  ✗ {key} = MISSING (should be {default})")

print("\n" + "=" * 60)
if issues:
    print(f"FOUND {len(issues)} ISSUES:")
    for issue in issues:
        print(issue)
    print("\nTo fix, add these values to settings.txt")
else:
    print("✓ All timer settings are valid!")
