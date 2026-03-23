import os
import json
import math
import uuid
import threading
import requests as http_requests
import pika
from flask import Flask, request, jsonify
from flask_cors import CORS
import amqp_setup
from common.request_tracking import (
    get_request_id, set_request_id, extract_request_id_from_amqp,
    log_with_context, init_flask_request_tracking
)

app = Flask(__name__)
CORS(app)
init_flask_request_tracking(app)
print("  [ORDER] Request tracking initialized")

INVENTORY_URL = os.environ.get("INVENTORY_URL", "http://inventory:5003")
HOSPITAL_URL = os.environ.get("HOSPITAL_URL", "http://hospital:5005")

orders = {}
amqp_channel = None
amqp_connection = None

EARTH_RADIUS_KM = 6371.0


def haversine(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def init_amqp():
    global amqp_connection, amqp_channel
    amqp_connection, amqp_channel = amqp_setup.get_connection()


def publish_message(exchange, routing_key, message):
    global amqp_channel, amqp_connection
    request_id = get_request_id()

    try:
        if amqp_channel is None or amqp_channel.is_closed:
            init_amqp()

        # Include request ID in AMQP headers for tracing
        headers = {}
        if request_id:
            headers['X-Request-ID'] = request_id

        amqp_channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2, headers=headers),
        )
        log_with_context(None, f"AMQP Published to {exchange}/{routing_key}: {message.get('order_id', 'N/A')}",
                       request_id=request_id, exchange=exchange, routing_key=routing_key)
    except Exception as e:
        log_with_context(None, f"AMQP ERROR publishing to {exchange}/{routing_key}: {e}",
                       level="error", request_id=request_id, error=str(e))
        init_amqp()
        amqp_channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2),
        )





def find_nearest_hospital(customer_coords, item_id, quantity):
    """Find the nearest hospital to the customer that has sufficient stock."""
    # Get hospitals with sufficient stock from inventory service
    try:
        search_resp = http_requests.get(
            f"{INVENTORY_URL}/inventory/search",
            params={"item_id": item_id, "quantity": quantity},
            timeout=10,
        )
        search_data = search_resp.json()
        stocked_hospitals = {h["hospital_id"] for h in search_data.get("hospitals", [])}
    except Exception as e:
        print(f"  [ORDER] Inventory search failed: {e}")
        return None, f"Inventory service unavailable: {e}"

    if not stocked_hospitals:
        return None, "NO_HOSPITAL_WITH_STOCK"

    # Get all hospital coordinates
    try:
        hosp_resp = http_requests.get(f"{HOSPITAL_URL}/hospitals", timeout=10)
        all_hospitals = hosp_resp.json()
    except Exception as e:
        print(f"  [ORDER] Hospital service unavailable: {e}")
        return None, f"Hospital service unavailable: {e}"

    # Filter to hospitals that have stock and compute distances
    candidates = []
    for h in all_hospitals:
        if h["hospital_id"] in stocked_hospitals:
            dist = haversine(
                customer_coords["lat"], customer_coords["lng"],
                h["lat"], h["lng"],
            )
            candidates.append({
                "hospital_id": h["hospital_id"],
                "name": h["name"],
                "lat": h["lat"],
                "lng": h["lng"],
                "distance_km": dist,
            })

    if not candidates:
        return None, "NO_ACTIVE_HOSPITAL_WITH_STOCK"

    candidates.sort(key=lambda c: c["distance_km"])
    return candidates[0], None


@app.route("/order", methods=["POST"])
def create_order():
    """Scenario 1: Doctor submits a delivery request with an optional explicit hospital_id. If not provided, falls back to nearest."""
    data = request.get_json()
    hospital_id = data.get("hospital_id")
    item_id = data.get("item_id")
    quantity = data.get("quantity", 1)
    urgency_level = data.get("urgency_level", "NORMAL")
    customer_address = data.get("customer_address", "")
    customer_coords = data.get("customer_coords")

    request_id = get_request_id()
    log_with_context(None, f"POST /order - Creating order: hospital_id={hospital_id or 'AUTO'}, item_id={item_id}, quantity={quantity}, urgency={urgency_level}",
                   request_id=request_id, hospital_id=hospital_id, item_id=item_id, quantity=quantity, urgency=urgency_level)

    if not customer_coords or "lat" not in customer_coords or "lng" not in customer_coords:
        log_with_context(None, "Order failed: Missing customer coordinates", level="warn", request_id=request_id)
        return jsonify({"status": "FAILED", "reason": "CUSTOMER_COORDS_REQUIRED",
                        "message": "Validated customer coordinates are required."}), 400

    if not item_id:
        log_with_context(None, "Order failed: Missing item_id", level="warn", request_id=request_id)
        return jsonify({"status": "FAILED", "reason": "ITEM_ID_REQUIRED"}), 400

    order_id = f"ORD-{uuid.uuid4().hex[:6].upper()}"
    log_with_context(None, f"Generated order_id: {order_id}", request_id=request_id, order_id=order_id)

    distance_km = None

    if hospital_id:
        # Validate the explicit hospital_id via Hospital Service
        try:
            hosp_resp = http_requests.get(f"{HOSPITAL_URL}/hospital/{hospital_id}/location", timeout=10)
            if hosp_resp.status_code == 404:
                log_with_context(None, f"Order {order_id} failed: Invalid hospital ID {hospital_id}", level="error", request_id=request_id, order_id=order_id)
                return jsonify({"order_id": order_id, "status": "FAILED", "reason": "INVALID_HOSPITAL", "message": "The selected hospital could not be found."}), 404
            hosp_resp.raise_for_status()
            hosp_data = hosp_resp.json()
        except Exception as e:
            log_with_context(None, f"Hospital verification failed: {e}", level="error", request_id=request_id, order_id=order_id)
            return jsonify({"order_id": order_id, "status": "ERROR", "message": f"Hospital verification unavailable: {e}"}), 503

        if hosp_data.get("status") != "ACTIVE":
            log_with_context(None, f"Order {order_id} failed: Hospital {hospital_id} is not ACTIVE", level="error", request_id=request_id, order_id=order_id)
            return jsonify({"order_id": order_id, "status": "FAILED", "reason": "HOSPITAL_NOT_ACTIVE", "message": "The selected hospital is currently not operational."}), 409

        hospital_name = hosp_data.get("location_name", hospital_id)
        hosp_coords = hosp_data.get("hospital_coords")
        if hosp_coords:
            distance_km = haversine(customer_coords["lat"], customer_coords["lng"], hosp_coords["lat"], hosp_coords["lng"])
        
        log_with_context(None, f"Explicit hospital verified: {hospital_id} ({hospital_name})",
                       request_id=request_id, order_id=order_id, hospital_id=hospital_id)
    else:
        # Fallback: Auto-select nearest hospital with stock
        nearest, error = find_nearest_hospital(customer_coords, item_id, quantity)
        if not nearest:
            orders[order_id] = {
                "order_id": order_id, "hospital_id": None, "item_id": item_id,
                "quantity": quantity, "urgency_level": urgency_level,
                "customer_address": customer_address, "status": f"FAILED_{error}",
                "drone_id": None, "eta_minutes": None, "dispatch_status": None,
            }
            log_with_context(None, f"Order {order_id} failed: {error}", level="error", request_id=request_id, order_id=order_id, error=error)
            publish_message("notifications", "notify.sms", {
                "event_type": "ORDER_FAILED",
                "order_id": order_id,
                "message": f"Order {order_id} failed: {error}. No hospital nearby has sufficient stock.",
            })
            return jsonify({
                "order_id": order_id,
                "status": "FAILED",
                "reason": error,
            }), 409

        hospital_id = nearest["hospital_id"]
        hospital_name = nearest["name"]
        distance_km = nearest["distance_km"]
        log_with_context(None, f"Auto-selected nearest hospital: {hospital_id} ({hospital_name}) at {distance_km:.1f}km",
                       request_id=request_id, order_id=order_id, hospital_id=hospital_id)

    orders[order_id] = {
        "order_id": order_id,
        "hospital_id": hospital_id,
        "hospital_name": hospital_name,
        "item_id": item_id,
        "quantity": quantity,
        "urgency_level": urgency_level,
        "customer_address": customer_address,
        "status": "PENDING",
        "drone_id": None,
        "eta_minutes": None,
        "dispatch_status": None,
    }

    # Reserve inventory from the selected hospital
    log_with_context(None, f"Reserving inventory: {item_id} x{quantity} from {hospital_id}",
                   request_id=request_id, order_id=order_id, item_id=item_id, quantity=quantity)
    try:
        reserve_resp = http_requests.post(
            f"{INVENTORY_URL}/inventory/reserve",
            json={"order_id": order_id, "hospital_id": hospital_id, "item_id": item_id, "quantity": quantity},
            headers={"X-Request-ID": request_id or ""},
            timeout=10,
        )
        reserve_data = reserve_resp.json()
    except Exception as e:
        orders[order_id]["status"] = "ERROR"
        log_with_context(None, f"Inventory service error: {e}", level="error", request_id=request_id, order_id=order_id)
        return jsonify({"order_id": order_id, "status": "ERROR", "message": f"Inventory service unavailable: {e}"}), 503

    if reserve_data.get("status") != "RESERVED":
        orders[order_id]["status"] = "FAILED_STOCK"
        log_with_context(None, f"Inventory reservation failed: {reserve_data.get('reason', 'UNKNOWN')}",
                       level="warn", request_id=request_id, order_id=order_id, reason=reserve_data.get("reason"))

        publish_message("orders", "order.failed", {
            "order_id": order_id,
            "hospital_id": hospital_id,
            "item_id": item_id,
            "reason": reserve_data.get("reason", "UNKNOWN"),
        })
        publish_message("notifications", "notify.sms", {
            "event_type": "ORDER_FAILED",
            "order_id": order_id,
            "hospital_id": hospital_id,
            "message": f"Order {order_id} failed: {reserve_data.get('reason', 'Insufficient stock')}.",
        })

        return jsonify({
            "order_id": order_id,
            "status": "FAILED",
            "reason": reserve_data.get("reason", "INSUFFICIENT_STOCK"),
        }), 409

    orders[order_id]["status"] = "CONFIRMED"
    log_with_context(None, f"Order {order_id} CONFIRMED - Publishing order.confirmed event",
                   request_id=request_id, order_id=order_id, status="CONFIRMED")

    publish_message("orders", "order.confirmed", {
        "order_id": order_id,
        "hospital_id": hospital_id,
        "item_id": item_id,
        "quantity": quantity,
        "urgency_level": urgency_level,
        "customer_address": customer_address,
        "customer_coords": customer_coords,
        "message": f"Order confirmed from {hospital_name}. Awaiting drone assignment.",
    })

    publish_message("notifications", "notify.sms", {
        "order_id": order_id,
        "hospital_id": hospital_id,
        "item_id": item_id,
        "event_type": "ORDER_CONFIRMED",
        "message": f"Your order {order_id} has been confirmed from {hospital_name}. Waiting for drone dispatch.",
    })

    return jsonify({
        "order_id": order_id,
        "status": "CONFIRMED",
        "hospital_id": hospital_id,
        "hospital_name": hospital_name,
        "distance_km": round(distance_km, 2) if distance_km else None,
        "item_id": item_id,
        "reserved_quantity": quantity,
        "message": f"Order confirmed. Dispatched from: {hospital_name}. Pending drone dispatch.",
    }), 201


@app.route("/order/<order_id>/cancel", methods=["POST"])
def cancel_order(order_id):
    """Called by Drone Dispatch when dispatch cannot proceed."""
    data = request.get_json() or {}
    reason = data.get("reason", "CANCELLED")
    cancel_message = data.get("message", f"Order cancelled: {reason}")

    order = orders.get(order_id)
    if not order:
        return jsonify({"error": "Order not found", "order_id": order_id}), 404

    inventory_released = False
    try:
        http_requests.post(
            f"{INVENTORY_URL}/inventory/release",
            json={
                "order_id": order_id,
                "hospital_id": order["hospital_id"],
                "item_id": order["item_id"],
                "quantity": order["quantity"],
            },
            timeout=10,
        )
        inventory_released = True
    except Exception as e:
        print(f"  [WARNING] Inventory release failed for order {order_id}: {e}")

    order["status"] = f"CANCELLED_{reason}"
    order["cancel_message"] = cancel_message

    stock_note = "Reserved stock has been released." if inventory_released else "Warning: stock release failed — please check inventory manually."
    publish_message("notifications", "notify.sms", {
        "event_type": "ORDER_CANCELLED",
        "order_id": order_id,
        "hospital_id": order["hospital_id"],
        "message": f"Order {order_id}: {cancel_message} {stock_note}",
    })

    return jsonify({"order_id": order_id, "status": order["status"], "message": cancel_message})


@app.route("/dispatch/update", methods=["POST"])
def dispatch_update():
    """Receives reroute/status updates from Drone Dispatch (Scenario 3.1)."""
    data = request.get_json()
    order_id = data.get("order_id")

    order = orders.get(order_id)
    if not order:
        return jsonify({"error": "Order not found", "order_id": order_id}), 404

    order["drone_id"] = data.get("drone_id", order.get("drone_id"))
    order["dispatch_status"] = data.get("dispatch_status", order.get("dispatch_status"))
    order["eta_minutes"] = data.get("eta_minutes", order.get("eta_minutes"))

    # Always update mission_phase if provided
    if "mission_phase" in data:
        order["mission_phase"] = data["mission_phase"]

    if data.get("dispatch_status") == "REROUTED_IN_FLIGHT":
        # Preserve the mission phase (TO_HOSPITAL or TO_CUSTOMER) when rerouting
        mission_phase = data.get("mission_phase", order.get("mission_phase", order.get("status", "TO_CUSTOMER")))
        order["status"] = mission_phase  # Keep phase badge (To Hospital or To Customer)
        order["route_id"] = data.get("route_id")
        order["updated_eta"] = data.get("updated_eta")

    return jsonify({
        "message": "Dispatch update recorded successfully",
        "order_id": order_id,
        "order_status": order["status"],
        "dispatch_status": order["dispatch_status"],
    })


@app.route("/dispatch/confirm", methods=["POST"])
def dispatch_confirm():
    """Receives drone assignment confirmation from Drone Dispatch (Scenario 2, Step 7)."""
    data = request.get_json()
    order_id = data.get("order_id")

    order = orders.get(order_id)
    if not order:
        return jsonify({"error": "Order not found", "order_id": order_id}), 404

    drone_id = data.get("drone_id")
    eta_minutes = data.get("eta_minutes")
    dispatch_status = data.get("status", "TO_HOSPITAL")  # Drone dispatch sends TO_HOSPITAL status
    mission_phase = data.get("mission_phase", dispatch_status)  # Get mission phase if provided

    order["status"] = dispatch_status  # Main status reflects mission phase
    order["mission_phase"] = mission_phase  # Store mission phase separately
    order["drone_id"] = drone_id
    order["eta_minutes"] = eta_minutes
    order["dispatch_status"] = dispatch_status

    return jsonify({
        "order_id": order_id,
        "status": dispatch_status,
        "drone_id": drone_id,
        "eta_minutes": eta_minutes,
    })


@app.route("/dispatch/failure", methods=["POST"])
def dispatch_failure():
    """Receives dispatch failure from Drone Dispatch (Scenario 3.2)."""
    data = request.get_json()
    order_id = data.get("order_id")
    failure_code = data.get("failure_code", "UNKNOWN")

    order = orders.get(order_id)
    if not order:
        return jsonify({"error": "Order not found", "order_id": order_id}), 404

    order["status"] = f"CANCELLED_{failure_code}"
    order["dispatch_status"] = data.get("dispatch_status", "ABORTED")

    inventory_released = False
    try:
        http_requests.post(
            f"{INVENTORY_URL}/inventory/release",
            json={
                "order_id": order_id,
                "hospital_id": order["hospital_id"],
                "item_id": order["item_id"],
                "quantity": order["quantity"],
            },
            timeout=10,
        )
        inventory_released = True
    except Exception as e:
        print(f"  [WARNING] Inventory release failed for order {order_id}: {e}")

    stock_note = "Reserved stock has been released." if inventory_released else "Warning: stock release failed — please check inventory manually."
    publish_message("notifications", "notify.sms", {
        "event_type": f"ORDER_CANCELLED_{failure_code}",
        "order_id": order_id,
        "hospital_id": order["hospital_id"],
        "message": f"URGENT: Delivery cancelled mid-flight due to {failure_code.replace('_', ' ').lower()}. "
                   f"Drone returning to base. {stock_note}",
    })

    return jsonify({
        "order_id": order_id,
        "drone_id": data.get("drone_id"),
        "status": order["status"],
        "reason": f"{failure_code}",
    })


@app.route("/dispatch/complete", methods=["POST"])
def dispatch_complete():
    """Receives delivery completion from Drone Dispatch - marks order as DELIVERED."""
    data = request.get_json()
    order_id = data.get("order_id")
    drone_id = data.get("drone_id")

    order = orders.get(order_id)
    if not order:
        return jsonify({"error": "Order not found", "order_id": order_id}), 404

    order["status"] = "DELIVERED"
    order["dispatch_status"] = "DELIVERED"
    order["drone_id"] = drone_id or order.get("drone_id")

    # Publish delivery notification via both exchanges
    publish_message("orders", "order.delivered", {
        "order_id": order_id,
        "drone_id": order["drone_id"],
        "hospital_id": order.get("hospital_id"),
        "item_id": order.get("item_id"),
        "message": f"Order {order_id} successfully delivered by drone {order['drone_id']}.",
    })

    publish_message("notifications", "notify.sms", {
        "order_id": order_id,
        "drone_id": order["drone_id"],
        "hospital_id": order.get("hospital_id"),
        "item_id": order.get("item_id"),
        "event_type": "ORDER_DELIVERED",
        "message": f"Your order {order_id} has been successfully delivered by drone {order['drone_id']}!",
    })

    return jsonify({
        "order_id": order_id,
        "status": "DELIVERED",
        "drone_id": order["drone_id"],
    })


@app.route("/order/<order_id>", methods=["GET"])
def get_order(order_id):
    order = orders.get(order_id)
    if not order:
        return jsonify({"error": "Order not found", "order_id": order_id}), 404
    return jsonify(order)


@app.route("/orders", methods=["GET"])
def list_orders():
    status_filter = request.args.get("status")  # active, cancelled, completed

    filtered_orders = list(orders.values())

    if status_filter:
        if status_filter == "active":
            filtered_orders = [o for o in filtered_orders if o.get("status") in ("TO_HOSPITAL", "TO_CUSTOMER", "IN_TRANSIT", "DISPATCHED")]
        elif status_filter == "cancelled":
            filtered_orders = [o for o in filtered_orders if o.get("status", "").startswith("CANCELLED")]
        elif status_filter == "completed":
            filtered_orders = [o for o in filtered_orders if o.get("status") == "DELIVERED"]

    return jsonify({"orders": filtered_orders})


@app.route("/order/<order_id>", methods=["DELETE"])
def delete_order(order_id):
    """Delete an order (only allowed for cancelled or completed orders)."""
    order = orders.get(order_id)
    if not order:
        return jsonify({"error": "Order not found", "order_id": order_id}), 404

    current_status = order.get("status")

    # Cannot delete active orders
    if current_status in ("TO_HOSPITAL", "TO_CUSTOMER", "IN_TRANSIT", "DISPATCHED", "CONFIRMED", "PENDING"):
        return jsonify({
            "error": "Cannot delete active order",
            "order_id": order_id,
            "status": current_status,
            "message": "Only cancelled or completed orders can be deleted"
        }), 400

    del orders[order_id]
    return jsonify({
        "order_id": order_id,
        "status": "DELETED",
        "message": f"Order {order_id} has been deleted"
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "order", "orders_count": len(orders)})


if __name__ == "__main__":
    init_amqp()
    print("  Order Service running on port 5001")
    app.run(host="0.0.0.0", port=5001, debug=True)
