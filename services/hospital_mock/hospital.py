import os
import time
import mysql.connector
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_CONFIG = {
    "host": os.environ.get("MYSQL_HOST", "mysql-hospital"),
    "port": int(os.environ.get("MYSQL_PORT", 3306)),
    "user": "root",
    "password": os.environ.get("MYSQL_ROOT_PASSWORD", "root_password"),
    "database": "hospital_db",
}


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def wait_for_db(max_retries=12, delay=5):
    for attempt in range(max_retries):
        try:
            conn = get_db()
            conn.close()
            print("  Connected to MySQL hospital_db")
            return
        except mysql.connector.Error:
            print(f"  Waiting for MySQL... attempt {attempt + 1}/{max_retries}")
            time.sleep(delay)
    raise Exception("Could not connect to MySQL after retries")


@app.route("/hospital/<hospital_id>/location", methods=["GET"])
def get_location(hospital_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT hospital_id, name, status, lat, lng FROM hospital WHERE hospital_id = %s",
            (hospital_id,),
        )
        row = cursor.fetchone()

        if not row:
            return jsonify({"error": "Hospital not found", "hospital_id": hospital_id}), 404

        return jsonify({
            "hospital_id": row["hospital_id"],
            "location_name": row["name"],
            "status": row["status"],
            "hospital_coords": {"lat": row["lat"], "lng": row["lng"]},
        })
    finally:
        cursor.close()
        conn.close()


@app.route("/hospitals", methods=["GET"])
def list_hospitals():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT hospital_id, name, status, lat, lng FROM hospital WHERE status = 'ACTIVE'")
        rows = cursor.fetchall()
        return jsonify([
            {
                "hospital_id": r["hospital_id"],
                "name": r["name"],
                "lat": r["lat"],
                "lng": r["lng"],
            }
            for r in rows
        ])
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    wait_for_db()
    print("  Hospital Service (Mock) running on port 5005")
    app.run(host="0.0.0.0", port=5005, debug=True)
