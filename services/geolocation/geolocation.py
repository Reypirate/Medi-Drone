import os
import hashlib
import requests as http_requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

geocode_cache = {}

SG_BOUNDS = {"lat_min": 1.15, "lat_max": 1.47, "lng_min": 103.60, "lng_max": 104.05}

FALLBACK_COORDINATES = {
    "singapore": {"lat": 1.3521, "lng": 103.8198},
    "changi": {"lat": 1.3644, "lng": 103.9915},
    "jurong": {"lat": 1.3329, "lng": 103.7436},
    "woodlands": {"lat": 1.4382, "lng": 103.7891},
    "tampines": {"lat": 1.3496, "lng": 103.9568},
    "bedok": {"lat": 1.3236, "lng": 103.9273},
    "orchard": {"lat": 1.3048, "lng": 103.8318},
    "toa payoh": {"lat": 1.3343, "lng": 103.8563},
    "ang mo kio": {"lat": 1.3691, "lng": 103.8454},
    "bukit merah": {"lat": 1.2819, "lng": 103.8239},
}


def is_within_singapore(lat, lng):
    return (SG_BOUNDS["lat_min"] <= lat <= SG_BOUNDS["lat_max"] and
            SG_BOUNDS["lng_min"] <= lng <= SG_BOUNDS["lng_max"])


def extract_address_components(result):
    """Extract country and postal_code from Google Maps address_components."""
    country = ""
    postal_code = ""
    for component in result.get("address_components", []):
        types = component.get("types", [])
        if "country" in types:
            country = component.get("long_name", "")
        if "postal_code" in types:
            postal_code = component.get("long_name", "")
    return country, postal_code


def hash_address(address):
    """Compute SHA-256 hash of the normalized address for cache key."""
    normalized = address.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def fallback_geocode(address):
    """Return approximate coordinates based on keyword matching when API is unavailable."""
    addr_lower = address.strip().lower()
    for keyword, coords in FALLBACK_COORDINATES.items():
        if keyword in addr_lower:
            return coords, f"{address} (approximate)"
    return FALLBACK_COORDINATES["singapore"], f"{address} (default: Singapore center)"


def build_response(coords, formatted, source, country="", postal_code="", cache_key="", **extra):
    region_valid = is_within_singapore(coords["lat"], coords["lng"])
    resp = {
        "customer_coords": coords,
        "source": source,
        "formatted_address": formatted,
        "region_valid": region_valid,
        "country": country or ("Singapore" if region_valid else "Unknown"),
        "postal_code": postal_code,
        "cache_key": cache_key,
    }
    resp.update(extra)
    return resp


@app.route("/maps/api/geocode/json", methods=["GET"])
def geocode():
    address = request.args.get("address", "")
    region = request.args.get("region", "sg")

    if not address:
        return jsonify({"error": "address parameter is required"}), 400

    addr_hash = hash_address(address)
    cache_key = addr_hash[:12]

    if addr_hash in geocode_cache:
        cached = geocode_cache[addr_hash]
        return jsonify(build_response(
            cached["coords"], cached["formatted_address"], "CACHE",
            country=cached.get("country", ""),
            postal_code=cached.get("postal_code", ""),
            cache_key=cache_key,
        ))

    if not GOOGLE_MAPS_API_KEY:
        coords, formatted = fallback_geocode(address)
        geocode_cache[addr_hash] = {
            "coords": coords, "formatted_address": formatted,
            "country": "Singapore", "postal_code": "",
        }
        print(f"  [GEOCODE] No API key — using fallback for: {address}")
        return jsonify(build_response(coords, formatted, "FALLBACK",
                                      country="Singapore", cache_key=cache_key))

    try:
        params = {"address": address, "key": GOOGLE_MAPS_API_KEY, "region": region}
        resp = http_requests.get(GEOCODE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        api_status = data.get("status")
        if api_status == "REQUEST_DENIED":
            error_msg = data.get("error_message", "Geocoding API not enabled or key invalid")
            print(f"  [GEOCODE] API REQUEST_DENIED: {error_msg}")
            return jsonify({"error": "Geocoding API not available", "detail": error_msg,
                            "api_status": api_status}), 502

        if api_status != "OK" or not data.get("results"):
            if api_status == "ZERO_RESULTS":
                return jsonify({"error": "No results found for this address",
                                "api_status": api_status}), 404
            print(f"  [GEOCODE] API returned {api_status} for: {address}")
            return jsonify({"error": f"Geocoding failed with status: {api_status}",
                            "api_status": api_status}), 502

        result = data["results"][0]
        location = result["geometry"]["location"]
        formatted = result.get("formatted_address", address)
        country, postal_code = extract_address_components(result)

        coords = {"lat": location["lat"], "lng": location["lng"]}
        geocode_cache[addr_hash] = {
            "coords": coords, "formatted_address": formatted,
            "country": country, "postal_code": postal_code,
        }

        return jsonify(build_response(coords, formatted, "EXTERNAL_API",
                                      country=country, postal_code=postal_code,
                                      cache_key=cache_key))

    except Exception as e:
        print(f"  [GEOCODE] API call failed: {e} — using fallback for: {address}")
        coords, formatted = fallback_geocode(address)
        geocode_cache[addr_hash] = {
            "coords": coords, "formatted_address": formatted,
            "country": "Singapore", "postal_code": "",
        }
        return jsonify(build_response(coords, formatted, "FALLBACK",
                                      country="Singapore", cache_key=cache_key))


@app.route("/maps/api/reverse-geocode", methods=["GET"])
def reverse_geocode():
    """Reverse geocode lat/lng to a formatted address with Singapore validation."""
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)

    if lat is None or lng is None:
        return jsonify({"error": "lat and lng query parameters are required"}), 400

    coords = {"lat": lat, "lng": lng}
    cache_key_str = f"rev_{lat:.6f}_{lng:.6f}"
    cache_key = hashlib.sha256(cache_key_str.encode()).hexdigest()[:12]

    if cache_key in geocode_cache:
        cached = geocode_cache[cache_key]
        return jsonify(build_response(
            cached["coords"], cached["formatted_address"], "CACHE",
            country=cached.get("country", ""),
            postal_code=cached.get("postal_code", ""),
            cache_key=cache_key,
        ))

    if not GOOGLE_MAPS_API_KEY:
        region_valid = is_within_singapore(lat, lng)
        formatted = f"{lat}, {lng} (Singapore)" if region_valid else f"{lat}, {lng}"
        country = "Singapore" if region_valid else "Unknown"
        geocode_cache[cache_key] = {
            "coords": coords, "formatted_address": formatted,
            "country": country, "postal_code": "",
        }
        print(f"  [REVERSE-GEOCODE] No API key — fallback for ({lat}, {lng})")
        return jsonify(build_response(coords, formatted, "FALLBACK",
                                      country=country, cache_key=cache_key))

    try:
        params = {"latlng": f"{lat},{lng}", "key": GOOGLE_MAPS_API_KEY}
        resp = http_requests.get(GEOCODE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        api_status = data.get("status")
        if api_status == "REQUEST_DENIED":
            error_msg = data.get("error_message", "Geocoding API not enabled or key invalid")
            print(f"  [REVERSE-GEOCODE] API REQUEST_DENIED: {error_msg}")
            return jsonify({"error": "Geocoding API not available", "detail": error_msg,
                            "api_status": api_status}), 502

        if api_status != "OK" or not data.get("results"):
            if api_status == "ZERO_RESULTS":
                return jsonify({"error": "No results found for these coordinates",
                                "api_status": api_status}), 404
            print(f"  [REVERSE-GEOCODE] API returned {api_status} for ({lat}, {lng})")
            return jsonify({"error": f"Geocoding failed with status: {api_status}",
                            "api_status": api_status}), 502

        result = data["results"][0]
        formatted = result.get("formatted_address", f"{lat}, {lng}")
        country, postal_code = extract_address_components(result)

        geocode_cache[cache_key] = {
            "coords": coords, "formatted_address": formatted,
            "country": country, "postal_code": postal_code,
        }

        return jsonify(build_response(coords, formatted, "EXTERNAL_API",
                                      country=country, postal_code=postal_code,
                                      cache_key=cache_key))

    except Exception as e:
        print(f"  [REVERSE-GEOCODE] API call failed: {e} — fallback for ({lat}, {lng})")
        region_valid = is_within_singapore(lat, lng)
        formatted = f"{lat}, {lng} (Singapore)" if region_valid else f"{lat}, {lng}"
        country = "Singapore" if region_valid else "Unknown"
        geocode_cache[cache_key] = {
            "coords": coords, "formatted_address": formatted,
            "country": country, "postal_code": "",
        }
        return jsonify(build_response(coords, formatted, "FALLBACK",
                                      country=country, cache_key=cache_key))


@app.route("/geocode/cache/stats", methods=["GET"])
def cache_stats():
    return jsonify({"cache_size": len(geocode_cache), "entries": list(geocode_cache.keys())[:20]})


@app.route("/health", methods=["GET"])
def health():
    api_status = "configured" if GOOGLE_MAPS_API_KEY else "not_configured"
    return jsonify({"status": "healthy", "service": "geolocation", "google_maps_api": api_status, "cache_size": len(geocode_cache)})


if __name__ == "__main__":
    if not GOOGLE_MAPS_API_KEY:
        print("  WARNING: GOOGLE_MAPS_API_KEY not set. Using fallback coordinates.")
    print("  Geolocation Service running on port 5007")
    app.run(host="0.0.0.0", port=5007, debug=True)
