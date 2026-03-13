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


@app.route("/weather/check", methods=["GET"])
def check_weather():
    """Single-point weather check for pre-dispatch (Scenario 2)."""
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)

    if lat is None or lng is None:
        return jsonify({"error": "lat and lng are required"}), 400

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


if __name__ == "__main__":
    if not OPENWEATHER_API_KEY:
        print("  WARNING: OPENWEATHER_API_KEY not set. Weather checks will fail.")
    print("  Weather Service running on port 5006")
    app.run(host="0.0.0.0", port=5006, debug=True)
