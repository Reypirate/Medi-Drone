# ═══════════════════════════════════════════════════════════════════════════════
# DRONE MANAGEMENT SERVICE
# ═══════════════════════════════════════════════════════════════════════════════
#
# ⚠️  DOCUMENTATION REMINDER ⚠️
# When modifying this file, please run: python scripts/sync_docs.py
# to check if documentation (README.md, docs/system-flow.md) needs updates.
#
# Key areas that require documentation updates:
# - New endpoints: Add to API endpoints section
# - New drone statuses: Update Drone Status Lifecycle section
# - Battery threshold changes: Update LOW_BATTERY_THRESHOLD value
# - New fields: Add to database schema section
#
# ═══════════════════════════════════════════════════════════════════════════════

import os
import time
import mysql.connector
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_CONFIG = {
    "host": os.environ.get("MYSQL_HOST", "mysql-drone"),
    "port": int(os.environ.get("MYSQL_PORT", 3306)),
    "user": "root",
    "password": os.environ.get("MYSQL_ROOT_PASSWORD", "root_password"),
    "database": "drone_db",
}

# Central Charging Depot Configuration
DEPOT_CONFIG = {
    "lat": float(os.environ.get("DEPOT_LAT", "1.3644")),
    "lng": float(os.environ.get("DEPOT_LNG", "103.8190")),
}


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def wait_for_db(max_retries=12, delay=5):
    for attempt in range(max_retries):
        try:
            conn = get_db()
            conn.close()
            print("  Connected to MySQL drone_db")
            return
        except mysql.connector.Error:
            print(f"  Waiting for MySQL... attempt {attempt + 1}/{max_retries}")
            time.sleep(delay)
    raise Exception("Could not connect to MySQL after retries")


@app.route("/drones/available", methods=["GET"])
def get_available():
    min_battery = int(request.args.get("min_battery_pct", 30))
    region = request.args.get("region", "CENTRAL")

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT drone_id, battery, status, lat, lng FROM drone")
        all_drones = cursor.fetchall()

        available = []
        excluded = []

        # Statuses that are NOT available for dispatch
        unavailable_statuses = {"IN_FLIGHT", "TO_HOSPITAL", "TO_CUSTOMER", "CHARGING", "RETURNING_TO_DEPOT", "LOW_BATTERY", "FAULTY"}

        for d in all_drones:
            if d["status"] not in unavailable_statuses and d["battery"] >= min_battery:
                available.append({
                    "drone_id": d["drone_id"],
                    "battery_pct": d["battery"],
                    "status": d["status"],
                    "coords": {"lat": d["lat"], "lng": d["lng"]},
                })
            else:
                reason = d["status"] if d["status"] in unavailable_statuses else ("LOW_BATTERY" if d["battery"] < min_battery else "UNKNOWN")
                excluded.append({
                    "drone_id": d["drone_id"],
                    "battery_pct": d["battery"],
                    "status": d["status"],
                    "reason": reason,
                })

        return jsonify({
            "region": region,
            "available_drones": available,
            "excluded_drones": excluded,
        })
    finally:
        cursor.close()
        conn.close()


@app.route("/drones/<drone_id>/status", methods=["PATCH"])
def update_status(drone_id):
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    try:
        sets = []
        vals = []
        for field in ("battery", "status", "lat", "lng", "current_lat", "current_lng", "target_lat", "target_lng"):
            if field in data:
                sets.append(f"{field} = %s")
                vals.append(data[field])

        if not sets:
            return jsonify({"error": "No fields to update"}), 400

        vals.append(drone_id)
        cursor.execute(f"UPDATE drone SET {', '.join(sets)} WHERE drone_id = %s", vals)
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Drone not found", "drone_id": drone_id}), 404

        return jsonify({"drone_id": drone_id, "status": "UPDATED", "updated_fields": list(data.keys())})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/drones/<drone_id>/position", methods=["PATCH"])
def update_position(drone_id):
    """Update drone's current position during flight."""
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    try:
        new_lat = data.get("lat")
        new_lng = data.get("lng")

        if not new_lat or not new_lng:
            return jsonify({"error": "lat and lng are required"}), 400

        cursor.execute(
            "UPDATE drone SET current_lat = %s, current_lng = %s WHERE drone_id = %s",
            (new_lat, new_lng, drone_id)
        )
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Drone not found", "drone_id": drone_id}), 404

        return jsonify({"drone_id": drone_id, "position": "UPDATED"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/drones", methods=["GET"])
def list_all():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT drone_id, battery, status, lat, lng FROM drone")
        drones = cursor.fetchall()
        return jsonify(drones)
    finally:
        cursor.close()
        conn.close()


@app.route("/health", methods=["GET"])
def health():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM drone")
        count = cursor.fetchone()
        cursor.close()
        conn.close()
        return jsonify({"status": "healthy", "service": "drone-management", "database": "connected", "drones_count": count[0] if count else 0})
    except Exception as e:
        return jsonify({"status": "unhealthy", "service": "drone-management", "error": str(e)}), 503


@app.route("/depot", methods=["GET"])
def get_depot():
    """Get the central charging depot location."""
    return jsonify({
        "status": "DEPOT",
        "location": {
            "lat": DEPOT_CONFIG["lat"],
            "lng": DEPOT_CONFIG["lng"]
        },
        "charging_bays": 3  # Number of available charging stations
    })


if __name__ == "__main__":
    wait_for_db()
    print("  Drone Management Service running on port 5008")
    app.run(host="0.0.0.0", port=5008, debug=True)


if __name__ == "__main__":
    wait_for_db()
    print("  Drone Management Service running on port 5008")
    app.run(host="0.0.0.0", port=5008, debug=True)
