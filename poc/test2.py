import requests

base = "http://localhost:5001"

# Try API v3 endpoints with /api prefix
endpoints_to_test = [
    "/api/v3.0/shells",
    "/api/v1/aas",
    "/aas/CarASS",
    "/packages",
    "/packages/aHR0cHM6Ly9leGFtcGxlLmNvbS9pZHMvc20vNTE4NV8zMTQwXzIxNTJfOTI5MQ",
]

for endpoint in endpoints_to_test:
    url = base + endpoint
    try:
        resp = requests.get(url, timeout=2)
        print(f"✓ {endpoint} -> {resp.status_code} ({resp.headers.get('content-type')})")
        if 'json' in resp.headers.get('content-type', ''):
            print(f"  JSON preview: {resp.text[:200]}")
    except Exception as e:
        print(f"✗ {endpoint} -> ERROR: {str(e)[:80]}")