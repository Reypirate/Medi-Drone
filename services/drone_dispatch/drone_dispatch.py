# ═══════════════════════════════════════════════════════════════════════════════
# DRONE DISPATCH SERVICE
# ═══════════════════════════════════════════════════════════════════════════════
#
# ⚠️  DOCUMENTATION REMINDER ⚠️
# When modifying this file, please run: python scripts/sync_docs.py
# to check if documentation (README.md, docs/system-flow.md) needs updates.
#
# Key areas that require documentation updates:
# - New endpoints: Add to API endpoints section
# - New mission types: Add to Mission Types section
# - Changed constants (battery threshold, poll interval): Update values
# - New features: Describe in appropriate scenario sections
#
# ═══════════════════════════════════════════════════════════════════════════════

import os
import json
import time
import math
import threading
import sys
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

# Battery consumption: ~1.8% per km at base drone weight (matches route_planning BASE_CONSUMPTION_PER_KM)
BATTERY_CONSUMPTION_PER_KM = 1.8
LOW_BATTERY_THRESHOLD = 40  # Percentage below which drones auto-charge

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
DRONE_SPEED_KMH = 36.0  # Drone cruise speed in km/h

# Global lock for drone reservation to prevent race conditions
drone_reservation_lock = threading.Lock()
reserved_drones = set()  # Track drones that have been reserved but not yet in flight
order_drone_reservations = {}  # Map order_id -> drone_id for cleanup before active_missions is populated


def haversine(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def get_depot_location():
    """Fetch central charging depot location from drone-management service."""
    try:
        resp = http_requests.get(f"{DRONE_MGMT_URL}/depot", timeout=10)
        data = resp.json()
        return data.get("location", {})
    except Exception as e:
        print(f"  [DEPOT] Warning: could not fetch depot location: {e}")
        return {"lat": 1.3644, "lng": 103.8190}  # Default to Singapore central


def calculate_battery_consumption(distance_km):
    """Calculate battery consumption based on distance traveled."""
    return int(distance_km * BATTERY_CONSUMPTION_PER_KM)


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

    # Step 2d: Check drone availability (with race condition protection)
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

    # Filter out drones that are already reserved by other in-flight dispatches
    with drone_reservation_lock:
        available_drones = [d for d in available_drones if d["drone_id"] not in reserved_drones]

    if not available_drones:
        print(f"  [DISPATCH] No drones available for {order_id} (all reserved or unavailable)")
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

    # Step 5.5: Atomically reserve the selected drone to prevent race conditions
    with drone_reservation_lock:
        # Check if the drone was reserved while we were doing route planning
        if selected_drone in reserved_drones:
            print(f"  [DISPATCH] Drone {selected_drone} was just reserved by another order. Cancelling {order_id}")
            cancel_order(order_id, "NO_DRONES_AVAILABLE", "All drones have been assigned to other orders.")
            return

        # Reserve the drone and track order->drone mapping for cleanup
        reserved_drones.add(selected_drone)
        order_drone_reservations[order_id] = selected_drone
        print(f"  [DISPATCH] Reserved drone {selected_drone} for order {order_id}")

    # Get drone start coordinates for phase 1 (needed for ETA calculation and confirm call)
    drone_start_coords = None
    for d in available_drones:
        if d["drone_id"] == selected_drone:
            drone_start_coords = {"lat": d["coords"]["lat"], "lng": d["coords"]["lng"]}
            break

    if not drone_start_coords:
        drone_start_coords = hospital_coords  # Fallback to hospital if not found

    # Calculate Phase 1 ETA: drone start → hospital (needed for confirm call)
    distance_to_hospital = haversine(
        drone_start_coords["lat"], drone_start_coords["lng"],
        hospital_coords["lat"], hospital_coords["lng"]
    )
    hospital_eta = round((distance_to_hospital / DRONE_SPEED_KMH) * 60)

    # Step 6: Update drone status to IN_FLIGHT with position tracking
    try:
        http_requests.patch(
            f"{DRONE_MGMT_URL}/drones/{selected_drone}/status",
            json={
                "status": "IN_FLIGHT",
                "current_lat": hospital_coords["lat"],
                "current_lng": hospital_coords["lng"],
                "target_lat": customer_coords["lat"],
                "target_lng": customer_coords["lng"],
            },
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
                "eta_minutes": hospital_eta,
                "status": "TO_HOSPITAL",
                "mission_phase": "TO_HOSPITAL",  # Explicitly set mission phase
            },
            timeout=10,
        )
    except Exception as e:
        print(f"  [DISPATCH] Warning: could not confirm with order service: {e}")

    print(f"  [DISPATCH] Order {order_id} dispatched: drone={selected_drone}, Hospital ETA={hospital_eta}min, Customer ETA={eta_minutes}min")

    # Initialize the active_missions entry with full mission details
    # MISSION PHASES:
    # 1. TO_HOSPITAL: Drone flying from its current location to hospital to pick up supplies
    # 2. TO_CUSTOMER: Drone flying from hospital to customer to deliver supplies
    active_missions[order_id] = {
        "order_id": order_id,
        "drone_id": selected_drone,
        "drone_start_coords": drone_start_coords,
        "hospital_coords": hospital_coords,
        "customer_coords": customer_coords,
        "current_coords": drone_start_coords.copy(),  # Start at actual drone position
        "dispatch_status": "TO_HOSPITAL",  # Start with phase 1: drone → hospital
        "mission_phase": "TO_HOSPITAL",
        "eta_minutes": hospital_eta,  # Start countdown with hospital ETA
        "initial_eta": hospital_eta + eta_minutes,  # Total mission time
        "payload_weight": payload_weight,
        "hospital_eta_minutes": hospital_eta,  # ETA to reach hospital
        "customer_eta_minutes": eta_minutes,  # ETA from hospital to customer
    }

    # Drone is now in active_missions, so remove from reservation tracking
    with drone_reservation_lock:
        reserved_drones.discard(selected_drone)
        order_drone_reservations.pop(order_id, None)
    print(f"  [MISSIONS] Mission initialized: {order_id} | Phase: TO_HOSPITAL | Hospital ETA: {hospital_eta}min, Customer ETA: {eta_minutes}min | Total: {hospital_eta + eta_minutes}min")


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
    """Compensating action: cancel order via Order Service and cleanup reserved drone."""
    message = detail_message or CANCEL_MESSAGES.get(reason, f"Dispatch failed: {reason}")

    # Clean up reserved drone if it was reserved
    drone_id = None
    if order_id in active_missions:
        drone_id = active_missions[order_id].get("drone_id")
        print(f"  [DISPATCH] Releasing drone {drone_id} for cancelled order {order_id}")
        del active_missions[order_id]

    # Also check order_drone_reservations for drones reserved but not yet in active_missions
    with drone_reservation_lock:
        if not drone_id:
            drone_id = order_drone_reservations.pop(order_id, None)
        else:
            order_drone_reservations.pop(order_id, None)
        if drone_id and drone_id in reserved_drones:
            reserved_drones.remove(drone_id)
            print(f"  [DISPATCH] Removed {drone_id} from reserved_drones")

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

def check_and_send_low_battery_drones_to_charging():
    """Check for drones with low battery and send them to depot for charging."""
    try:
        resp = http_requests.get(f"{DRONE_MGMT_URL}/drones", timeout=10)
        drones = resp.json()
    except Exception as e:
        print(f"  [BATTERY] Warning: could not fetch drones: {e}")
        return

    depot_coords = get_depot_location()
    low_battery_drones = []

    for drone in drones:
        # Skip drones that are already charging, in flight, or being processed
        if drone.get("status") in ("CHARGING", "IN_FLIGHT", "RETURNING_TO_DEPOT", "FAULTY"):
            continue

        # Check if battery is below threshold
        if drone.get("battery", 100) < LOW_BATTERY_THRESHOLD:
            low_battery_drones.append(drone)

    if not low_battery_drones:
        return

    print(f"  [BATTERY] Found {len(low_battery_drones)} drone(s) below {LOW_BATTERY_THRESHOLD}% battery", flush=True)

    for drone in low_battery_drones:
        drone_id = drone.get("drone_id")
        current_battery = drone.get("battery", 0)

        # Skip if a charging mission already exists for this drone
        if f"{drone_id}_charging" in active_missions:
            print(f"  [BATTERY] Drone {drone_id} already has a charging mission, skipping")
            continue

        try:
            # Update drone to CHARGING status at depot
            http_requests.patch(
                f"{DRONE_MGMT_URL}/drones/{drone_id}/status",
                json={
                    "status": "CHARGING",
                    "lat": depot_coords["lat"],
                    "lng": depot_coords["lng"],
                    "current_lat": depot_coords["lat"],
                    "current_lng": depot_coords["lng"],
                    "target_lat": depot_coords["lat"],
                    "target_lng": depot_coords["lng"],
                },
                timeout=10,
            )
            print(f"  [BATTERY] Drone {drone_id} ({current_battery}%) sent to depot for charging", flush=True)

            # Add to active_missions for charging cycle tracking
            charging_mission_id = f"{drone_id}_charging"
            active_missions[charging_mission_id] = {
                "order_id": charging_mission_id,
                "drone_id": drone_id,
                "mission_type": "LOW_BATTERY_CHARGING",
                "destination_coords": depot_coords,
                "dispatch_status": "CHARGING",
                "charging_cycles": 0,
                "original_battery": current_battery,
            }
            print(f"  [BATTERY] Added charging mission for {drone_id}")

        except Exception as e:
            print(f"  [BATTERY] Warning: could not send drone {drone_id} to charging: {e}")


def poll_active_missions():
    """Background thread that polls weather and simulates drone movement for active missions."""
    print(f"  [MISSIONS] Polling thread started | Active missions: {len(active_missions)}")
    while True:
        time.sleep(POLL_INTERVAL_SECONDS)

        # First, check for low battery drones and send them to charging
        check_and_send_low_battery_drones_to_charging()

        print(f"  [MISSIONS] Polling {len(active_missions)} active missions...", flush=True)

        for order_id, mission in list(active_missions.items()):
            # Handle return-to-depot missions
            if mission.get("mission_type") == "RETURN_TO_DEPOT":
                # Simulate return trip
                if mission.get("return_cycles", 0) >= 1:
                    # Drone has arrived at depot - start charging
                    if mission.get("charging", False):
                        # Already charging - check if charging complete
                        if mission.get("charging_cycles", 0) >= 2:
                            # Charging complete - make drone available again
                            try:
                                http_requests.patch(
                                    f"{DRONE_MGMT_URL}/drones/{mission['drone_id']}/status",
                                    json={"status": "AVAILABLE", "battery": 100, "lat": mission["destination_coords"]["lat"],
                                          "lng": mission["destination_coords"]["lng"]},
                                    timeout=10,
                                )
                                print(f"  [CHARGING] Drone {mission['drone_id']} fully charged. Now AVAILABLE.")
                            except Exception as e:
                                print(f"  [CHARGING] Warning: could not update drone status: {e}")
                            del active_missions[order_id]
                            print(f"  [MISSIONS] Charging mission completed: {order_id} | Active missions: {len(active_missions)}")
                        else:
                            mission["charging_cycles"] = mission.get("charging_cycles", 0) + 1
                            print(f"  [CHARGING] Drone {mission['drone_id']} charging... cycle {mission.get('charging_cycles', 0)}/2")
                    else:
                        # Start charging
                        try:
                            http_requests.patch(
                                f"{DRONE_MGMT_URL}/drones/{mission['drone_id']}/status",
                                json={"status": "CHARGING", "lat": mission["destination_coords"]["lat"],
                                      "lng": mission["destination_coords"]["lng"]},
                                timeout=10,
                            )
                            print(f"  [RETURN] Drone {mission['drone_id']} arrived at depot. Now CHARGING.")
                            mission["charging"] = True
                        except Exception as e:
                            print(f"  [RETURN] Warning: could not update drone status: {e}")
                            del active_missions[order_id]
                else:
                    mission["return_cycles"] = mission.get("return_cycles", 0) + 1
                    print(f"  [RETURN] Drone {mission['drone_id']} returning to depot... cycle {mission['return_cycles']}/1")
                continue

            # Handle low battery charging missions (drone already at depot)
            if mission.get("mission_type") == "LOW_BATTERY_CHARGING":
                if mission.get("charging_cycles", 0) >= 2:
                    # Charging complete - make drone available again
                    try:
                        http_requests.patch(
                            f"{DRONE_MGMT_URL}/drones/{mission['drone_id']}/status",
                            json={
                                "status": "AVAILABLE",
                                "battery": 100,
                                "lat": mission["destination_coords"]["lat"],
                                "lng": mission["destination_coords"]["lng"]
                            },
                            timeout=10,
                        )
                        print(f"  [CHARGING] Drone {mission['drone_id']} fully charged from low battery ({mission.get('original_battery', 0)}%). Now AVAILABLE.")
                    except Exception as e:
                        print(f"  [CHARGING] Warning: could not update drone status: {e}")
                    del active_missions[order_id]
                    print(f"  [MISSIONS] Low battery charging completed: {order_id} | Active missions: {len(active_missions)}")
                else:
                    mission["charging_cycles"] = mission.get("charging_cycles", 0) + 1
                    print(f"  [CHARGING] Drone {mission['drone_id']} charging from low battery... cycle {mission.get('charging_cycles', 0)}/2")
                continue

            # Skip missions that are not in active delivery phases
            if mission["dispatch_status"] not in ("TO_HOSPITAL", "TO_CUSTOMER", "IN_FLIGHT", "REROUTED_IN_FLIGHT"):
                continue

            # MISSION PHASE HANDLING
            mission_phase = mission.get("mission_phase", mission["dispatch_status"])

            # Phase 1: Drone flying to hospital to pick up supplies
            if mission_phase == "TO_HOSPITAL" or mission["dispatch_status"] == "TO_HOSPITAL":
                hospital_eta = mission.get("hospital_eta_minutes", 0)
                if hospital_eta <= 0:
                    # Reached hospital - transition to Phase 2
                    print(f"  [HOSPITAL] {order_id}: Drone {mission['drone_id']} arrived at hospital. Picking up supplies...")
                    mission["mission_phase"] = "TO_CUSTOMER"
                    mission["dispatch_status"] = "TO_CUSTOMER"
                    mission["current_coords"] = mission["hospital_coords"].copy()
                    mission["eta_minutes"] = mission.get("customer_eta_minutes", 0)
                    mission["initial_eta"] = mission.get("customer_eta_minutes", 0)

                    # Update order service with new phase
                    try:
                        http_requests.post(
                            f"{ORDER_URL}/dispatch/update",
                            json={
                                "order_id": order_id,
                                "drone_id": mission["drone_id"],
                                "dispatch_status": "TO_CUSTOMER",
                                "mission_phase": "TO_CUSTOMER",
                                "eta_minutes": mission["eta_minutes"],
                            },
                            timeout=10,
                        )
                    except Exception as e:
                        print(f"  [HOSPITAL] Warning: could not update order service phase: {e}")

                    # Update drone position to hospital
                    try:
                        http_requests.patch(
                            f"{DRONE_MGMT_URL}/drones/{mission['drone_id']}/status",
                            json={
                                "status": "TO_CUSTOMER",
                                "lat": mission["hospital_coords"]["lat"],
                                "lng": mission["hospital_coords"]["lng"],
                                "current_lat": mission["hospital_coords"]["lat"],
                                "current_lng": mission["hospital_coords"]["lng"],
                                "target_lat": mission["customer_coords"]["lat"],
                                "target_lng": mission["customer_coords"]["lng"],
                            },
                            timeout=10,
                        )
                    except Exception as e:
                        print(f"  [HOSPITAL] Warning: could not update drone status: {e}")
                    continue

                # Countdown to hospital
                old_eta = mission.get("eta_minutes", 0)
                mission["eta_minutes"] = max(0, old_eta - (POLL_INTERVAL_SECONDS / 60))
                print(f"  [TO_HOSPITAL] {order_id}: ETA to hospital {old_eta:.1f} → {mission['eta_minutes']:.1f} min")

                # Update drone position (drone → hospital)
                drone_start = mission.get("drone_start_coords", mission["current_coords"])
                hospital = mission["hospital_coords"]
                progress = 1 - (mission["eta_minutes"] / max(mission.get("hospital_eta_minutes", mission["eta_minutes"] + 1), 1))
                new_lat = drone_start["lat"] + progress * (hospital["lat"] - drone_start["lat"])
                new_lng = drone_start["lng"] + progress * (hospital["lng"] - drone_start["lng"])
                mission["current_coords"] = {"lat": new_lat, "lng": new_lng}

                # Update position in drone management
                try:
                    http_requests.patch(
                        f"{DRONE_MGMT_URL}/drones/{mission['drone_id']}/position",
                        json={"lat": new_lat, "lng": new_lng},
                        timeout=10,
                    )
                except Exception as e:
                    print(f"  [TO_HOSPITAL] Warning: could not update drone position: {e}")

                # Skip weather check during TO_HOSPITAL phase (no hazard concern)
                continue

            # Phase 2: Drone flying from hospital to customer (delivering supplies)
            if mission_phase == "TO_CUSTOMER" or mission["dispatch_status"] == "TO_CUSTOMER":
                # For backward compatibility with existing IN_FLIGHT status
                mission["dispatch_status"] = "IN_FLIGHT"

            # Simulate drone movement and battery consumption
            current_eta = mission.get("eta_minutes", 0)
            if current_eta <= 0:
                # Delivery complete!
                print(f"  [DELIVERY] ETA reached zero for {order_id}. Completing delivery...")
                handle_delivery_completion(order_id, mission)
                continue

            # Decrease ETA by poll interval (30 seconds = 0.5 minutes)
            old_eta = current_eta
            mission["eta_minutes"] = max(0, current_eta - (POLL_INTERVAL_SECONDS / 60))
            print(f"  [POLL] {order_id}: ETA {old_eta:.1f} → {mission['eta_minutes']:.1f} min (decremented by {POLL_INTERVAL_SECONDS/60:.1f} min)")

            # Update order service with current ETA
            try:
                http_requests.post(
                    f"{ORDER_URL}/dispatch/update",
                    json={
                        "order_id": order_id,
                        "drone_id": mission["drone_id"],
                        "dispatch_status": mission["dispatch_status"],
                        "eta_minutes": mission["eta_minutes"],
                    },
                    timeout=10,
                )
            except Exception as e:
                print(f"  [POLL] Warning: could not update order service ETA: {e}")

            # Update drone position (simulate movement towards destination)
            if "current_coords" in mission and "customer_coords" in mission:
                progress_fraction = 1 - (mission["eta_minutes"] / max(mission.get("initial_eta", mission["eta_minutes"] + 1), 1))
                new_lat = mission["hospital_coords"]["lat"] + progress_fraction * (
                    mission["customer_coords"]["lat"] - mission["hospital_coords"]["lat"]
                )
                new_lng = mission["hospital_coords"]["lng"] + progress_fraction * (
                    mission["customer_coords"]["lng"] - mission["hospital_coords"]["lng"]
                )
                mission["current_coords"] = {"lat": new_lat, "lng": new_lng}

                # Update position in drone management
                try:
                    http_requests.patch(
                        f"{DRONE_MGMT_URL}/drones/{mission['drone_id']}/position",
                        json={"lat": new_lat, "lng": new_lng},
                        timeout=10,
                    )
                except Exception as e:
                    print(f"  [POLL] Warning: could not update drone position: {e}")

            print(f"  [POLL] Checking weather for mission {order_id} (phase: {mission.get('mission_phase', 'UNKNOWN')}, drone {mission['drone_id']}, ETA: {mission['eta_minutes']:.1f}min)")

            # Determine destination based on mission phase
            mission_phase = mission.get("mission_phase", mission["dispatch_status"])
            if mission_phase == "TO_HOSPITAL":
                destination_coords = mission["hospital_coords"]
                destination_name = "hospital"
            elif mission_phase == "TO_CUSTOMER" or mission_phase == "IN_FLIGHT" or mission_phase == "REROUTED_IN_FLIGHT":
                destination_coords = mission["customer_coords"]
                destination_name = "customer"
            else:
                continue  # Skip weather check for other phases

            try:
                resp = http_requests.post(
                    f"{WEATHER_URL}/weather/live",
                    json={
                        "order_id": order_id,
                        "drone_id": mission["drone_id"],
                        "current_coords": mission["current_coords"],
                        "destination_coords": destination_coords,
                    },
                    timeout=15,
                )
                weather_data = resp.json()
            except Exception as e:
                print(f"  [POLL] Weather check failed for {order_id}: {e}")
                continue

            if weather_data.get("status") != "UNSAFE":
                continue

            print(f"  [POLL] UNSAFE weather detected for {order_id} (phase: {mission_phase}): {weather_data.get('reason')}")
            hazard_zone = weather_data.get("hazard_zone", {})

            # Scenario 3.1/3.2: Attempt reroute
            try:
                resp = http_requests.post(
                    f"{ROUTE_URL}/route/reroute",
                    json={
                        "order_id": order_id,
                        "drone_id": mission["drone_id"],
                        "current_coords": mission["current_coords"],
                        "destination_coords": destination_coords,
                        "hazard_zone": hazard_zone,
                        "avoid_conditions": weather_data.get("reason", []),
                        "max_detour_minutes": 10,
                        "mission_phase": mission_phase,  # Pass mission phase to route planning
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
                print(f"  [REROUTE] Reroute found for {order_id}: {reroute_data.get('route_id')}")

                # Extract reroute details for comprehensive logging
                original_distance_km = reroute_data.get("original_distance_km", 0)
                new_distance_km = reroute_data.get("distance_km", 0)
                detour_percentage = reroute_data.get("detour_percentage", 0)
                waypoint_count = reroute_data.get("waypoint_count", 0)
                battery_impact_pct = reroute_data.get("additional_battery_consumption_pct", 0)
                route_summary = reroute_data.get("route_summary", "N/A")
                new_eta_minutes = reroute_data.get("eta_minutes", 0)

                # Enhanced logging with [REROUTE] prefix
                print(f"  [REROUTE] Distance: {original_distance_km:.2f}km → {new_distance_km:.2f}km (detour: +{detour_percentage:.1f}%)")
                print(f"  [REROUTE] Waypoints: {waypoint_count} | Battery impact: +{battery_impact_pct:.1f}%")
                print(f"  [REROUTE] Route summary: {route_summary}")
                print(f"  [REROUTE] New ETA: {new_eta_minutes:.1f} minutes")

                # Store comprehensive reroute details in mission object
                mission["dispatch_status"] = "REROUTED_IN_FLIGHT"
                mission["route_id"] = reroute_data.get("route_id")
                mission["updated_eta"] = reroute_data.get("updated_eta")
                # Store comprehensive reroute details in mission object
                mission["reroute_details"] = {
                    "original_distance_km": original_distance_km,
                    "new_distance_km": new_distance_km,
                    "detour_percentage": detour_percentage,
                    "waypoint_count": waypoint_count,
                    "battery_impact_pct": battery_impact_pct,
                    "route_summary": route_summary,
                    "new_eta_minutes": new_eta_minutes,
                }
                # Reset the countdown ETA to account for time already traveled + new route time
                # The route planning service returns ETA for remaining segment only, so we need to
                # add back the time already spent to get the correct total mission time
                old_initial_eta = mission.get("initial_eta", new_eta_minutes)
                old_eta_minutes = mission.get("eta_minutes", 0)
                time_already_spent = old_initial_eta - old_eta_minutes
                new_total_mission_time = time_already_spent + new_eta_minutes

                print(f"  [REROUTE] ETA Calculation:")
                print(f"  [REROUTE]   Old initial ETA: {old_initial_eta:.1f} min")
                print(f"  [REROUTE]   Old remaining ETA: {old_eta_minutes:.1f} min")
                print(f"  [REROUTE]   Time already spent: {time_already_spent:.1f} min")
                print(f"  [REROUTE]   New route ETA (remaining): {new_eta_minutes:.1f} min")
                print(f"  [REROUTE]   New total mission time: {new_total_mission_time:.1f} min")
                print(f"  [REROUTE]   ETA change: {old_eta_minutes:.1f} → {new_total_mission_time:.1f} min ({new_total_mission_time - old_eta_minutes:+.1f} min)")

                if reroute_data.get("eta_minutes"):
                    mission["eta_minutes"] = new_eta_minutes
                    mission["initial_eta"] = new_total_mission_time

                try:
                    http_requests.post(
                        f"{ORDER_URL}/dispatch/update",
                        json={
                            "order_id": order_id,
                            "drone_id": mission["drone_id"],
                            "dispatch_status": "REROUTED_IN_FLIGHT",
                            "mission_phase": mission.get("mission_phase", "TO_CUSTOMER"),  # Preserve current phase
                            "route_id": reroute_data.get("route_id"),
                            "updated_eta": reroute_data.get("updated_eta"),
                            "reroute_summary": route_summary,
                            "detour_percentage": detour_percentage,
                            "new_eta_minutes": new_eta_minutes,
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
            json={"status": "RETURNING_TO_DEPOT", "lat": mission["current_coords"]["lat"],
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
    print(f"  [MISSIONS] Mission aborted: {order_id} | Active missions: {len(active_missions)}")


def handle_delivery_completion(order_id, mission):
    """Handle successful delivery: complete order and return drone to depot."""
    print(f"  [DELIVERY] Order {order_id} delivered successfully. Processing completion...")

    # Get depot location
    depot_coords = get_depot_location()

    # Calculate battery consumed during ENTIRE mission (both phases)
    drone_start = mission.get("drone_start_coords", mission["hospital_coords"])
    hospital = mission["hospital_coords"]
    customer = mission["customer_coords"]

    # Phase 1: Drone start → Hospital (pickup)
    distance_to_hospital = haversine(
        drone_start["lat"], drone_start["lng"],
        hospital["lat"], hospital["lng"]
    )

    # Phase 2: Hospital → Customer (delivery)
    distance_hospital_to_customer = haversine(
        hospital["lat"], hospital["lng"],
        customer["lat"], customer["lng"]
    )

    # Total mission distance
    total_mission_distance = distance_to_hospital + distance_hospital_to_customer
    battery_consumed = calculate_battery_consumption(total_mission_distance)

    # Calculate distance to depot and additional battery needed
    distance_to_depot = haversine(
        mission["customer_coords"]["lat"], mission["customer_coords"]["lng"],
        depot_coords["lat"], depot_coords["lng"]
    )
    return_battery = calculate_battery_consumption(distance_to_depot)
    total_consumed = battery_consumed + return_battery

    # Get current drone battery
    try:
        resp = http_requests.get(f"{DRONE_MGMT_URL}/drones", timeout=10)
        drones_data = resp.json()
        drone = next((d for d in drones_data if d["drone_id"] == mission["drone_id"]), None)
        current_battery = drone.get("battery", 100) if drone else 100
        final_battery = max(10, current_battery - total_consumed)  # Minimum 10%
    except Exception as e:
        print(f"  [DELIVERY] Warning: could not fetch drone battery: {e}")
        final_battery = 50  # Conservative default

    # Update drone status to RETURNING_TO_DEPOT with reduced battery
    try:
        http_requests.patch(
            f"{DRONE_MGMT_URL}/drones/{mission['drone_id']}/status",
            json={
                "status": "RETURNING_TO_DEPOT",
                "battery": final_battery,
                "current_lat": mission["customer_coords"]["lat"],
                "current_lng": mission["customer_coords"]["lng"],
                "target_lat": depot_coords["lat"],
                "target_lng": depot_coords["lng"],
            },
            timeout=10,
        )
        print(f"  [DELIVERY] Drone {mission['drone_id']} returning to depot (battery: {final_battery}%)")
    except Exception as e:
        print(f"  [DELIVERY] Warning: could not update drone status: {e}")

    # Complete the order
    try:
        http_requests.post(
            f"{ORDER_URL}/dispatch/complete",
            json={
                "order_id": order_id,
                "drone_id": mission["drone_id"],
                "status": "DELIVERED",
            },
            timeout=10,
        )
        print(f"  [DELIVERY] Order {order_id} marked as DELIVERED")
    except Exception as e:
        print(f"  [DELIVERY] Warning: could not complete order: {e}")

    # Schedule charging at depot (after return trip)
    active_missions[f"{order_id}_return"] = {
        "order_id": f"{order_id}_return",
        "drone_id": mission["drone_id"],
        "mission_type": "RETURN_TO_DEPOT",
        "current_coords": mission["customer_coords"].copy(),
        "destination_coords": depot_coords,
        "dispatch_status": "RETURNING_TO_DEPOT",
        "eta_minutes": round((distance_to_depot / DRONE_SPEED_KMH) * 60),
    }
    print(f"  [MISSIONS] Return mission added: {order_id}_return | Active missions: {len(active_missions)}")

    # Remove original delivery mission
    del active_missions[order_id]
    print(f"  [MISSIONS] Delivery mission completed: {order_id} | Active missions: {len(active_missions)}")


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
        # Successful reroute - enhanced logging
        print(f"  [REROUTE] Reroute found for {order_id}: {reroute_data.get('route_id')}")

        # Extract reroute details for comprehensive logging
        original_distance_km = reroute_data.get("original_distance_km", 0)
        new_distance_km = reroute_data.get("distance_km", 0)
        detour_percentage = reroute_data.get("detour_percentage", 0)
        waypoint_count = reroute_data.get("waypoint_count", 0)
        battery_impact_pct = reroute_data.get("additional_battery_consumption_pct", 0)
        route_summary = reroute_data.get("route_summary", "N/A")
        new_eta_minutes = reroute_data.get("eta_minutes", 0)

        # Enhanced logging with [REROUTE] prefix
        print(f"  [REROUTE] Distance: {original_distance_km:.2f}km → {new_distance_km:.2f}km (detour: +{detour_percentage:.1f}%)")
        print(f"  [REROUTE] Waypoints: {waypoint_count} | Battery impact: +{battery_impact_pct:.1f}%")
        print(f"  [REROUTE] Route summary: {route_summary}")
        print(f"  [REROUTE] New ETA: {new_eta_minutes:.1f} minutes")

        # Store comprehensive reroute details in mission object
        mission["dispatch_status"] = "REROUTED_IN_FLIGHT"
        mission["route_id"] = reroute_data.get("route_id")
        mission["updated_eta"] = reroute_data.get("updated_eta")
        # Store comprehensive reroute details in mission object
        mission["reroute_details"] = {
            "original_distance_km": original_distance_km,
            "new_distance_km": new_distance_km,
            "detour_percentage": detour_percentage,
            "waypoint_count": waypoint_count,
            "battery_impact_pct": battery_impact_pct,
            "route_summary": route_summary,
            "new_eta_minutes": new_eta_minutes,
        }
        # Reset the countdown ETA to the rerouted distance's ETA
        if reroute_data.get("eta_minutes"):
            mission["eta_minutes"] = reroute_data["eta_minutes"]
            mission["initial_eta"] = reroute_data["eta_minutes"]
        try:
            http_requests.post(
                f"{ORDER_URL}/dispatch/update",
                json={
                    "order_id": order_id,
                    "drone_id": mission["drone_id"],
                    "dispatch_status": "REROUTED_IN_FLIGHT",
                    "mission_phase": mission.get("mission_phase", "TO_CUSTOMER"),  # Preserve current phase
                    "route_id": reroute_data.get("route_id"),
                    "updated_eta": reroute_data.get("updated_eta"),
                    "reroute_summary": route_summary,
                    "detour_percentage": detour_percentage,
                    "new_eta_minutes": new_eta_minutes,
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
    app.run(host="0.0.0.0", port=5002, debug=False)
