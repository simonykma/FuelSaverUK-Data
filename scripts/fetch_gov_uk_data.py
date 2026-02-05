#!/usr/bin/env python3
"""
Fetch fuel prices from GOV UK Fuel Finder API and save to JSON.

This script:
1. Authenticates with GOV UK API using OAuth 2.0 client credentials
2. Fetches fuel prices for all fuel types (E10, E5, B7, SDV)
3. Aggregates and deduplicates stations
4. Outputs CMA-compatible JSON format for the iOS app

Requires environment variables:
- GOV_UK_CLIENT_ID: OAuth client ID
- GOV_UK_CLIENT_SECRET: OAuth client secret

Based on:
- GOV UK Fuel Finder API: https://www.fuel-finder.service.gov.uk
- The Motor Fuel Price (Open Data) Regulations 2025
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Any

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# GOV UK Fuel Finder API endpoints
# Confirmed by Fuel Finder Support Team (VE3 Global):
# Base URL: https://www.fuel-finder.service.gov.uk/
# Note: API requires access from UK-based network
API_BASE_URL = "https://www.fuel-finder.service.gov.uk"

# Token endpoint paths to try (different docs show different endpoints)
# 1. API Docs PDF shows: POST /api/v1/oauth/generate_access_token (JSON body)
# 2. API Authentication PDF shows standard OAuth 2.0 (form-urlencoded)
TOKEN_PATHS = [
    "/api/v1/oauth/generate_access_token",  # From API Docs PDF
    "/oauth/token",                          # Standard OAuth 2.0 pattern
    "/api/oauth/token",                      # Alternative pattern
    "/v1/oauth/token",                       # Version prefixed
]

# Prices endpoint path (from Rest API PDF and API Authentication PDF)
# GET /v1/prices?fuel_type=unleaded
PRICES_PATH = "/v1/prices"

# Fuel types as per CMA Open Data Schema
# API Authentication PDF shows: fuel_type=unleaded
# We map to standard codes
FUEL_TYPES = ["E10", "E5", "B7", "SDV"]

# Request timeout in seconds
REQUEST_TIMEOUT = 30


def get_access_token() -> str:
    """
    Obtain OAuth 2.0 access token using client credentials.
    
    Tries multiple endpoint paths and both JSON and form-urlencoded formats
    as the documentation shows different approaches.
    
    Returns:
        Access token string
        
    Raises:
        ValueError: If credentials are not set
        requests.RequestException: If all token requests fail
    """
    client_id = os.environ.get("GOV_UK_CLIENT_ID")
    client_secret = os.environ.get("GOV_UK_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        raise ValueError(
            "Missing OAuth credentials. Set GOV_UK_CLIENT_ID and GOV_UK_CLIENT_SECRET environment variables."
        )
    
    last_error = None
    
    for token_path in TOKEN_PATHS:
        token_url = f"{API_BASE_URL}{token_path}"
        logger.info(f"Trying token endpoint: {token_url}")
        
        # Try 1: JSON format (as per API Docs PDF)
        try:
            response = requests.post(
                token_url,
                json={
                    "client_id": client_id,
                    "client_secret": client_secret
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                logger.info(f"Success with JSON format at {token_path}")
                return _extract_token(response.json())
            logger.warning(f"JSON format returned {response.status_code}: {response.text[:200]}")
        except requests.RequestException as e:
            logger.warning(f"JSON format failed for {token_path}: {e}")
            last_error = e
        
        # Try 2: Form-urlencoded with all OAuth fields (as per API Authentication PDF)
        try:
            response = requests.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "fuelfinder.read"
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json"
                },
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                logger.info(f"Success with form-urlencoded at {token_path}")
                return _extract_token(response.json())
            logger.warning(f"Form-urlencoded returned {response.status_code}: {response.text[:200]}")
        except requests.RequestException as e:
            logger.warning(f"Form-urlencoded failed for {token_path}: {e}")
            last_error = e
        
        # Try 3: Basic Auth with client credentials (alternative OAuth pattern)
        try:
            response = requests.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "scope": "fuelfinder.read"
                },
                auth=(client_id, client_secret),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json"
                },
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                logger.info(f"Success with Basic Auth at {token_path}")
                return _extract_token(response.json())
            logger.warning(f"Basic Auth returned {response.status_code}: {response.text[:200]}")
        except requests.RequestException as e:
            logger.warning(f"Basic Auth failed for {token_path}: {e}")
            last_error = e
    
    raise requests.RequestException(f"All token endpoints failed. Last error: {last_error}")


def _extract_token(data: dict) -> str:
    """Extract access token from response data."""
    # Handle wrapped format: {"success": true, "data": {"access_token": "..."}}
    if data.get("success") and "data" in data:
        token = data["data"].get("access_token")
    else:
        # Standard OAuth format: {"access_token": "..."}
        token = data.get("access_token")
    
    if not token:
        raise ValueError(f"No access token in response: {data}")
    
    logger.info("Successfully obtained access token")
    return token


def fetch_prices_by_fuel_type(token: str, fuel_type: str) -> list[dict[str, Any]]:
    """
    Fetch fuel prices for a specific fuel type.
    
    Args:
        token: OAuth access token
        fuel_type: Fuel type code (E10, E5, B7, SDV)
        
    Returns:
        List of station dictionaries
    """
    prices_url = f"{API_BASE_URL}{PRICES_PATH}"
    logger.info(f"Fetching {fuel_type} prices from {prices_url}...")
    
    response = requests.get(
        prices_url,
        params={"fuel_type": fuel_type},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        },
        timeout=REQUEST_TIMEOUT
    )
    
    response.raise_for_status()
    
    data = response.json()
    stations = data.get("stations", [])
    
    logger.info(f"Fetched {len(stations)} stations with {fuel_type} prices")
    return stations


def aggregate_stations(all_stations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Aggregate stations and merge prices by site_id.
    
    Stations may appear multiple times (once per fuel type). This function
    merges them into single station objects with all available prices.
    
    Args:
        all_stations: List of all station records (may have duplicates)
        
    Returns:
        List of unique stations with merged prices
    """
    logger.info(f"Aggregating {len(all_stations)} station records...")
    
    by_id: dict[str, dict[str, Any]] = {}
    
    for station in all_stations:
        # Use site_id as unique identifier (12-character geohash)
        site_id = station.get("site_id")
        if not site_id:
            continue
        
        if site_id not in by_id:
            # First occurrence: store the station
            by_id[site_id] = station.copy()
            # Ensure prices is a dict
            if not isinstance(by_id[site_id].get("prices"), dict):
                by_id[site_id]["prices"] = {}
        else:
            # Subsequent occurrence: merge prices
            existing_prices = by_id[site_id].get("prices", {})
            new_prices = station.get("prices", {})
            if isinstance(new_prices, dict):
                existing_prices.update(new_prices)
            by_id[site_id]["prices"] = existing_prices
    
    unique_stations = list(by_id.values())
    logger.info(f"Aggregated to {len(unique_stations)} unique stations")
    
    return unique_stations


def transform_to_cma_format(stations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Transform GOV UK API response to CMA-compatible format for iOS app.
    
    The iOS app expects the CMA Open Data Schema format.
    
    Args:
        stations: List of stations from GOV UK API
        
    Returns:
        List of stations in CMA format
    """
    transformed = []
    
    for station in stations:
        # Extract location coordinates
        location = station.get("location", {})
        lat = location.get("latitude")
        lng = location.get("longitude")
        
        # Skip stations without valid coordinates
        if lat is None or lng is None:
            continue
        
        # Validate coordinate bounds
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            logger.warning(f"Invalid coordinates for station {station.get('site_id')}: lat={lat}, lng={lng}")
            continue
        
        # Build address from available fields
        address_parts = []
        address_obj = station.get("address", {})
        if isinstance(address_obj, dict):
            if address_obj.get("line1"):
                address_parts.append(address_obj["line1"])
            if address_obj.get("town"):
                address_parts.append(address_obj["town"])
            postcode = address_obj.get("postcode", "")
        elif isinstance(address_obj, str):
            address_parts.append(address_obj)
            postcode = station.get("postcode", "")
        else:
            postcode = station.get("postcode", "")
        
        address = ", ".join(address_parts) if address_parts else station.get("address", "")
        
        # Build CMA-compatible station object
        cma_station = {
            "site_id": station.get("site_id", ""),
            "brand": station.get("brand", "Unknown"),
            "address": address,
            "postcode": postcode,
            "location": {
                "latitude": lat,
                "longitude": lng
            },
            "prices": station.get("prices", {})
        }
        
        transformed.append(cma_station)
    
    return transformed


def fetch_all_prices(token: str) -> list[dict[str, Any]]:
    """
    Fetch all fuel prices from GOV UK API.
    
    Fetches prices for each fuel type and aggregates them.
    
    Args:
        token: OAuth access token
        
    Returns:
        List of aggregated station dictionaries
    """
    all_stations = []
    
    for fuel_type in FUEL_TYPES:
        try:
            stations = fetch_prices_by_fuel_type(token, fuel_type)
            all_stations.extend(stations)
        except requests.HTTPError as e:
            logger.error(f"Failed to fetch {fuel_type} prices: {e}")
            # Continue with other fuel types
    
    return aggregate_stations(all_stations)


def save_output(stations: list[dict[str, Any]], output_path: str) -> None:
    """
    Save aggregated data to JSON file.
    
    Args:
        stations: List of station dictionaries
        output_path: Path to output JSON file
    """
    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source": "GOV UK Fuel Finder API",
        "station_count": len(stations),
        "stations": stations
    }
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved {len(stations)} stations to {output_path}")


def main() -> int:
    """
    Main entry point.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        logger.info("Starting GOV UK Fuel Finder data fetch...")
        logger.info(f"API Base URL: {API_BASE_URL}")
        
        # Get OAuth token
        token = get_access_token()
        
        # Fetch all prices
        stations = fetch_all_prices(token)
        
        if not stations:
            logger.error("No stations fetched")
            return 1
        
        # Transform to CMA format
        cma_stations = transform_to_cma_format(stations)
        
        if not cma_stations:
            logger.error("No valid stations after transformation")
            return 1
        
        # Save output
        output_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data",
            "uk-fuel-prices.json"
        )
        save_output(cma_stations, output_path)
        
        logger.info(f"Successfully fetched and saved {len(cma_stations)} stations")
        return 0
        
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    except requests.HTTPError as e:
        logger.error(f"API error: {e}")
        return 1
    except requests.RequestException as e:
        logger.error(f"Network error: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
