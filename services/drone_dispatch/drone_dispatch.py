import os
import json
import time
import math
import threading
import requests as http_requests
import pika
from flask import Flask, request, jsonify
from flask_cors import CORS
import amqp_setup

app = Flask(__name__)
CORS(app)

ORDER_URL = os.environ.get("ORDER_URL", "http://order:5001")
HOSPITAL_URL = os.environ.get("HOSPITAL_URL", "http://hospital:5005")
GEOLOCATION_URL = os.environ.get("GEOLOCATION_URL", "http://geolocation:5007")
DRONE_MGMT_URL = os.environ.get("DRONE_MGMT_URL", "http://drone-management:5008")
WEATHER_URL = os.environ.get("WEATHER_URL", "http://weather:5006")
ROUTE_URL = os.environ.get("ROUTE_URL", "http://route-planning:5009")

GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

ITEM_WEIGHTS = {
    "BLOOD-O-NEG": 0.6,
    "BLOOD-A-POS": 0.6,
    "BLOOD-B-POS": 0.6,
    "DEFIB-01": 2.5,
    "ORGAN-KIT-01": 3.0,
    "EPINEPHRINE-01": 0.2,
}
DEFAULT_ITEM_WEIGHT = 1.0

active_missions = {}
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL", 30))
MAX_DELIVERY_DISTANCE_KM = 50
EARTH_RADIUS_KM = 6371.0


def haversine(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Scenario 2: Drone Dispatch Orchestration
# ---------------------------------------------------------------------------

def dispatch_order(order_data):
    """Full dispatch orchestration triggered by order.confirmed AMQP message."""
    order_id = order_data.get("order_id")
    hospital_id = order_data.get("hospital_id")
    item_id = order_data.get("item_id", "")
    quantity = order_data.get("quantity", 1)
    urgency = order_data.get("urgency_level", "NORMAL")
    customer_address = order_data.get("customer_address", "")

    print(f"  [DISPATCH] Starting dispatch for {order_id} (hospital={hospital_id}, urgency={urgency})")

    # Step 2a: Resolve hospital coordinates
    hospital_coords = None
    errors = []

    try:
        resp = http_requests.get(f"{HOSPITAL_URL}/hospital/{hospital_id}/location", timeout=10)
        data = resp.json()
        hospital_coords = data.get("hospital_coords")
        print(f"  [DISPATCH] Hospital coords: {hospital_coords}")
    except Exception as e:
        errors.append(f"Hospital service: {e}")

    # Step 2b: Use customer_coords from order message if available, else geocode
    customer_coords = order_data.get("customer_coords")
    if customer_coords:
        print(f"  [DISPATCH] Customer coords from order message: {customer_coords}")
    else:
        try:
            resp = http_requests.get(
                f"{GEOLOCATION_URL}/maps/api/geocode/json",
                params={"address": customer_address, "key": GOOGLE_MAPS_API_KEY, "region": "sg"},
                timeout=10,
            )
            geo_data = resp.json()
            customer_coords = geo_data.get("customer_coords")
            print(f"  [DISPATCH] Customer coords from geolocation: {customer_coords} (source: {geo_data.get('source')})")
        except Exception as e:
            errors.append(f"Geolocation service: {e}")

    if errors or not hospital_coords or not customer_coords:
        print(f"  [DISPATCH] Coordinate resolution failed: {errors}")
        cancel_order(order_id, "COORD_RESOLUTION_FAILED")
        return

    delivery_distance = haversine(
        hospital_coords["lat"], hospital_coords["lng"],
        customer_coords["lat"], customer_coords["lng"],
    )
    if delivery_distance > MAX_DELIVERY_DISTANCE_KM:
        print(f"  [DISPATCH] Delivery distance {delivery_distance:.1f}km exceeds {MAX_DELIVERY_DISTANCE_KM}km limit for {order_id}")
        cancel_order(order_id, "OUT_OF_RANGE")
        return

    # Step 2c: Payload assembly
    unit_weight = ITEM_WEIGHTS.get(item_id, DEFAULT_ITEM_WEIGHT)
    payload_weight = unit_weight * quantity

    # Step 2d: Check drone availability
    try:
        resp = http_requests.get(
            f"{DRONE_MGMT_URL}/drones/available",
            params={"min_battery_pct": 30, "region": "CENTRAL"},
            timeout=10,
        )
        drone_data = resp.json()
        available_drones = drone_data.get("available_drones", [])
    except Exception as e:
        print(f"  [DISPATCH] Drone management unavailable: {e}")
        cancel_order(order_id, "DRONE_SERVICE_UNAVAILABLE")
        return

    if not available_drones:
        print(f"  [DISPATCH] No drones available for {order_id}")
        cancel_order(order_id, "NO_DRONES_AVAILABLE")
        return

    # Step 3: Weather check at destination
    try:
        resp = http_requests.get(
            f"{WEATHER_URL}/weather/check",
            params={"lat": customer_coords["lat"], "lng": customer_coords["lng"]},
            timeout=10,
        )
        weather_data = resp.json()
    except Exception as e:
        print(f"  [DISPATCH] Weather service unavailable: {e}")
        cancel_order(order_id, "WEATHER_SERVICE_UNAVAILABLE")
        return

    if weather_data.get("status") == "UNSAFE":
        print(f"  [DISPATCH] Unsafe weather for {order_id}: {weather_data.get('reasons')}")
        cancel_order(order_id, "UNSAFE_WEATHER")
        return

    # Step 4-5: Route planning
    route_payload = {
        "hospital_coords": hospital_coords,
        "customer_coords": customer_coords,
        "payload_weight": payload_weight,
        "available_drones": [
            {
                "drone_id": d["drone_id"],
                "coords": d["coords"],
                "battery": d["battery_pct"],
            }
            for d in available_drones
        ],
    }

    try:
        resp = http_requests.post(f"{ROUTE_URL}/route/plan", json=route_payload, timeout=15)
        route_data = resp.json()
    except Exception as e:
        print(f"  [DISPATCH] Route planning failed: {e}")
        cancel_order(order_id, "ROUTE_PLANNING_FAILED")
        return

    if route_data.get("status") != "ROUTE_CONFIRMED":
        detail_msg = route_data.get("message", "No viable route found for available drones.")
        print(f"  [DISPATCH] No viable route for {order_id}: {detail_msg}")
        cancel_order(order_id, "NO_VIABLE_ROUTE", detail_message=detail_msg)
        return

    selected_drone = route_data.get("selected_drone")
    eta_minutes = route_data.get("eta_minutes")

    # Step 6: Update drone status to IN_FLIGHT
    try:
        http_requests.patch(
            f"{DRONE_MGMT_URL}/drones/{selected_drone}/status",
            json={"status": "IN_FLIGHT"},
            timeout=10,
        )
    except Exception as e:
        print(f"  [DISPATCH] Warning: could not update drone status: {e}")

    # Step 7: Confirm dispatch with Order Service
    try:
        http_requests.post(
            f"{ORDER_URL}/dispatch/confirm",
            json={
                "order_id": order_id,
                "drone_id": selected_drone,
                "eta_minutes": eta_minutes,
                "status": "DISPATCHED",
            },
            timeout=10,
        )
    except Exception as e:
        print(f"  [DISPATCH] Warning: could not confirm with order service: {e}")

    print(f"  [DISPATCH] Order {order_id} dispatched: drone={selected_drone}, ETA={eta_minutes}min")

    # Register active mission for Scenario 3 polling
    active_missions[order_id] = {
        "order_id": order_id,
        "drone_id": selected_drone,
        "hospital_coords": hospital_coords,
        "customer_coords": customer_coords,
        "current_coords": hospital_coords.copy(),
        "dispatch_status": "IN_FLIGHT",
        "eta_minutes": eta_minutes,
        "payload_weight": payload_weight,
    }


CANCEL_MESSAGES = {
    "COORD_RESOLUTION_FAILED": "Could not resolve hospital or delivery coordinates. Please try again.",
    "OUT_OF_RANGE": "Delivery address is too far from the nearest hospital (exceeds 50km limit).",
    "NO_DRONES_AVAILABLE": "No operational drones are currently available. Please try again shortly.",
    "DRONE_SERVICE_UNAVAILABLE": "Drone management system is temporarily offline.",
    "WEATHER_SERVICE_UNAVAILABLE": "Weather monitoring system is temporarily offline.",
    "UNSAFE_WEATHER": "Current weather conditions are unsafe for drone flight at the delivery location.",
    "ROUTE_PLANNING_FAILED": "Route planning system is temporarily offline.",
}


def cancel_order(order_id, reason, detail_message=None):
    """Compensating action: cancel order via Order Service."""
    message = detail_message or CANCEL_MESSAGES.get(reason, f"Dispatch failed: {reason}")
    try:
        http_requests.post(
            f"{ORDER_URL}/order/{order_id}/cancel",
            json={"reason": reason, "status": "CANCELLED", "message": message},
            timeout=10,
        )
        print(f"  [DISPATCH] Cancelled order {order_id}: {reason} — {message}")
    except Exception as e:
        print(f"  [DISPATCH] Warning: could not cancel order {order_id}: {e}")


# ---------------------------------------------------------------------------
# Scenario 3: Mid-Flight Weather Polling & Rerouting
# ---------------------------------------------------------------------------

def poll_active_missions():
    """Background thread that polls weather for all active in-flight missions."""
    while True:
        time.sleep(POLL_INTERVAL_SECONDS)

        for order_id, mission in list(active_missions.items()):
            if mission["dispatch_status"] not in ("IN_FLIGHT", "REROUTED_IN_FLIGHT"):
                continue

            print(f"  [POLL] Checking weather for mission {order_id} (drone {mission['drone_id']})")

            try:
                resp = http_requests.post(
                    f"{WEATHER_URL}/weather/live",
                    json={
                        "order_id": order_id,
                        "drone_id": mission["drone_id"],
                        "current_coords": mission["current_coords"],
                        "destination_coords": mission["customer_coords"],
                    },
                    timeout=15,
                )
                weather_data = resp.json()
            except Exception as e:
                print(f"  [POLL] Weather check failed for {order_id}: {e}")
                continue

            if weather_data.get("status") != "UNSAFE":
                continue

            print(f"  [POLL] UNSAFE weather detected for {order_id}: {weather_data.get('reason')}")
            hazard_zone = weather_data.get("hazard_zone", {})

            # Scenario 3.1/3.2: Attempt reroute
            try:
                resp = http_requests.post(
                    f"{ROUTE_URL}/route/reroute",
                    json={
                        "order_id": order_id,
                        "drone_id": mission["drone_id"],
                        "current_coords": mission["current_coords"],
                        "destination_coords": mission["customer_coords"],
                        "hazard_zone": hazard_zone,
                        "avoid_conditions": weather_data.get("reason", []),
                        "max_detour_minutes": 10,
                    },
                    timeout=15,
                )
                reroute_data = resp.json()
            except Exception as e:
                print(f"  [POLL] Reroute request failed for {order_id}: {e}")
                handle_mission_abort(order_id, mission)
                continue

            if resp.status_code == 409 or reroute_data.get("status") == "NO_VIABLE_ROUTE":
                # Scenario 3.2: No viable route — abort mission
                print(f"  [POLL] No viable reroute for {order_id}. Aborting mission.")
                handle_mission_abort(order_id, mission)
            else:
                # Scenario 3.1: Successful reroute
                print(f"  [POLL] Reroute found for {order_id}: {reroute_data.get('route_id')}")
                mission["dispatch_status"] = "REROUTED_IN_FLIGHT"
                mission["route_id"] = reroute_data.get("route_id")
                mission["updated_eta"] = reroute_data.get("updated_eta")

                try:
                    http_requests.post(
                        f"{ORDER_URL}/dispatch/update",
                        json={
                            "order_id": order_id,
                            "drone_id": mission["drone_id"],
                            "dispatch_status": "REROUTED_IN_FLIGHT",
                            "route_id": reroute_data.get("route_id"),
                            "updated_eta": reroute_data.get("updated_eta"),
                        },
                        timeout=10,
                    )
                except Exception as e:
                    print(f"  [POLL] Warning: could not update order service: {e}")


def handle_mission_abort(order_id, mission):
    """Scenario 3.2: Abort mission, return drone, trigger compensating transactions."""
    mission["dispatch_status"] = "ABORTED_WEATHER"

    # Return drone to operational
    try:
        http_requests.patch(
            f"{DRONE_MGMT_URL}/drones/{mission['drone_id']}/status",
            json={"status": "RETURNING", "lat": mission["current_coords"]["lat"],
                  "lng": mission["current_coords"]["lng"]},
            timeout=10,
        )
    except Exception as e:
        print(f"  [ABORT] Warning: could not update drone status: {e}")

    # Notify Order Service of failure
    try:
        http_requests.post(
            f"{ORDER_URL}/dispatch/failure",
            json={
                "order_id": order_id,
                "drone_id": mission["drone_id"],
                "failure_code": "WEATHER_NO_ROUTE",
                "dispatch_status": "ABORTED_WEATHER",
                "recovery_action": "RETURN_TO_ORIGIN",
            },
            timeout=10,
        )
    except Exception as e:
        print(f"  [ABORT] Warning: could not notify order service: {e}")

    del active_missions[order_id]
    print(f"  [ABORT] Mission {order_id} aborted. Drone {mission['drone_id']} returning to origin.")


# ---------------------------------------------------------------------------
# AMQP Consumer: order.confirmed
# ---------------------------------------------------------------------------

def on_order_confirmed(channel, method, properties, body):
    """Callback for AMQP messages on orders/order.confirmed."""
    try:
        order_data = json.loads(body)
        print(f"  [AMQP] Received order.confirmed: {order_data.get('order_id')}")
        dispatch_thread = threading.Thread(target=dispatch_order, args=(order_data,))
        dispatch_thread.start()
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"  [AMQP ERROR] {str(e)}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def start_consumer():
    """Start the AMQP consumer for order.confirmed events."""
    print(f"  [AMQP] Starting consumer thread...")
    connection, channel = amqp_setup.get_connection()

    queue_name = "dispatch_queue"
    print(f"  [AMQP] Declaring queue: {queue_name} (durable=True)")
    channel.queue_declare(queue=queue_name, durable=True)

    routing_key = "order.confirmed"
    print(f"  [AMQP] Binding queue '{queue_name}' to exchange 'orders' with routing key '{routing_key}'")
    channel.queue_bind(exchange="orders", queue=queue_name, routing_key=routing_key)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=queue_name, on_message_callback=on_order_confirmed)

    print(f"  [AMQP] Listening for order.confirmed events on queue '{queue_name}'...")
    channel.start_consuming()


# ---------------------------------------------------------------------------
# Flask endpoints
# ---------------------------------------------------------------------------

@app.route("/dispatch/missions", methods=["GET"])
def list_missions():
    return jsonify({"active_missions": list(active_missions.values())})


@app.route("/dispatch/missions/<order_id>", methods=["GET"])
def get_mission(order_id):
    mission = active_missions.get(order_id)
    if not mission:
        return jsonify({"error": "Mission not found", "order_id": order_id}), 404
    return jsonify(mission)


@app.route("/dispatch/simulate/weather", methods=["POST"])
def simulate_weather_poll():
    """Debug endpoint: manually trigger weather poll for a specific mission."""
    data = request.get_json()
    order_id = data.get("order_id")
    mission = active_missions.get(order_id)
    if not mission:
        return jsonify({"error": "Mission not found", "order_id": order_id}), 404

    if "current_coords" in data:
        mission["current_coords"] = data["current_coords"]

    threading.Thread(target=_run_single_poll, args=(order_id, mission)).start()
    return jsonify({"status": "POLL_TRIGGERED", "order_id": order_id})


def _run_single_poll(order_id, mission):
    """Run a single weather poll for a specific mission."""
    try:
        resp = http_requests.post(
            f"{WEATHER_URL}/weather/live",
            json={
                "order_id": order_id,
                "drone_id": mission["drone_id"],
                "current_coords": mission["current_coords"],
                "destination_coords": mission["customer_coords"],
            },
            timeout=15,
        )
        weather_data = resp.json()
    except Exception as e:
        print(f"  [SIM_POLL] Weather check failed: {e}")
        return

    if weather_data.get("status") != "UNSAFE":
        print(f"  [SIM_POLL] Weather is SAFE for {order_id}")
        return

    hazard_zone = weather_data.get("hazard_zone", {})
    try:
        resp = http_requests.post(
            f"{ROUTE_URL}/route/reroute",
            json={
                "order_id": order_id,
                "drone_id": mission["drone_id"],
                "current_coords": mission["current_coords"],
                "destination_coords": mission["customer_coords"],
                "hazard_zone": hazard_zone,
                "avoid_conditions": weather_data.get("reason", []),
                "max_detour_minutes": 10,
            },
            timeout=15,
        )
        reroute_data = resp.json()
    except Exception as e:
        print(f"  [SIM_POLL] Reroute request failed: {e}")
        handle_mission_abort(order_id, mission)
        return

    if resp.status_code == 409 or reroute_data.get("status") == "NO_VIABLE_ROUTE":
        handle_mission_abort(order_id, mission)
    else:
        mission["dispatch_status"] = "REROUTED_IN_FLIGHT"
        mission["route_id"] = reroute_data.get("route_id")
        mission["updated_eta"] = reroute_data.get("updated_eta")
        try:
            http_requests.post(
                f"{ORDER_URL}/dispatch/update",
                json={
                    "order_id": order_id,
                    "drone_id": mission["drone_id"],
                    "dispatch_status": "REROUTED_IN_FLIGHT",
                    "route_id": reroute_data.get("route_id"),
                    "updated_eta": reroute_data.get("updated_eta"),
                },
                timeout=10,
            )
        except Exception as e:
            print(f"  [SIM_POLL] Warning: could not update order service: {e}")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "drone-dispatch", "active_missions": len(active_missions)})


if __name__ == "__main__":
    consumer_thread = threading.Thread(target=start_consumer, daemon=True)
    consumer_thread.start()

    poller_thread = threading.Thread(target=poll_active_missions, daemon=True)
    poller_thread.start()

    print("  Drone Dispatch Service running on port 5002")
    app.run(host="0.0.0.0", port=5002, debug=True)
