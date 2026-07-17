"""
Mocked Hetzner Cloud API responses.

Shaped to match the real documented response schemas at
https://docs.hetzner.cloud/reference/cloud (GET /v1/servers, GET /v1/pricing)
so this can be swapped for real HTTP calls later with zero changes
to the parsing/cost-reconstruction logic downstream.

TODO once real credentials exist: verify these shapes against a real
API response and adjust for any drift (Hetzner does version their docs,
but always double check a live call before trusting this blindly).
"""

MOCK_SERVERS_RESPONSE = {
    "servers": [
        {
            "id": 42,
            "name": "web-01",
            "status": "running",
            "created": "2026-06-01T00:00:00+00:00",
            "server_type": {
                "id": 1,
                "name": "cx23",
                "cores": 2,
                "memory": 4,
                "disk": 40,
            },
            "datacenter": {
                "id": 1,
                "name": "fsn1-dc14",
                "location": {"name": "fsn1", "country": "DE"},
            },
            "public_net": {
                "ipv4": {"ip": "203.0.113.10"},
            },
        },
        {
            "id": 43,
            "name": "worker-01",
            "status": "running",
            "created": "2026-06-15T00:00:00+00:00",
            "server_type": {
                "id": 3,
                "name": "cpx31",
                "cores": 4,
                "memory": 8,
                "disk": 160,
            },
            "datacenter": {
                "id": 2,
                "name": "hel1-dc2",
                "location": {"name": "hel1", "country": "FI"},
            },
            "public_net": {
                "ipv4": {"ip": "203.0.113.11"},
            },
        },
    ],
    "meta": {"pagination": {"page": 1, "per_page": 25, "total_entries": 2}},
}

MOCK_PRICING_RESPONSE = {
    "pricing": {
        "currency": "EUR",
        "vat_rate": "19.00",
        "server_types": [
            {
                "id": 1,
                "name": "cx23",
                "prices": [
                    {
                        "location": "fsn1",
                        "price_hourly": {"net": "0.0072", "gross": "0.008568"},
                        "price_monthly": {"net": "5.49", "gross": "6.5331"},
                    }
                ],
            },
            {
                "id": 3,
                "name": "cpx31",
                "prices": [
                    {
                        "location": "hel1",
                        "price_hourly": {"net": "0.0179", "gross": "0.021301"},
                        "price_monthly": {"net": "13.10", "gross": "15.589"},
                    }
                ],
            },
        ],
        "traffic": {"price_per_tb": {"net": "1.00", "gross": "1.19"}},
    }
}
