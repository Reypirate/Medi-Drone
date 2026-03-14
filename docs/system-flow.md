# Medi-Drone Application: Complete System Flow

## System Architecture Overview

Medi-Drone is a **microservices-based medical drone delivery system** that delivers medical supplies (blood, defibrillators, insulin, etc.) from hospitals to patients' homes.

### Technology Stack
- **API Gateway**: Kong 3.8 (DB-less declarative mode)
- **Message Broker**: RabbitMQ (AMQP topic exchanges)
- **Databases**: MySQL 8.0 (3 separate databases)
- **Services**: 9 Python Flask microservices
- **Container Orchestration**: Docker Compose

---

## Services Overview

### Atomic Services (Single Responsibility)
| Service | Port | Purpose | Database |
|---------|------|---------|----------|
| **inventory** | 5003 | Manages hospital stock, reserves/releases items | inventory_db |
| **hospital** | 5005 | Hospital/location data | hospital_db |
| **drone-management** | 5008 | Drone fleet tracking, status updates | drone_db |
| **weather** | 5006 | Weather safety checks for drone flights | - |
| **geolocation** | 5007 | Address geocoding to coordinates | - |
| **route-planning** | 5009 | Route optimization, drone selection, rerouting | - |
| **notification** | 5004 | SMS notifications via Twilio | - |

### Composite Services (Orchestration)
| Service | Port | Purpose |
|---------|------|---------|
| **order** | 5001 | Order creation, hospital auto-selection, inventory reservation |
| **drone-dispatch** | 5002 | Full delivery orchestration, weather polling, mid-flight rerouting |

---

## Complete Flow: Start to End

### Scenario 1: Normal Order Delivery

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: DOCTOR CREATES ORDER                                                       │
│─────────────────────────────────────────────────────────────────────────────────────│
│  Doctor → Kong API Gateway → Order Service: POST /order                            │
│  Payload: { item_id, quantity, urgency_level, customer_coords }                   │
│                                                                                   │
│  Order Service creates order_id (e.g., "ORD-A1B2C3")                               │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: ORDER SERVICE - HOSPITAL SELECTION                                         │
│─────────────────────────────────────────────────────────────────────────────────────│
│  1. Calls inventory: GET /inventory/search?item_id=BLOOD-O-NEG&quantity=1         │
│     → Returns list of hospitals with sufficient stock                             │
│                                                                                   │
│  2. Calls hospital: GET /hospitals → Gets all hospital coordinates               │
│                                                                                   │
│  3. Calculates distance from customer to each stocked hospital (Haversine)      │
│                                                                                   │
│  4. Selects NEAREST hospital with stock                                           │
│     Example: HOSP-003 (Tan Tock Seng Hospital) at 6.09km                          │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 3: ORDER SERVICE - INVENTORY RESERVATION                                     │
│─────────────────────────────────────────────────────────────────────────────────────│
│  Calls inventory: POST /inventory/reserve                                         │
│  Payload: { order_id, hospital_id, item_id, quantity }                            │
│                                                                                   │
│  Inventory Service reserves stock in database (status: RESERVED)                 │
│  Prevents double-booking via database row locking                                 │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 4: ORDER CONFIRMED - AMQP EVENT                                             │
│─────────────────────────────────────────────────────────────────────────────────────│
│  Order Service publishes to RabbitMQ:                                            │
│  Exchange: "orders" | Routing Key: "order.confirmed"                             │
│  Message: { order_id, hospital_id, item_id, quantity, urgency, customer_coords }  │
│                                                                                   │
│  Order status updated to "CONFIRMED"                                              │
│  Response to Doctor: "Order confirmed. Nearest hospital: Tan Tock Seng..."       │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 5: DRONE DISPATCH RECEIVES ORDER                                             │
│─────────────────────────────────────────────────────────────────────────────────────│
│  AMQP Consumer (drone-dispatch) receives "order.confirmed" message              │
│  Spawns dispatch_thread to process order                                         │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 6: RESOLVE COORDINATES                                                       │
│─────────────────────────────────────────────────────────────────────────────────────│
│  1. GET /hospital/{hospital_id}/location → hospital_coords                       │
│  2. customer_coords from order message (or geocode if needed)                     │
│                                                                                   │
│  Calculate delivery distance (Haversine formula)                                 │
│  If > 50km → CANCEL (OUT_OF_RANGE)                                                 │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 7: CHECK DRONE AVAILABILITY                                                  │
│─────────────────────────────────────────────────────────────────────────────────────│
│  GET /drones/available?min_battery_pct=30&region=CENTRAL                         │
│  → Returns list of available drones                                              │
│                                                                                   │
│  If no drones available → CANCEL (NO_DRONES_AVAILABLE)                            │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 8: WEATHER SAFETY CHECK                                                      │
│─────────────────────────────────────────────────────────────────────────────────────│
│  POST /weather/check?lat={customer_lat}&lng={customer_lng}                       │
│  → Returns weather safety status                                                 │
│                                                                                   │
│  If status = "UNSAFE" → CANCEL (UNSAFE_WEATHER)                                   │
│  Checks: wind speed, visibility, precipitation                                   │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 9: ROUTE PLANNING & DRONE SELECTION                                          │
│─────────────────────────────────────────────────────────────────────────────────────│
│  POST /route/plan                                                                │
│  Payload: { hospital_coords, customer_coords, payload_weight, available_drones }│
│                                                                                   │
│  Route Planning Service:                                                          │
│  - Calculates battery consumption for each drone                                │
│  - Selects optimal drone (battery + distance)                                    │
│  - Computes route and ETA                                                        │
│                                                                                   │
│  If no viable route → CANCEL (NO_VIABLE_ROUTE)                                    │
│  Returns: { selected_drone, eta_minutes, route_id }                              │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 10: UPDATE DRONE STATUS                                                      │
│─────────────────────────────────────────────────────────────────────────────────────│
│  PATCH /drones/{drone_id}/status                                                  │
│  Payload: { status: "IN_FLIGHT" }                                                  │
│                                                                                   │
│  Drone marked as in-use, unavailable for other orders                             │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 11: CONFIRM DISPATCH                                                         │
│─────────────────────────────────────────────────────────────────────────────────────│
│  POST /dispatch/confirm to Order Service                                         │
│  Payload: { order_id, drone_id, eta_minutes, status: "DISPATCHED" }              │
│                                                                                   │
│  Order updated with drone assignment and ETA                                     │
│  Active mission registered for weather polling                                   │
│                                                                                   │
│  Doctor gets: "Order ORD-XXXX dispatched via Drone DRN-XXX, ETA: 15 minutes"     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 12: ACTIVE MISSION MONITORING (Background Thread)                            │
│─────────────────────────────────────────────────────────────────────────────────────│
│  Polling Thread (runs every 30 seconds):                                         │
│  - Checks active_missions dictionary                                            │
│  - For each IN_FLIGHT mission: POST /weather/live                               │
│    → Checks real-time weather along route                                        │
│                                                                                   │
│  If weather becomes UNSAFE: → Attempt REROUTE (Scenario 3)                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Scenario 3: Mid-Flight Weather Rerouting

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 3.1: WEATHER HAZARD DETECTED                                                  │
│─────────────────────────────────────────────────────────────────────────────────────│
│  Polling thread detects unsafe weather:                                          │
│  - hazard_zone: { lat, lng, radius }                                              │
│  - reasons: ["HIGH_WIND", "POOR_VISIBILITY"]                                      │
│                                                                                   │
│  Attempts reroute: POST /route/reroute                                          │
│  Payload: { order_id, drone_id, current_coords, destination_coords,              │
│            hazard_zone, max_detour_minutes: 10 }                                 │
│                                                                                   │
│  If SUCCESSFUL REROUTE:                                                           │
│  - mission.status = "REROUTED_IN_FLIGHT"                                         │
│  - Notifies Order Service of new ETA                                             │
│  - SMS to Doctor: "Weather reroute. New ETA: 22 minutes"                         │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 3.2: NO VIABLE ROUTE - MISSION ABORT                                          │
│─────────────────────────────────────────────────────────────────────────────────────│
│  If reroute fails (no safe path):                                                 │
│  1. PATCH /drones/{drone_id}/status → { status: "RETURNING" }                      │
│  2. POST /dispatch/failure to Order Service                                      │
│  3. POST /inventory/release → Return reserved stock to hospital                   │
│  4. POST /notifications/notify.sms → URGENT SMS to Doctor                        │
│  5. Delete mission from active_missions                                          │
│                                                                                   │
│  SMS: "URGENT: Delivery cancelled due to unsafe weather. Drone returning..."    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Design Patterns

### 1. Event-Driven Choreography (AMQP)
```
order.confirmed → [drone-dispatch]
                    ↓
order.failed → [notification]
                    ↓
notify.sms → [notification] (Twilio SMS)
```

### 2. Compensating Transactions (Saga Pattern)
When any step fails, previous actions are undone:
```
Inventory Reserve → Weather Unsafe → Release Inventory
Drone IN_FLIGHT → Mission Abort → Drone RETURNING
```

### 3. Geospatial Calculations
- **Haversine Formula**: Distance between coordinates (Earth radius: 6371 km)
- Used for hospital proximity and delivery distance

### 4. Thread-Based Background Processing
- **AMQP Consumer Thread**: Listens for orders (daemon thread)
- **Weather Polling Thread**: Monitors active missions (30s interval)

---

## Data Flow Summary

```
Doctor Order
    │
    ▼
[Order Service] ──► [Inventory] (reserve stock)
    │                     │
    │                     └─── hospitals with stock
    ▼
[Hospital Service] (get coordinates)
    │
    ▼
Select Nearest Hospital
    │
    ▼
AMQP: order.confirmed
    │
    ▼
[Drone Dispatch] ◄──┬── [Drone Management] (available drones)
                    ├── [Weather Service] (safety check)
                    ├── [Route Planning] (optimize route)
                    └── [Geolocation] (address → coords)
    │
    ├──────────────────────┐
    ▼                       ▼
[Order Service]      [Background Polling]
(confirm dispatch)    (weather monitoring)
    │                       │
    ▼                       ▼
Doctor Notified    Weather Hazard?
                      │
            ┌─────────┴─────────┐
            ▼                   ▼
        Reroute            Abort Mission
            │                   │
            ▼                   ▼
    New Route/ETA    Release Inventory
                      Return Drone
```

---

## Database Schema Overview

**inventory_db**: `inventory` table (hospital_id, item_id, quantity)
**hospital_db**: `hospital` table (hospital_id, name, lat, lng)
**drone_db**: `drone` table (drone_id, coords, battery_pct, status)

---

## Error Handling

| Failure Point | Compensating Action | User Notification |
|---------------|---------------------|-------------------|
| No hospital has stock | Return error | SMS: "No hospital nearby has stock" |
| Delivery > 50km | Cancel order | SMS: "Address too far from hospital" |
| No drones available | Release inventory | SMS: "No operational drones available" |
| Unsafe weather | Cancel order | SMS: "Weather unsafe for drone flight" |
| No viable route | Release inventory, return drone | SMS: "Delivery cancelled - weather reroute failed" |

---

## Entry Points

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/order/order` | Create new delivery order |
| GET | `/api/order/order/{order_id}` | Get order status |
| GET | `/api/order/orders` | List all orders |
| GET | `/health` | Service health check (all services) |
| GET | `/dispatch/missions` | List active missions |
| POST | `/dispatch/simulate/weather` | Trigger manual weather poll (debug) |
