import os
import json
import math
import uuid
import threading
import requests as http_requests
import pika
import mysql.connector
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
import amqp_setup
from common.request_tracking import (
    get_request_id, set_request_id,
    log_with_context, init_flask_request_tracking
)

app = Flask(__name__)
CORS(app)
init_flask_request_tracking(app)

INVENTORY_URL = os.environ.get("INVENTORY_URL", "http://inventory:5003")
HOSPITAL_URL  = os.environ.get("HOSPITAL_URL",  "http://hospital:5005")

amqp_channel    = None
amqp_connection = None
EARTH_RADIUS_KM = 6371.0

# ── Database helpers ──────────────────────────────────────────────────────────

DB_CONFIG = {
    "host":     os.environ.get("MYSQL_HOST", "mysql-order"),
    "port":     int(os.environ.get("MYSQL_PORT", 3306)),
    "user":     "root",
    "password": os.environ.get("MYSQL_ROOT_PASSWORD", "root_password"),
    "database": "order_db",
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def wait_for_db(max_retries=12, delay=5):
    for attempt in range(max_retries):
        try:
            conn = get_db()
            conn.close()
            print("  [ORDER] Connected to MySQL order_db")
            return
        except mysql.connector.Error:
            print(f"  [ORDER] Waiting for MySQL... attempt {attempt + 1}/{max_retries}")
            time.sleep(delay)
    raise Exception("Could not connect to MySQL after retries")

def db_create_order(order_data: dict):
    """Insert a new order row."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        customer_coords = order_data.get("customer_coords") or {}
        cursor.execute("""
            INSERT INTO orders (
                order_id, hospital_id, hospital_name, item_id, quantity,
                urgency_level, customer_address, customer_lat, customer_lng, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            order_data["order_id"],
            order_data.get("hospital_id"),
            order_data.get("hospital_name"),
            order_data.get("item_id"),
            order_data.get("quantity", 1),
            order_data.get("urgency_level", "NORMAL"),
            order_data.get("customer_address", ""),
            customer_coords.get("lat"),
            customer_coords.get("lng"),
            order_data.get("status", "PENDING"),
        ))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def db_get_order(order_id: str) -> dict | None:
    """Fetch a single order by ID. Returns None if not found."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,))
        row = cursor.fetchone()
        if not row:
            return None
        # Deserialise JSON column
        if row.get("reroute_details") and isinstance(row["reroute_details"], str):
            row["reroute_details"] = json.loads(row["reroute_details"])
        # Rebuild customer_coords sub-object for callers that expect it
        if row.get("customer_lat") and row.get("customer_lng"):
            row["customer_coords"] = {"lat": row["customer_lat"], "lng": row["customer_lng"]}
        return row
    finally:
        cursor.close()
        conn.close()

def db_update_order(order_id: str, fields: dict):
    """Update arbitrary fields on an order row."""
    if not fields:
        return
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Serialise any dict/list values to JSON
        processed = {}
        for k, v in fields.items():
            if isinstance(v, (dict, list)):
                processed[k] = json.dumps(v)
            else:
                processed[k] = v

        set_clause = ", ".join(f"{k} = %s" for k in processed)
        values = list(processed.values()) + [order_id]
        cursor.execute(f"UPDATE orders SET {set_clause} WHERE order_id = %s", values)
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def db_delete_order(order_id: str) -> bool:
    """Hard-delete an order. Returns True if a row was deleted."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM orders WHERE order_id = %s", (order_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()

def db_list_orders(status_filter: str | None = None) -> list[dict]:
    """Return all orders, optionally filtered by status group."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        if status_filter == "active":
            cursor.execute("""
                SELECT * FROM orders
                WHERE status IN ('CONFIRMED','TO_HOSPITAL','TO_CUSTOMER','IN_TRANSIT','DISPATCHED')
                ORDER BY created_at DESC
            """)
        elif status_filter == "cancelled":
            cursor.execute("""
                SELECT * FROM orders
                WHERE status LIKE 'CANCELLED%'
                ORDER BY created_at DESC
            """)
        elif status_filter == "completed":
            cursor.execute("""
                SELECT * FROM orders WHERE status = 'DELIVERED'
                ORDER BY created_at DESC
            """)
        else:
            cursor.execute("SELECT * FROM orders ORDER BY created_at DESC")

        rows = cursor.fetchall()
        for row in rows:
            if row.get("reroute_details") and isinstance(row["reroute_details"], str):
                row["reroute_details"] = json.loads(row["reroute_details"])
            if row.get("customer_lat") and row.get("customer_lng"):
                row["customer_coords"] = {"lat": row["customer_lat"], "lng": row["customer_lng"]}
        return rows
    finally:
        cursor.close()
        conn.close()

# ── AMQP helpers ──────────────────────────────────────────────────────────────

def init_amqp():
    global amqp_connection, amqp_channel
    amqp_connection, amqp_channel = amqp_setup.get_connection()

def publish_message(exchange, routing_key, message):
    global amqp_channel, amqp_connection
    request_id = get_request_id()
    try:
        if amqp_channel is None or amqp_channel.is_closed:
            init_amqp()
        headers = {"X-Request-ID": request_id} if request_id else {}
        amqp_channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2, headers=headers),
        )
    except Exception as e:
        print(f"  [AMQP ERROR] {e}")
        init_amqp()
        amqp_channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2),
        )

# ── Hospital auto-selection ───────────────────────────────────────────────────

def haversine(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlng/2)**2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))

def find_nearest_hospital(customer_coords, item_id, quantity):
    try:
        resp = http_requests.get(
            f"{INVENTORY_URL}/inventory/search",
            params={"item_id": item_id, "quantity": quantity},
            timeout=10,
        )
        stocked = {h["hospital_id"] for h in resp.json().get("hospitals", [])}
    except Exception as e:
        return None, f"Inventory service unavailable: {e}"

    if not stocked:
        return None, "NO_HOSPITAL_WITH_STOCK"

    try:
        all_hosps = http_requests.get(f"{HOSPITAL_URL}/hospitals", timeout=10).json()
    except Exception as e:
        return None, f"Hospital service unavailable: {e}"

    candidates = []
    for h in all_hosps:
        if h["hospital_id"] in stocked:
            dist = haversine(
                customer_coords["lat"], customer_coords["lng"],
                h["lat"], h["lng"],
            )
            candidates.append({**h, "distance_km": dist})

    if not candidates:
        return None, "NO_ACTIVE_HOSPITAL_WITH_STOCK"

    candidates.sort(key=lambda c: c["distance_km"])
    return candidates[0], None

# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/order", methods=["POST"])
def create_order():
    data = request.get_json()
    hospital_id     = data.get("hospital_id")
    item_id         = data.get("item_id")
    quantity        = data.get("quantity", 1)
    urgency_level   = data.get("urgency_level", "NORMAL")
    customer_address= data.get("customer_address", "")
    customer_coords = data.get("customer_coords")

    if not customer_coords or "lat" not in customer_coords:
        return jsonify({"status": "FAILED", "reason": "CUSTOMER_COORDS_REQUIRED"}), 400
    if not item_id:
        return jsonify({"status": "FAILED", "reason": "ITEM_ID_REQUIRED"}), 400

    order_id     = f"ORD-{uuid.uuid4().hex[:6].upper()}"
    distance_km  = None
    hospital_name = None

    if hospital_id:
        try:
            resp = http_requests.get(
                f"{HOSPITAL_URL}/hospital/{hospital_id}/location", timeout=10)
            if resp.status_code == 404:
                return jsonify({"order_id": order_id, "status": "FAILED",
                                "reason": "INVALID_HOSPITAL"}), 404
            hosp_data = resp.json()
        except Exception as e:
            return jsonify({"order_id": order_id, "status": "ERROR",
                            "message": str(e)}), 503

        if hosp_data.get("status") != "ACTIVE":
            return jsonify({"order_id": order_id, "status": "FAILED",
                            "reason": "HOSPITAL_NOT_ACTIVE"}), 409

        hospital_name = hosp_data.get("location_name", hospital_id)
        coords = hosp_data.get("hospital_coords", {})
        if coords:
            distance_km = haversine(
                customer_coords["lat"], customer_coords["lng"],
                coords["lat"], coords["lng"])
    else:
        nearest, error = find_nearest_hospital(customer_coords, item_id, quantity)
        if not nearest:
            db_create_order({
                "order_id": order_id, "hospital_id": None, "item_id": item_id,
                "quantity": quantity, "urgency_level": urgency_level,
                "customer_address": customer_address,
                "customer_coords": customer_coords,
                "status": f"FAILED_{error}",
            })
            publish_message("notifications", "notify.sms", {
                "event_type": "ORDER_FAILED", "order_id": order_id,
                "message": f"Order {order_id} failed: {error}.",
            })
            return jsonify({"order_id": order_id, "status": "FAILED", "reason": error}), 409

        hospital_id   = nearest["hospital_id"]
        hospital_name = nearest["name"]
        distance_km   = nearest["distance_km"]

    # Write to DB as PENDING before attempting inventory reservation
    db_create_order({
        "order_id": order_id, "hospital_id": hospital_id,
        "hospital_name": hospital_name, "item_id": item_id,
        "quantity": quantity, "urgency_level": urgency_level,
        "customer_address": customer_address,
        "customer_coords": customer_coords,
        "status": "PENDING",
    })

    # Reserve inventory
    try:
        reserve_resp = http_requests.post(
            f"{INVENTORY_URL}/inventory/reserve",
            json={"order_id": order_id, "hospital_id": hospital_id,
                  "item_id": item_id, "quantity": quantity},
            timeout=10,
        )
        reserve_data = reserve_resp.json()
    except Exception as e:
        db_update_order(order_id, {"status": "ERROR"})
        return jsonify({"order_id": order_id, "status": "ERROR",
                        "message": str(e)}), 503

    if reserve_data.get("status") != "RESERVED":
        db_update_order(order_id, {"status": "FAILED_STOCK"})
        publish_message("orders", "order.failed", {
            "order_id": order_id, "hospital_id": hospital_id,
            "item_id": item_id, "reason": reserve_data.get("reason"),
        })
        publish_message("notifications", "notify.sms", {
            "event_type": "ORDER_FAILED", "order_id": order_id,
            "hospital_id": hospital_id,
            "message": f"Order failed: {reserve_data.get('reason', 'Insufficient stock')}.",
        })
        return jsonify({"order_id": order_id, "status": "FAILED",
                        "reason": reserve_data.get("reason", "INSUFFICIENT_STOCK")}), 409

    db_update_order(order_id, {"status": "CONFIRMED"})

    publish_message("orders", "order.confirmed", {
        "order_id": order_id, "hospital_id": hospital_id,
        "item_id": item_id, "quantity": quantity,
        "urgency_level": urgency_level,
        "customer_address": customer_address,
        "customer_coords": customer_coords,
        "message": f"Order confirmed from {hospital_name}.",
    })
    publish_message("notifications", "notify.sms", {
        "order_id": order_id, "hospital_id": hospital_id,
        "event_type": "ORDER_CONFIRMED",
        "message": f"Order {order_id} confirmed from {hospital_name}. Awaiting drone dispatch.",
    })

    return jsonify({
        "order_id": order_id, "status": "CONFIRMED",
        "hospital_id": hospital_id, "hospital_name": hospital_name,
        "distance_km": round(distance_km, 2) if distance_km else None,
        "item_id": item_id, "reserved_quantity": quantity,
        "message": f"Order confirmed. Dispatching from: {hospital_name}.",
    }), 201


@app.route("/order/<order_id>/cancel", methods=["POST"])
def cancel_order(order_id):
    data   = request.get_json() or {}
    reason = data.get("reason", "CANCELLED")
    msg    = data.get("message", f"Order cancelled: {reason}")

    order = db_get_order(order_id)
    if not order:
        return jsonify({"error": "Order not found", "order_id": order_id}), 404

    released = False
    try:
        http_requests.post(
            f"{INVENTORY_URL}/inventory/release",
            json={"order_id": order_id, "hospital_id": order["hospital_id"],
                  "item_id": order["item_id"], "quantity": order["quantity"]},
            timeout=10,
        )
        released = True
    except Exception as e:
        print(f"  [WARNING] Inventory release failed: {e}")

    db_update_order(order_id, {
        "status": f"CANCELLED_{reason}",
        "cancel_message": msg,
    })

    stock_note = "Reserved stock released." if released else "Warning: stock release failed."
    publish_message("notifications", "notify.sms", {
        "event_type": "ORDER_CANCELLED", "order_id": order_id,
        "hospital_id": order["hospital_id"],
        "message": f"Order {order_id}: {msg} {stock_note}",
    })

    return jsonify({"order_id": order_id,
                    "status": f"CANCELLED_{reason}", "message": msg})


@app.route("/dispatch/confirm", methods=["POST"])
def dispatch_confirm():
    data     = request.get_json()
    order_id = data.get("order_id")
    order    = db_get_order(order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404

    dispatch_status = data.get("status", "TO_HOSPITAL")
    db_update_order(order_id, {
        "status":          dispatch_status,
        "mission_phase":   data.get("mission_phase", dispatch_status),
        "drone_id":        data.get("drone_id"),
        "eta_minutes":     data.get("eta_minutes"),
        "dispatch_status": dispatch_status,
    })

    return jsonify({"order_id": order_id, "status": dispatch_status,
                    "drone_id": data.get("drone_id"),
                    "eta_minutes": data.get("eta_minutes")})


@app.route("/dispatch/update", methods=["POST"])
def dispatch_update():
    data     = request.get_json()
    order_id = data.get("order_id")
    order    = db_get_order(order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404

    updates = {}
    if "drone_id"        in data: updates["drone_id"]        = data["drone_id"]
    if "dispatch_status" in data: updates["dispatch_status"] = data["dispatch_status"]
    if "eta_minutes"     in data: updates["eta_minutes"]     = data["eta_minutes"]
    if "mission_phase"   in data: updates["mission_phase"]   = data["mission_phase"]
    if "route_id"        in data: updates["route_id"]        = data["route_id"]
    if "updated_eta"     in data: updates["updated_eta"]     = data["updated_eta"]
    if "reroute_details" in data: updates["reroute_details"] = data["reroute_details"]

    if "dispatch_status" in data:
        updates["status"] = data.get("mission_phase", data["dispatch_status"])

    if updates:
        db_update_order(order_id, updates)

    refreshed = db_get_order(order_id)
    return jsonify({
        "message": "Dispatch update recorded",
        "order_id": order_id,
        "order_status":    refreshed["status"],
        "dispatch_status": refreshed["dispatch_status"],
    })


@app.route("/dispatch/failure", methods=["POST"])
def dispatch_failure():
    data         = request.get_json()
    order_id     = data.get("order_id")
    failure_code = data.get("failure_code", "UNKNOWN")
    order        = db_get_order(order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404

    db_update_order(order_id, {
        "status":          f"CANCELLED_{failure_code}",
        "dispatch_status": data.get("dispatch_status", "ABORTED"),
    })

    released = False
    try:
        http_requests.post(
            f"{INVENTORY_URL}/inventory/release",
            json={"order_id": order_id, "hospital_id": order["hospital_id"],
                  "item_id": order["item_id"], "quantity": order["quantity"]},
            timeout=10,
        )
        released = True
    except Exception as e:
        print(f"  [WARNING] Inventory release failed: {e}")

    stock_note = "Reserved stock released." if released else "Warning: stock release failed."
    publish_message("notifications", "notify.sms", {
        "event_type": f"ORDER_CANCELLED_{failure_code}",
        "order_id": order_id, "hospital_id": order["hospital_id"],
        "message": f"URGENT: Delivery cancelled due to {failure_code.replace('_',' ').lower()}. {stock_note}",
    })

    return jsonify({"order_id": order_id, "drone_id": data.get("drone_id"),
                    "status": f"CANCELLED_{failure_code}",
                    "reason": failure_code})


@app.route("/dispatch/complete", methods=["POST"])
def dispatch_complete():
    data     = request.get_json()
    order_id = data.get("order_id")
    order    = db_get_order(order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404

    drone_id = data.get("drone_id") or order.get("drone_id")
    db_update_order(order_id, {
        "status":          "DELIVERED",
        "dispatch_status": "DELIVERED",
        "drone_id":        drone_id,
    })

    publish_message("orders", "order.delivered", {
        "order_id": order_id, "drone_id": drone_id,
        "hospital_id": order["hospital_id"], "item_id": order["item_id"],
        "message": f"Order {order_id} delivered by drone {drone_id}.",
    })
    publish_message("notifications", "notify.sms", {
        "order_id": order_id, "drone_id": drone_id,
        "hospital_id": order["hospital_id"], "event_type": "ORDER_DELIVERED",
        "message": f"Your order {order_id} has been delivered by drone {drone_id}!",
    })

    return jsonify({"order_id": order_id, "status": "DELIVERED", "drone_id": drone_id})


@app.route("/order/<order_id>", methods=["GET"])
def get_order(order_id):
    order = db_get_order(order_id)
    if not order:
        return jsonify({"error": "Order not found", "order_id": order_id}), 404
    return jsonify(order)


@app.route("/orders", methods=["GET"])
def list_orders():
    status_filter = request.args.get("status")
    orders = db_list_orders(status_filter)
    return jsonify({"orders": orders})


@app.route("/order/<order_id>", methods=["DELETE"])
def delete_order(order_id):
    order = db_get_order(order_id)
    if not order:
        return jsonify({"error": "Order not found", "order_id": order_id}), 404

    active_statuses = {"TO_HOSPITAL","TO_CUSTOMER","IN_TRANSIT","DISPATCHED","CONFIRMED","PENDING"}
    if order["status"] in active_statuses:
        return jsonify({
            "error": "Cannot delete active order",
            "order_id": order_id, "status": order["status"],
        }), 400

    db_delete_order(order_id)
    return jsonify({"order_id": order_id, "status": "DELETED",
                    "message": f"Order {order_id} deleted"})


@app.route("/health", methods=["GET"])
def health():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orders")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return jsonify({"status": "healthy", "service": "order",
                        "database": "connected", "orders_count": count})
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 503


if __name__ == "__main__":
    wait_for_db()
    init_amqp()
    print("  Order Service running on port 5001")
    app.run(host="0.0.0.0", port=5001, debug=False)