import os
import math
import requests as http_requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

WIND_SPEED_THRESHOLD_KMH = 40.0
RAIN_THRESHOLD_MM = 10.0
DANGEROUS_CONDITIONS = {"Thunderstorm", "Tornado", "Squall", "Hurricane"}

# Simulation mode for testing
simulation_mode = {
    "enabled": False,
    "force_unsafe": False,
    "unsafe_reason": ["HIGH_WIND"],
    "wind_speed_kmh": 65.0,
    "rain_mm": 15.0,
    "hazard_center": None,
    "hazard_zones": []  # List of {"lat": x, "lng": y, "radius_km": z} for grid-based simulation
}


def ms_to_kmh(speed_ms):
    return speed_ms * 3.6


def fetch_weather(lat, lng):
    """Fetch weather data from OpenWeatherMap for a single point."""
    params = {"lat": lat, "lon": lng, "appid": OPENWEATHER_API_KEY, "units": "metric"}
    try:
        resp = http_requests.get(OPENWEATHER_URL, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def evaluate_weather(data):
    """Evaluate weather data and return safety assessment."""
    reasons = []

    wind_speed_ms = data.get("wind", {}).get("speed", 0)
    wind_kmh = ms_to_kmh(wind_speed_ms)
    if wind_kmh > WIND_SPEED_THRESHOLD_KMH:
        reasons.append("HIGH_WIND")

    rain_1h = data.get("rain", {}).get("1h", 0)
    if rain_1h > RAIN_THRESHOLD_MM:
        reasons.append("HEAVY_RAIN")

    weather_list = data.get("weather", [])
    for w in weather_list:
        if w.get("main") in DANGEROUS_CONDITIONS:
            reasons.append(w["main"].upper())

    return reasons, wind_kmh, rain_1h


def interpolate_points(start, end_point, num_samples=5):
    """Generate evenly spaced sample points along a corridor."""
    points = []
    for i in range(num_samples):
        frac = i / max(num_samples - 1, 1)
        lat = start["lat"] + frac * (end_point["lat"] - start["lat"])
        lng = start["lng"] + frac * (end_point["lng"] - start["lng"])
        points.append({"lat": round(lat, 4), "lng": round(lng, 4)})
    return points


def is_point_in_hazard_zone(lat, lng, hazard_zones):
    """Check if a point is within any of the given hazard zones."""
    for zone in hazard_zones:
        zone_lat = zone.get("lat", 0)
        zone_lng = zone.get("lng", 0)
        radius = zone.get("radius_km", 2.0)
        distance = haversine_distance(lat, lng, zone_lat, zone_lng)
        if distance <= radius:
            return True, zone
    return False, None


def haversine_distance(lat1, lng1, lat2, lng2):
    """Calculate distance between two points in km using Haversine formula."""
    from math import radians, cos, sin, asin, sqrt
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))


# ---------------------------------------------------------------------------
# Simulation endpoints for testing
# ---------------------------------------------------------------------------

@app.route("/weather/simulate/enable", methods=["POST"])
@app.route("/simulate/enable", methods=["POST"])  # For Kong gateway (strip_path)
def enable_simulation():
    """Enable weather simulation mode for testing."""
    global simulation_mode
    data = request.get_json() or {}
    simulation_mode["enabled"] = True
    simulation_mode["force_unsafe"] = data.get("force_unsafe", True)
    simulation_mode["unsafe_reason"] = data.get("unsafe_reason", ["HIGH_WIND"])
    simulation_mode["wind_speed_kmh"] = data.get("wind_speed_kmh", 65.0)
    simulation_mode["rain_mm"] = data.get("rain_mm", 15.0)
    simulation_mode["hazard_center"] = data.get("hazard_center", None)
    # Support multiple hazard zones for grid-based simulation
    simulation_mode["hazard_zones"] = data.get("hazard_zones", [])
    print(f"  [SIMULATION] Weather simulation enabled: {simulation_mode}")
    return jsonify({
        "status": "SIMULATION_ENABLED",
        "config": simulation_mode,
        "message": "Weather service will return simulated conditions"
    })


@app.route("/weather/simulate/disable", methods=["POST"])
@app.route("/simulate/disable", methods=["POST"])  # For Kong gateway (strip_path)
def disable_simulation():
    """Disable weather simulation mode."""
    global simulation_mode
    simulation_mode["enabled"] = False
    print(f"  [SIMULATION] Weather simulation disabled")
    return jsonify({
        "status": "SIMULATION_DISABLED",
        "message": "Weather service will use real API data or dev mode"
    })


@app.route("/weather/simulate/status", methods=["GET"])
@app.route("/simulate/status", methods=["GET"])  # For Kong gateway (strip_path)
def simulation_status():
    """Get current simulation status."""
    return jsonify({
        "simulation_enabled": simulation_mode["enabled"],
        "config": simulation_mode if simulation_mode["enabled"] else None
    })


@app.route("/weather/check", methods=["GET"])
def check_weather():
    """Single-point weather check for pre-dispatch (Scenario 2)."""
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)

    if lat is None or lng is None:
        return jsonify({"error": "lat and lng are required"}), 400

    # Check simulation mode first
    if simulation_mode["enabled"]:
        if simulation_mode["force_unsafe"]:
            print(f"  [SIMULATION] Returning UNSAFE weather for ({lat}, {lng})")
            return jsonify({
                "status": "UNSAFE",
                "wind_speed_kmh": simulation_mode["wind_speed_kmh"],
                "reasons": simulation_mode["unsafe_reason"],
                "coords": {"lat": lat, "lng": lng},
                "source": "SIMULATION",
            })
        else:
            print(f"  [SIMULATION] Returning SAFE weather for ({lat}, {lng})")
            return jsonify({
                "status": "SAFE",
                "wind_speed_kmh": 10.0,
                "reasons": [],
                "coords": {"lat": lat, "lng": lng},
                "source": "SIMULATION",
            })

    if not OPENWEATHER_API_KEY:
        print(f"  [WEATHER] No API key — returning SAFE (dev mode) for ({lat}, {lng})")
        return jsonify({
            "status": "SAFE",
            "wind_speed_kmh": 0.0,
            "reasons": [],
            "coords": {"lat": lat, "lng": lng},
            "source": "DEV_MODE",
        })

    data = fetch_weather(lat, lng)
    if "error" in data and "weather" not in data:
        print(f"  [WEATHER] API error — returning SAFE (fallback) for ({lat}, {lng})")
        return jsonify({
            "status": "SAFE",
            "wind_speed_kmh": 0.0,
            "reasons": [],
            "coords": {"lat": lat, "lng": lng},
            "source": "FALLBACK",
        })

    reasons, wind_kmh, _ = evaluate_weather(data)
    status = "UNSAFE" if reasons else "SAFE"

    return jsonify({
        "status": status,
        "wind_speed_kmh": round(wind_kmh, 1),
        "reasons": reasons,
        "coords": {"lat": lat, "lng": lng},
    })


@app.route("/weather/live", methods=["POST"])
def live_corridor_check():
    """Corridor safety check for mid-flight polling (Scenario 3)."""
    data = request.get_json()
    order_id = data.get("order_id")
    drone_id = data.get("drone_id")
    current = data.get("current_coords", {})
    destination = data.get("destination_coords", {})

    # Check simulation mode first
    if simulation_mode["enabled"]:
        if simulation_mode["force_unsafe"]:
            # Use grid-based hazard zones if provided, otherwise use legacy single hazard center
            hazard_zones = simulation_mode.get("hazard_zones", [])

            if hazard_zones:
                # Grid-based simulation: check if the flight path intersects any hazard zone
                sample_points = interpolate_points(current, destination, num_samples=10)
                detected_hazards = []

                for point in sample_points:
                    in_hazard, zone = is_point_in_hazard_zone(
                        point["lat"], point["lng"], hazard_zones
                    )
                    if in_hazard and zone not in detected_hazards:
                        detected_hazards.append(zone)

                if detected_hazards:
                    # Return the first detected hazard zone for rerouting
                    primary_hazard = detected_hazards[0]
                    print(f"  [SIMULATION] Grid-based hazard detected for order {order_id}: {len(detected_hazards)} zone(s)")
                    return jsonify({
                        "status": "UNSAFE",
                        "reason": simulation_mode["unsafe_reason"],
                        "wind_kmh": simulation_mode["wind_speed_kmh"],
                        "hazard_zone": {
                            "center": {"lat": primary_hazard["lat"], "lng": primary_hazard["lng"]},
                            "radius_km": primary_hazard.get("radius_km", 2.0),
                        },
                        "recommended_action": "REROUTE",
                        "order_id": order_id,
                        "drone_id": drone_id,
                        "source": "SIMULATION_GRID",
                        "detected_hazards": len(detected_hazards),
                    })
                else:
                    # No hazard detected on flight path - safe to proceed
                    print(f"  [SIMULATION] No grid hazards on flight path for order {order_id}")
                    return jsonify({
                        "status": "SAFE",
                        "wind_kmh": 10.0,
                        "order_id": order_id,
                        "drone_id": drone_id,
                        "source": "SIMULATION_GRID",
                    })
            else:
                # Legacy single hazard zone (whole Singapore mode)
                hazard_center = simulation_mode["hazard_center"]
                if not hazard_center:
                    hazard_center = {
                        "lat": (current.get("lat", 0) + destination.get("lat", 0)) / 2,
                        "lng": (current.get("lng", 0) + destination.get("lng", 0)) / 2
                    }
                print(f"  [SIMULATION] Returning UNSAFE corridor weather for order {order_id} (legacy mode)")
                return jsonify({
                    "status": "UNSAFE",
                    "reason": simulation_mode["unsafe_reason"],
                    "wind_kmh": simulation_mode["wind_speed_kmh"],
                    "hazard_zone": {
                        "center": hazard_center,
                        "radius_km": 2.0,
                    },
                    "recommended_action": "REROUTE",
                    "order_id": order_id,
                    "drone_id": drone_id,
                    "source": "SIMULATION",
                })
        else:
            print(f"  [SIMULATION] Returning SAFE corridor weather for order {order_id}")
            return jsonify({
                "status": "SAFE",
                "wind_kmh": 10.0,
                "order_id": order_id,
                "drone_id": drone_id,
                "source": "SIMULATION",
            })

    if not OPENWEATHER_API_KEY:
        print(f"  [WEATHER] No API key — returning SAFE (dev mode) for corridor check")
        return jsonify({
            "status": "SAFE",
            "wind_kmh": 0.0,
            "order_id": order_id,
            "drone_id": drone_id,
            "source": "DEV_MODE",
        })

    sample_points = interpolate_points(current, destination, num_samples=5)

    worst_reasons = []
    worst_wind = 0
    hazard_center = None

    for point in sample_points:
        weather_data = fetch_weather(point["lat"], point["lng"])
        if "error" in weather_data and "weather" not in weather_data:
            continue

        reasons, wind_kmh, _ = evaluate_weather(weather_data)
        if reasons:
            for r in reasons:
                if r not in worst_reasons:
                    worst_reasons.append(r)
            if wind_kmh > worst_wind:
                worst_wind = wind_kmh
                hazard_center = point

    if worst_reasons:
        return jsonify({
            "status": "UNSAFE",
            "reason": worst_reasons,
            "wind_kmh": round(worst_wind, 1),
            "hazard_zone": {
                "center": hazard_center,
                "radius_km": 2.0,
            },
            "recommended_action": "REROUTE",
            "order_id": order_id,
            "drone_id": drone_id,
        })

    return jsonify({
        "status": "SAFE",
        "wind_kmh": round(worst_wind, 1),
        "order_id": order_id,
        "drone_id": drone_id,
    })


@app.route("/health", methods=["GET"])
def health():
    api_status = "configured" if OPENWEATHER_API_KEY else "not_configured"
    return jsonify({"status": "healthy", "service": "weather", "openweather_api": api_status})


if __name__ == "__main__":
    if not OPENWEATHER_API_KEY:
        print("  WARNING: OPENWEATHER_API_KEY not set. Weather checks will fail.")
    print("  Weather Service running on port 5006")
    app.run(host="0.0.0.0", port=5006, debug=True)
