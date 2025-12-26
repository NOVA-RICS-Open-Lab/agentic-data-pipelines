import requests

base = "http://localhost:5001"

# V2 file-based endpoints (no database needed)
endpoints_to_test = [
    "/server/getaasx2/0",  # Get AASX package by index
    "/aas/0",  # Get AAS by index
    "/aas/0/aas",  # Get AAS details
    "/aas/0/submodels",  # Get submodels for AAS at index 0
    "/submodel/0",  # Get first submodel
]

for endpoint in endpoints_to_test:
    url = base + endpoint
    try:
        resp = requests.get(url, timeout=2)
        ct = resp.headers.get('content-type', '')
        print(f"✓ {endpoint} -> {resp.status_code} ({ct})")
        if resp.status_code == 200:
            if 'json' in ct:
                print(f"  JSON keys: {list(resp.json().keys())[:5]}")
            else:
                print(f"  Preview: {resp.text[:100]}")
    except Exception as e:
        print(f"✗ {endpoint} -> {str(e)[:80]}")