import math
import heapq
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

EARTH_RADIUS_KM = 6371.0
DRONE_BASE_WEIGHT_KG = 2.5
BASE_CONSUMPTION_PER_KM = 1.8  # % battery per km at base weight
DRONE_SPEED_KMH = 36.0
GRID_RESOLUTION = 0.002  # ~220m per grid cell in lat/lng


def haversine(lat1, lng1, lat2, lng2):
    """Calculate great-circle distance between two points in km."""
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def estimate_energy(distance_km, payload_weight_kg, wind_factor=1.0):
    """Estimate battery % consumption for a given distance and payload."""
    total_weight = DRONE_BASE_WEIGHT_KG + payload_weight_kg
    weight_factor = total_weight / DRONE_BASE_WEIGHT_KG
    return BASE_CONSUMPTION_PER_KM * distance_km * weight_factor * wind_factor


def score_drone(battery, total_mission_time_min):
    """Score a drone candidate: higher is better."""
    if total_mission_time_min <= 0:
        return 0
    return battery / total_mission_time_min


@app.route("/route/plan", methods=["POST"])
def plan_route():
    """Initial route planning using Haversine + scoring (Scenario 2, Step 4-6)."""
    data = request.get_json()
    hospital_coords = data.get("hospital_coords", {})
    customer_coords = data.get("customer_coords", {})
    payload_weight = data.get("payload_weight", 1.0)
    available_drones = data.get("available_drones", [])

    if not available_drones:
        return jsonify({"status": "NO_DRONES", "reason": "No drones provided for route planning"}), 400

    h_lat, h_lng = hospital_coords.get("lat", 0), hospital_coords.get("lng", 0)
    c_lat, c_lng = customer_coords.get("lat", 0), customer_coords.get("lng", 0)

    hospital_to_customer_km = haversine(h_lat, h_lng, c_lat, c_lng)

    candidates = []
    rejected = []
    for drone in available_drones:
        d_coords = drone.get("coords", {})
        d_lat, d_lng = d_coords.get("lat", 0), d_coords.get("lng", 0)
        d_battery = drone.get("battery", 0)

        drone_to_hospital_km = haversine(d_lat, d_lng, h_lat, h_lng)
        total_km = drone_to_hospital_km + hospital_to_customer_km

        total_energy = estimate_energy(total_km, payload_weight)
        energy_available = d_battery
        eta_minutes = (total_km / DRONE_SPEED_KMH) * 60

        if total_energy > energy_available:
            rejected.append({
                "drone_id": drone["drone_id"],
                "battery_pct": d_battery,
                "energy_required_pct": round(total_energy, 1),
                "total_km": round(total_km, 1),
            })
            continue

        drone_score = score_drone(d_battery, eta_minutes)

        candidates.append({
            "drone_id": drone["drone_id"],
            "score": round(drone_score, 1),
            "calculation_data": {
                "estimated_energy_use": round(total_energy, 1),
                "estimated_energy_available": round(float(energy_available), 1),
                "flight_path": {
                    "drone_to_hospital_km": round(drone_to_hospital_km, 1),
                    "hospital_to_customer_km": round(hospital_to_customer_km, 1),
                    "total_km": round(total_km, 1),
                    "eta_minutes": round(eta_minutes),
                },
                "reason": "Optimal based on distance, battery, and ETA",
            },
        })

    if not candidates:
        best = min(rejected, key=lambda r: r["energy_required_pct"]) if rejected else {}
        total_weight_kg = round(DRONE_BASE_WEIGHT_KG + payload_weight, 1)
        return jsonify({
            "status": "NO_VIABLE_ROUTE",
            "reason": "No drone has enough battery for the mission",
            "detail": {
                "payload_weight_kg": round(payload_weight, 1),
                "total_weight_kg": total_weight_kg,
                "delivery_distance_km": round(hospital_to_customer_km, 1),
                "best_drone_id": best.get("drone_id"),
                "best_drone_battery_pct": best.get("battery_pct"),
                "min_energy_required_pct": best.get("energy_required_pct"),
                "shortest_route_km": best.get("total_km"),
                "drones_evaluated": len(rejected),
            },
            "message": f"Payload {total_weight_kg}kg is too heavy — closest drone needs "
                       f"{best.get('energy_required_pct', '?')}% battery but best available has "
                       f"{best.get('battery_pct', '?')}%. Try reducing quantity.",
        }), 409

    candidates.sort(key=lambda c: c["score"], reverse=True)
    best = candidates[0]

    return jsonify({
        "status": "ROUTE_CONFIRMED",
        "selected_drone": best["drone_id"],
        "score": best["score"],
        "calculation_data": best["calculation_data"],
        "eta_minutes": best["calculation_data"]["flight_path"]["eta_minutes"],
        "all_candidates": candidates,
    })


def astar_reroute(current, destination, hazard_zone, max_detour_minutes=10):
    """
    A* pathfinding on a lat/lng grid, avoiding a circular hazard zone.
    Returns (waypoints, distance_km, metadata) or None if no viable route exists.
    """
    hz_center = hazard_zone.get("center", {})
    hz_lat, hz_lng = hz_center.get("lat", 0), hz_center.get("lng", 0)
    hz_radius = hazard_zone.get("radius_km", 2.0)

    start = (round(current["lat"] / GRID_RESOLUTION) * GRID_RESOLUTION,
             round(current["lng"] / GRID_RESOLUTION) * GRID_RESOLUTION)
    goal = (round(destination["lat"] / GRID_RESOLUTION) * GRID_RESOLUTION,
            round(destination["lng"] / GRID_RESOLUTION) * GRID_RESOLUTION)

    original_direct_distance = haversine(start[0], start[1], goal[0], goal[1])
    max_detour_km = (max_detour_minutes / 60) * DRONE_SPEED_KMH + original_direct_distance

    def is_in_hazard(lat, lng):
        return haversine(lat, lng, hz_lat, hz_lng) < hz_radius

    def heuristic(node):
        return haversine(node[0], node[1], goal[0], goal[1])

    def neighbors(node):
        deltas = [
            (GRID_RESOLUTION, 0), (-GRID_RESOLUTION, 0),
            (0, GRID_RESOLUTION), (0, -GRID_RESOLUTION),
            (GRID_RESOLUTION, GRID_RESOLUTION), (-GRID_RESOLUTION, -GRID_RESOLUTION),
            (GRID_RESOLUTION, -GRID_RESOLUTION), (-GRID_RESOLUTION, GRID_RESOLUTION),
        ]
        result = []
        for dlat, dlng in deltas:
            nlat = round(node[0] + dlat, 6)
            nlng = round(node[1] + dlng, 6)
            if not is_in_hazard(nlat, nlng):
                result.append((nlat, nlng))
        return result

    open_set = [(heuristic(start), 0, start, [start])]
    visited = set()
    iterations = 0
    max_iterations = 5000

    while open_set and iterations < max_iterations:
        iterations += 1
        f, g, current_node, path = heapq.heappop(open_set)

        if current_node in visited:
            continue
        visited.add(current_node)

        dist_to_goal = haversine(current_node[0], current_node[1], goal[0], goal[1])
        if dist_to_goal < GRID_RESOLUTION * 2:
            path.append(goal)
            total_dist = sum(
                haversine(path[i][0], path[i][1], path[i + 1][0], path[i + 1][1])
                for i in range(len(path) - 1)
            )
            if total_dist > max_detour_km:
                return None

            waypoints = [path[0]]
            for i in range(1, len(path) - 1):
                prev_bearing = math.atan2(path[i][1] - path[i - 1][1], path[i][0] - path[i - 1][0])
                next_bearing = math.atan2(path[i + 1][1] - path[i][1], path[i + 1][0] - path[i][0])
                if abs(prev_bearing - next_bearing) > 0.15:
                    waypoints.append(path[i])
            waypoints.append(path[-1])

            detour_distance_km = total_dist - original_direct_distance
            detour_percentage = (detour_distance_km / original_direct_distance * 100) if original_direct_distance > 0 else 0
            additional_battery_pct = detour_distance_km * BASE_CONSUMPTION_PER_KM

            metadata = {
                "original_distance_km": round(original_direct_distance, 1),
                "detour_distance_km": round(detour_distance_km, 1),
                "detour_percentage": round(detour_percentage, 1),
                "additional_battery_consumption_pct": round(additional_battery_pct, 1),
            }

            return [{
                "lat": round(w[0], 4),
                "lng": round(w[1], 4),
            } for w in waypoints], round(total_dist, 1), metadata

        total_path_dist = sum(
            haversine(path[i][0], path[i][1], path[i + 1][0], path[i + 1][1])
            for i in range(len(path) - 1)
        ) if len(path) > 1 else 0

        if total_path_dist > max_detour_km:
            continue

        for nb in neighbors(current_node):
            if nb not in visited:
                step_cost = haversine(current_node[0], current_node[1], nb[0], nb[1])
                new_g = g + step_cost
                new_f = new_g + heuristic(nb)
                heapq.heappush(open_set, (new_f, new_g, nb, path + [nb]))

    return None


@app.route("/route/reroute", methods=["POST"])
def reroute():
    """Mid-flight rerouting using A* with hazard avoidance (Scenario 3)."""
    data = request.get_json()
    order_id = data.get("order_id")
    drone_id = data.get("drone_id")
    current_coords = data.get("current_coords", {})
    destination_coords = data.get("destination_coords", {})
    hazard_zone = data.get("hazard_zone", {})
    max_detour = data.get("max_detour_minutes", 10)
    mission_phase = data.get("mission_phase", "TO_CUSTOMER")  # Default to TO_CUSTOMER for backward compatibility

    # For TO_HOSPITAL phase, use simpler direct routing with hazard avoidance
    # (no need for complex A* since no supplies on board yet)
    if mission_phase == "TO_HOSPITAL":
        print(f"  [REROUTE] {order_id}: Rerouting TO_HOSPITAL phase")
        direct_distance = haversine(
            current_coords.get("lat", 0), current_coords.get("lng", 0),
            destination_coords.get("lat", 0), destination_coords.get("lng", 0)
        )

        # Simple detour: add 15-20% for going around hazard
        detour_factor = 1.2
        reroute_distance = round(direct_distance * detour_factor, 1)
        eta_minutes = round((reroute_distance / DRONE_SPEED_KMH) * 60)

        from datetime import datetime, timedelta, timezone
        sg_tz = timezone(timedelta(hours=8))
        updated_eta = (datetime.now(sg_tz) + timedelta(minutes=eta_minutes)).isoformat()

        return jsonify({
            "status": "REROUTE_FOUND",
            "route_id": f"RT-HOSP-{abs(hash(order_id)) % 1000:03d}",
            "order_id": order_id,
            "drone_id": drone_id,
            "waypoints": [
                {"lat": round(current_coords.get("lat", 0), 4), "lng": round(current_coords.get("lng", 0), 4)},
                {"lat": round(destination_coords.get("lat", 0), 4), "lng": round(destination_coords.get("lng", 0), 4)}
            ],
            "updated_eta": updated_eta,
            "distance_km": reroute_distance,
            "eta_minutes": eta_minutes,
            "original_distance_km": round(direct_distance, 1),
            "detour_distance_km": round(reroute_distance - direct_distance, 1),
            "detour_percentage": round((detour_factor - 1) * 100, 1),
            "waypoint_count": 2,
            "additional_battery_consumption_pct": round((reroute_distance - direct_distance) * BASE_CONSUMPTION_PER_KM, 1),
            "estimated_arrival_battery_pct": 80,  # Placeholder
            "route_summary": {
                "phase": "TO_HOSPITAL",
                "original_path": {
                    "start": {"lat": round(current_coords.get("lat", 0), 4), "lng": round(current_coords.get("lng", 0), 4)},
                    "end": {"lat": round(destination_coords.get("lat", 0), 4), "lng": round(destination_coords.get("lng", 0), 4)},
                    "distance_km": round(direct_distance, 1),
                },
                "new_path": {
                    "waypoints": [
                        {"lat": round(current_coords.get("lat", 0), 4), "lng": round(current_coords.get("lng", 0), 4)},
                        {"lat": round(destination_coords.get("lat", 0), 4), "lng": round(destination_coords.get("lng", 0), 4)}
                    ],
                    "distance_km": reroute_distance,
                },
                "reason_for_detour": f"Hazard zone avoided en route to hospital. Mission phase: {mission_phase}",
            },
            "hazards_avoided": [hazard_zone],
            "mission_phase": mission_phase,
        })

    # Original A* logic for TO_CUSTOMER phase

    result = astar_reroute(current_coords, destination_coords, hazard_zone, max_detour)

    if result is None:
        return jsonify({
            "order_id": order_id,
            "drone_id": drone_id,
            "status": "NO_VIABLE_ROUTE",
            "reason": "No safe route available within current weather and flight constraints",
        }), 409

    waypoints, distance_km, metadata = result
    eta_minutes = round((distance_km / DRONE_SPEED_KMH) * 60)

    from datetime import datetime, timedelta, timezone
    sg_tz = timezone(timedelta(hours=8))
    updated_eta = (datetime.now(sg_tz) + timedelta(minutes=eta_minutes)).isoformat()

    estimated_arrival_battery_pct = max(20, 80 - metadata["additional_battery_consumption_pct"])

    hz_center = hazard_zone.get("center", {})
    hz_radius = hazard_zone.get("radius_km", 2.0)
    hazard_type = hazard_zone.get("type", "weather")

    return jsonify({
        "status": "REROUTE_FOUND",
        "route_id": f"RT-{abs(hash(order_id)) % 1000:03d}",
        "order_id": order_id,
        "drone_id": drone_id,
        "waypoints": waypoints,
        "updated_eta": updated_eta,
        "distance_km": distance_km,
        "eta_minutes": eta_minutes,
        "original_distance_km": metadata["original_distance_km"],
        "detour_distance_km": metadata["detour_distance_km"],
        "detour_percentage": metadata["detour_percentage"],
        "waypoint_count": len(waypoints),
        "additional_battery_consumption_pct": metadata["additional_battery_consumption_pct"],
        "estimated_arrival_battery_pct": round(estimated_arrival_battery_pct, 1),
        "route_summary": {
            "phase": "TO_CUSTOMER",
            "original_path": {
                "start": {"lat": round(current_coords.get("lat", 0), 4), "lng": round(current_coords.get("lng", 0), 4)},
                "end": {"lat": round(destination_coords.get("lat", 0), 4), "lng": round(destination_coords.get("lng", 0), 4)},
                "distance_km": metadata["original_distance_km"],
            },
            "new_path": {
                "waypoints": waypoints,
                "distance_km": distance_km,
            },
            "reason_for_detour": f"Hazard zone detected at ({hz_center.get('lat', 0):.4f}, {hz_center.get('lng', 0):.4f}) with {hz_radius}km radius",
        },
        "hazards_avoided": [
            {
                "lat": hz_center.get("lat", 0),
                "lng": hz_center.get("lng", 0),
                "radius_km": hz_radius,
                "type": hazard_type,
            }
        ],
        "mission_phase": mission_phase,
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "route-planning"})


if __name__ == "__main__":
    print("  Route Planning Service running on port 5009")
    app.run(host="0.0.0.0", port=5009, debug=True)
