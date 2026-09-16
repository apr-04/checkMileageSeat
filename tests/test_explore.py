import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from web_app import app

def main():
    client = app.test_client()

    print("1. Testing /api/regions...")
    res = client.get('/api/regions')
    assert res.status_code == 200
    regions = res.get_json()
    print("Regions available:", list(regions.keys()))

    print("\n2. Testing /api/explore with small subset of airports (NRT, KIX)...")
    res = client.post('/api/explore', json={
        "departure": "ICN",
        "month": "202610",
        "airports": ["NRT", "KIX"],
        "seat_classes": ["X", "O"]
    })
    assert res.status_code == 200
    data = res.get_json()
    print("Success:", data.get("success"))
    print(f"Scanned: {data.get('scanned_count')}, Found: {data.get('found_count')}")
    
    for item in data.get("data", []):
        print(f"  Destination: {item['destination_name']} ({item['destination']})")
        print(f"  Total Available: {item['total_available_seats']}")
        print(f"  Classes: {item['available_classes']}")
        print(f"  Dates: {item['available_dates'][:5]}...")

if __name__ == "__main__":
    main()
