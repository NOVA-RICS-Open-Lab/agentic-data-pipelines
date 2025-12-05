import requests

base = "http://localhost:5001"

# Test ALL possible V2 endpoint patterns
tests = [
    # Try with index
    "/aas/0/submodels",
    "/aas/id/0/submodels", 
    
    # Try with idShort variations
    "/aas/CarASS/core/submodels",
    "/aas/id/CarASS/submodels",
    
    # Try with full encoded ID
    "/aas/aHR0cHM6Ly9leGFtcGxlLmNvbS9pZHMvc20vNTE4NV8zMTQwXzIxNTJfOTI5MQ/submodels",
    
    # Try without /aas prefix
    "/submodels",
    
    # Try API prefix
    "/api/v2/aas/CarASS/submodels",
]

for endpoint in tests:
    url = base + endpoint
    try:
        resp = requests.get(url, timeout=2)
        ct = resp.headers.get('content-type', '')
        if resp.status_code == 200 and 'json' in ct:
            print(f"✓✓✓ SUCCESS: {endpoint}")
            print(f"    JSON preview: {resp.text[:200]}")
        elif resp.status_code == 200:
            print(f"✗ {endpoint} -> HTML (not REST)")
        else:
            print(f"✗ {endpoint} -> {resp.status_code}")
    except Exception as e:
        print(f"✗ {endpoint} -> ERROR")