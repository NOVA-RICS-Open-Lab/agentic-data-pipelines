import requests

base = "http://localhost:5001"

endpoints_to_test = [
    "/server/listaas",
    "/aas",
    "/shells", 
    "/server/getaasx/0",
    "/packages/0",
]

for endpoint in endpoints_to_test:
    url = base + endpoint
    try:
        resp = requests.get(url, timeout=2)
        print(f"✓ {endpoint} -> {resp.status_code} ({resp.headers.get('content-type')})")
        if resp.status_code == 200:
            print(f"  Preview: {resp.text[:200]}")
    except Exception as e:
        print(f"✗ {endpoint} -> ERROR: {str(e)[:80]}")