#!/usr/bin/env python3
"""
Quick test script to verify proxy connection.
Run with: python test_proxy_direct.py
"""

import requests
import os
import sys

# Proxy configuration
PROXY_HOST = 'eu.proxy-jet.io'
PROXY_PORT = '1010'
PROXY_USERNAME = '250724Wn6DD-resi_region-UK_England'
PROXY_PASSWORD = os.environ.get('PROXY_PASSWORD', '')

if not PROXY_PASSWORD:
    print(" Error: PROXY_PASSWORD environment variable not set")
    print("Run: export PROXY_PASSWORD='your-password'")
    sys.exit(1)

print(f"✅ Proxy password loaded (length: {len(PROXY_PASSWORD)})")

# Build proxy URL
proxy_url = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}"
proxies = {
    'http': proxy_url,
    'https': proxy_url
}

print(f"\nProxy configuration:")
print(f"  Host: {PROXY_HOST}")
print(f"  Port: {PROXY_PORT}")
print(f"  Username: {PROXY_USERNAME}")
print(f"  Password: {'*' * len(PROXY_PASSWORD)}")
print(f"\nTesting proxy connection...")

test_url = "http://httpbin.org/ip"
print(f"\nAttempt 1: Fetching {test_url}")

try:
    response = requests.get(
        test_url,
        proxies=proxies,
        timeout=10
    )
    print(f"✅ Success! Status code: {response.status_code}")
    print(f"Response: {response.text}")
    print(f"\nYour IP through proxy: {response.json().get('origin', 'unknown')}")
    
except requests.exceptions.ProxyError as e:
    print(f" Proxy Error: {e}")
    print("\nThis usually means:")
    print("  1. Proxy credentials are incorrect")
    print("  2. Proxy server is not accessible")
    print("  3. Proxy server rejected the connection")
    
except requests.exceptions.Timeout as e:
    print(f" Timeout Error: {e}")
    print("\nThis usually means:")
    print("  1. Proxy server is not responding")
    print("  2. Network connection is slow")
    print("  3. Proxy server is down")
    
except Exception as e:
    print(f" Error: {type(e).__name__}: {e}")

print("\n" + "="*60)
print("Attempt 2: Testing HTTPS through proxy")
print("="*60)

test_url_https = "https://httpbin.org/ip"
print(f"\nFetching {test_url_https}")

try:
    response = requests.get(
        test_url_https,
        proxies=proxies,
        timeout=10,
        verify=True
    )
    print(f"✅ Success! Status code: {response.status_code}")
    print(f"Response: {response.text}")
    
except Exception as e:
    print(f" Error: {type(e).__name__}: {e}")
