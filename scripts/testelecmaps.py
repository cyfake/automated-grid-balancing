import requests
API_KEY = "Xx829MX7w87J0KKpWcO7"
import json
BASE_URL = "https://api.electricitymaps.com/v3"

headers = {
    "auth-token": API_KEY
}

endpoints = {
    "wind": "/electricity-source/wind/latest?zone=DE",
    "carbon_intensity": "/carbon-intensity/latest?zone=DE",
    "renewable_percentage": "/renewable-energy/latest?zone=DE"
}

results = {}

for name, endpoint in endpoints.items():
    url = BASE_URL + endpoint
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print("Request failed:", response.status_code)
        print(response.text)
        continue

    data = response.json()
    results[name] = data
    print("\n---", name.upper(), "---")
    print(json.dumps(data, indent=2))


# Save all responses for schema inspection
with open("electricitymaps_sample_data.json", "w") as f:
    json.dump(results, f, indent=2)


print("Saved responses for schema inspection") 