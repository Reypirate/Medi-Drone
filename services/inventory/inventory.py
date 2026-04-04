import os
import time
import mysql.connector
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_CONFIG = {
    "host": os.environ.get("MYSQL_HOST", "mysql-inventory"),
    "port": int(os.environ.get("MYSQL_PORT", 3306)),
    "user": "root",
    "password": os.environ.get("MYSQL_ROOT_PASSWORD", "root_password"),
    "database": "inventory_db",
}


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def wait_for_db(max_retries=12, delay=5):
    for attempt in range(max_retries):
        try:
            conn = get_db()
            conn.close()
            print("  Connected to MySQL inventory_db")
            return
        except mysql.connector.Error:
            print(f"  Waiting for MySQL... attempt {attempt + 1}/{max_retries}")
            time.sleep(delay)
    raise Exception("Could not connect to MySQL after retries")


@app.route("/inventory/reserve", methods=["POST"])
def reserve():
    data = request.get_json()
    order_id = data.get("order_id")
    hospital_id = data.get("hospital_id")
    item_id = data.get("item_id")
    quantity = data.get("quantity", 1)

    if not hospital_id:
        return jsonify({"status": "FAILED", "reason": "HOSPITAL_ID_REQUIRED", "order_id": order_id}), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT hospital_id, item_id, name, quantity FROM inventory "
            "WHERE hospital_id = %s AND item_id = %s FOR UPDATE",
            (hospital_id, item_id),
        )
        row = cursor.fetchone()

        if not row:
            return jsonify({"status": "FAILED", "reason": "ITEM_NOT_FOUND", "order_id": order_id}), 404

        if row["quantity"] < quantity:
            conn.rollback()
            return jsonify({
                "status": "FAILED",
                "reason": "INSUFFICIENT_STOCK",
                "order_id": order_id,
                "hospital_id": hospital_id,
                "available": row["quantity"],
                "requested": quantity,
            }), 409

        cursor.execute(
            "UPDATE inventory SET quantity = quantity - %s WHERE hospital_id = %s AND item_id = %s",
            (quantity, hospital_id, item_id),
        )
        conn.commit()

        return jsonify({
            "status": "RESERVED",
            "order_id": order_id,
            "hospital_id": hospital_id,
            "item_id": item_id,
            "reserved_quantity": quantity,
            "remaining_stock": row["quantity"] - quantity,
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "ERROR", "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/inventory/release", methods=["POST"])
def release():
    data = request.get_json()
    order_id = data.get("order_id")
    hospital_id = data.get("hospital_id")
    item_id = data.get("item_id")
    quantity = data.get("quantity", 0)

    if not quantity and "items" in data:
        items = data["items"]
        item_id = items[0].get("item_id") if items else item_id
        quantity = items[0].get("reserved_quantity", 0) if items else quantity

    if not hospital_id:
        return jsonify({"status": "FAILED", "reason": "HOSPITAL_ID_REQUIRED", "order_id": order_id}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE inventory SET quantity = quantity + %s WHERE hospital_id = %s AND item_id = %s",
            (quantity, hospital_id, item_id),
        )
        conn.commit()
        return jsonify({
            "status": "RELEASED",
            "order_id": order_id,
            "hospital_id": hospital_id,
            "item_id": item_id,
            "released_quantity": quantity,
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "ERROR", "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/inventory", methods=["GET"])
def list_inventory():
    hospital_id = request.args.get("hospital_id")
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        if hospital_id:
            cursor.execute(
                "SELECT hospital_id, item_id, name, quantity FROM inventory WHERE hospital_id = %s ORDER BY item_id",
                (hospital_id,),
            )
        else:
            cursor.execute("SELECT hospital_id, item_id, name, quantity FROM inventory ORDER BY hospital_id, item_id")
        return jsonify(cursor.fetchall())
    finally:
        cursor.close()
        conn.close()


@app.route("/inventory/items", methods=["GET"])
def list_items():
    """Return distinct items with total quantity across all hospitals (for UI dropdown)."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT item_id, name, SUM(quantity) AS total_quantity "
            "FROM inventory GROUP BY item_id, name ORDER BY item_id"
        )
        return jsonify(cursor.fetchall())
    finally:
        cursor.close()
        conn.close()


@app.route("/inventory/search", methods=["GET"])
def search():
    """Return hospital_ids that have sufficient stock for the given item and quantity."""
    item_id = request.args.get("item_id")
    quantity = int(request.args.get("quantity", 1))

    if not item_id:
        return jsonify({"error": "item_id is required"}), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT hospital_id, quantity FROM inventory "
            "WHERE item_id = %s AND quantity >= %s ORDER BY quantity DESC",
            (item_id, quantity),
        )
        rows = cursor.fetchall()
        return jsonify({
            "item_id": item_id,
            "requested_quantity": quantity,
            "hospitals": [{"hospital_id": r["hospital_id"], "available": r["quantity"]} for r in rows],
        })
    finally:
        cursor.close()
        conn.close()


@app.route("/inventory/restock", methods=["POST"])
def restock():
    """Reset all inventory to original seed quantities across all hospitals."""
    seed_data = [
        ("HOSP-001", "BLOOD-O-NEG", "O-Negative Blood Bags", 50),
        ("HOSP-001", "BLOOD-A-POS", "A-Positive Blood Bags", 30),
        ("HOSP-001", "BLOOD-B-POS", "B-Positive Blood Bags", 15),
        ("HOSP-001", "DEFIB-01", "Portable Defibrillator", 8),
        ("HOSP-001", "ORGAN-KIT-01", "Organ Transport Kit", 5),
        ("HOSP-001", "EPINEPHRINE-01", "Epinephrine Auto-Injector", 20),
        ("HOSP-002", "BLOOD-O-NEG", "O-Negative Blood Bags", 20),
        ("HOSP-002", "BLOOD-B-POS", "B-Positive Blood Bags", 25),
        ("HOSP-002", "DEFIB-01", "Portable Defibrillator", 6),
        ("HOSP-002", "EPINEPHRINE-01", "Epinephrine Auto-Injector", 40),
        ("HOSP-003", "BLOOD-O-NEG", "O-Negative Blood Bags", 35),
        ("HOSP-003", "BLOOD-A-POS", "A-Positive Blood Bags", 20),
        ("HOSP-003", "DEFIB-01", "Portable Defibrillator", 10),
        ("HOSP-003", "ORGAN-KIT-01", "Organ Transport Kit", 3),
        ("HOSP-003", "EPINEPHRINE-01", "Epinephrine Auto-Injector", 25),
        ("HOSP-004", "BLOOD-O-NEG", "O-Negative Blood Bags", 15),
        ("HOSP-004", "BLOOD-A-POS", "A-Positive Blood Bags", 10),
        ("HOSP-004", "ORGAN-KIT-01", "Organ Transport Kit", 8),
        ("HOSP-004", "DEFIB-01", "Portable Defibrillator", 4),
        ("HOSP-004", "EPINEPHRINE-01", "Epinephrine Auto-Injector", 15),
        ("HOSP-005", "BLOOD-O-NEG", "O-Negative Blood Bags", 25),
        ("HOSP-005", "BLOOD-A-POS", "A-Positive Blood Bags", 15),
        ("HOSP-005", "BLOOD-B-POS", "B-Positive Blood Bags", 10),
        ("HOSP-005", "DEFIB-01", "Portable Defibrillator", 5),
        ("HOSP-005", "EPINEPHRINE-01", "Epinephrine Auto-Injector", 45),
    ]

    conn = get_db()
    cursor = conn.cursor()
    try:
        for hospital_id, item_id, name, quantity in seed_data:
            cursor.execute(
                "INSERT INTO inventory (hospital_id, item_id, name, quantity) "
                "VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE quantity = %s",
                (hospital_id, item_id, name, quantity, quantity),
            )
        conn.commit()
        return jsonify({"status": "RESTOCKED", "items_reset": len(seed_data)})
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "ERROR", "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/health", methods=["GET"])
def health():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM inventory")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return jsonify({"status": "healthy", "service": "inventory", "database": "connected", "inventory_count": result[0] if result else 0})
    except Exception as e:
        return jsonify({"status": "unhealthy", "service": "inventory", "error": str(e)}), 503


if __name__ == "__main__":
    wait_for_db()
    print("  Inventory Service running on port 5003")
    app.run(host="0.0.0.0", port=5003, debug=True)
