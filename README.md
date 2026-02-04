# FuelSaverUK-Data

Backend data service for FuelSaver UK iOS app. Fetches fuel prices from the GOV UK Fuel Finder API and publishes aggregated data to GitHub Pages.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        BACKEND (GitHub Actions)                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐     ┌──────────────────┐     ┌───────────────────────┐│
│  │ GOV UK Fuel │     │  GitHub Actions  │     │    GitHub Pages       ││
│  │ Finder API  │────▶│  (Every 30 min)  │────▶│  uk-fuel-prices.json  ││
│  │ (OAuth 2.0) │     │                  │     │  (Public, no auth)    ││
│  └─────────────┘     └──────────────────┘     └───────────────────────┘│
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         iOS APP (FuelSaver UK)                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  FuelPriceService:                                                      │
│    1. Primary: GitHub Pages (no auth, no rate limits)                   │
│    2. Fallback: Direct retailer endpoints (14 sources)                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Source

- **API**: GOV UK Fuel Finder API
- **Regulation**: The Motor Fuel Price (Open Data) Regulations 2025
- **Data Freshness**: Updated within 30 minutes of changes (matches GOV UK SLA)
- **Coverage**: All registered UK filling stations

## Setup

### 1. Register for GOV UK Fuel Finder API

1. Visit the [GOV UK Fuel Finder Developer Portal](https://www.fuel-finder.service.gov.uk)
2. Sign in with GOV.UK One Login
3. Register as an Information Recipient
4. Create an application to get your OAuth credentials

### 2. Configure GitHub Secrets

Add the following secrets to your repository:

| Secret Name | Description |
|-------------|-------------|
| `GOV_UK_CLIENT_ID` | OAuth client ID from GOV UK Fuel Finder Developer Portal |
| `GOV_UK_CLIENT_SECRET` | OAuth client secret from GOV UK Fuel Finder Developer Portal |

### 3. Enable GitHub Pages

1. Go to repository Settings → Pages
2. Set source to "GitHub Actions"

## Files

```
FuelSaverUK-Data/
├── .github/
│   └── workflows/
│       └── fetch-fuel-prices.yml    # Runs every 30 minutes
├── scripts/
│   ├── fetch_gov_uk_data.py         # OAuth + API fetch script
│   └── requirements.txt             # Python dependencies
├── data/
│   └── uk-fuel-prices.json          # Published to GitHub Pages (generated)
└── README.md
```

## Output Format

The `uk-fuel-prices.json` file follows this schema:

```json
{
  "last_updated": "2026-02-04T10:30:00Z",
  "source": "GOV UK Fuel Finder API",
  "station_count": 8500,
  "stations": [
    {
      "site_id": "gcpvj0mq9q0d",
      "brand": "Tesco",
      "address": "123 High Street, London",
      "postcode": "SW1A 1AA",
      "location": {
        "latitude": 51.5074,
        "longitude": -0.1278
      },
      "prices": {
        "E10": 142.9,
        "E5": 152.9,
        "B7": 147.9,
        "SDV": 157.9
      }
    }
  ]
}
```

## Rate Limits

GitHub Actions: Runs every 30 minutes (48 runs/day)
GOV UK API: 120 requests/minute, 10,000 requests/day

## License

Data is provided under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

© Crown copyright
