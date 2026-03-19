# Medi-Drone

Emergency medical supply drone delivery platform built on a microservices architecture. Hospitals and clinics can request urgent delivery of critical medical supplies (blood bags, defibrillators, organ transport kits) via autonomous drones, bypassing traffic congestion and reaching remote or accident sites faster.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Services](#services)
- [Prerequisites](#prerequisites)
- [Setup & Run](#setup--run)
- [Web UI Guide](#web-ui-guide)
- [User Scenarios](#user-scenarios)
- [Weather Simulation Guide](#weather-simulation-guide)
- [API Endpoints](#api-endpoints)
- [Troubleshooting](#troubleshooting)
- [Technology Stack](#technology-stack)

## Architecture Overview

```
Hospital/Doctor UI (Port 8080)
        |
    [Kong API Gateway] (Port 8000)  ← BTL
        |
   ┌────┴────┐
   │         │
[Order     [Drone Dispatch     ← Composite Microservices
 Service]   Service]
   │         │
   └────┬────┘
        |
   [RabbitMQ] (AMQP)
        |
   ┌────┼────┬────────┬──────────┬──────────┬────────────┐
   │    │    │        │          │          │            │
[Inv] [Notif] [Hosp] [Weather] [Geo]  [Drone Mgmt] [Route Plan]
                                                        ↑
                                              Haversine + A* (BTL)
```

### Services

| Service | Type | Port | Data Store | External API |
|---|---|---|---|---|
| Order Service | Composite | 5001 | In-memory | - |
| Drone Dispatch Service | Composite | 5002 | In-memory | - |
| Inventory Service | Atomic | 5003 | MySQL (inventory_db) | - |
| Notification Service | Atomic | 5004 | - | Twilio SMS |
| Hospital Service (Mock) | Atomic | 5005 | MySQL (hospital_db) | - |
| Weather Service | Atomic | 5006 | - | OpenWeatherMap |
| Geolocation Service | Atomic | 5007 | In-memory cache | Google Maps |
| Drone Management Service | Atomic | 5008 | MySQL (drone_db) | - |
| Route Planning Service | Atomic | 5009 | - | - |

### Infrastructure

| Component | Port(s) |
|---|---|
| Kong API Gateway | 8000 (proxy), 8001 (admin) |
| RabbitMQ | 5672 (AMQP), 15672 (management UI) |
| MySQL - Inventory | 3306 |
| MySQL - Drone | 3307 |
| MySQL - Hospital | 3308 |
| Nginx (Web UI) | 8080 |

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- API keys (optional, for full functionality):
  - [OpenWeatherMap API key](https://openweathermap.org/api) (free tier)
  - [Google Maps Geocoding API key](https://developers.google.com/maps/documentation/geocoding)
  - [Twilio account](https://www.twilio.com/) (free trial) for SMS notifications

## Setup & Run

### 1. Clone the repository

```bash
git clone https://github.com/Reypirate/Medi-Drone.git
cd Medi-Drone
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your API keys:

```
OPENWEATHER_API_KEY=your_openweather_key
GOOGLE_MAPS_API_KEY=your_google_maps_key
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_FROM_NUMBER=+6598765432
TWILIO_TO_NUMBER=+6512345678
MYSQL_ROOT_PASSWORD=root_password
```

> **Note:** The system works without external API keys. Weather and geolocation calls will return errors, but the core order and dispatch flow can still be demonstrated. Twilio SMS will fall back to mock (console logging) mode.

### 3. Start all services

```bash
docker-compose up --build
```

This will start all 15 containers. Wait for all services to report "running on port XXXX" in the logs. First startup may take 2-3 minutes as Docker pulls images and builds services.

### 4. Access the application

| Interface | URL | Credentials |
|---|---|---|
| **Web UI** | http://localhost:8080 | - |
| **Kong API Gateway** | http://localhost:8000 | - |
| **Kong Admin API** | http://localhost:8001 | - |
| **RabbitMQ Management** | http://localhost:15672 | guest/guest |

### 5. Stop all services

```bash
docker-compose down
```

To also remove database volumes:

```bash
docker-compose down -v
```

## Web UI Guide

The Medi-Drone Web UI provides four main sections for managing emergency medical supply deliveries:

### Dashboard Tab

**Purpose:** Submit emergency delivery orders and track their status

**How to Use:**

1. **Select Medical Supply:** Choose from the dropdown:
   - O-Negative Blood Bags
   - A-Positive Blood Bags
   - B-Positive Blood Bags
   - Portable Defibrillator (DEFIB-01)
   - Epinephrine Auto-Injector
   - Organ Transport Kit

2. **Set Quantity:** Use the spin button to select quantity (default: 1)

3. **Enter Delivery Location:**
   - **Postal Code Mode:** Enter Singapore postal code (e.g., 168588)
   - **Lat/Lng Mode:** Enter coordinates directly (e.g., 1.3644, 103.8190)
   - **Use My Location:** Click the 📍 button to auto-detect your location

4. **Check Address:** Click "Check Address" to validate the delivery location is within Singapore's drone delivery zone

5. **Confirm Address:** Review the resolved address and click "Confirm Address"

6. **Submit Order:** Click "Submit Emergency Order" to dispatch

7. **Track Status:** Watch the orders panel for real-time updates:
   - `PENDING` → `CONFIRMED` → `DISPATCHED` → `DELIVERED`
   - ETA countdown shown in red (≤5 min), yellow (≤10 min), or green (>10 min)

8. **Delete Orders:** For cancelled or completed orders, click the "Delete" button to remove them from the list

### Inventory Tab

**Purpose:** Search and view stock levels across all hospitals

**How to Use:**

1. Select a medical supply item from the dropdown
2. View real-time stock levels at each hospital
3. Color coding:
   - **Green:** High stock (≥30 units)
   - **Yellow:** Medium stock (10-29 units)
   - **Orange:** Low stock (1-9 units)
   - **Red:** Out of stock (0 units)

### Drones Tab

**Purpose:** Monitor the drone fleet status and active missions

**How to Use:**

1. View fleet statistics:
   - Total Fleet
   - Operational (available for dispatch)
   - In Flight (on active missions)
   - Unavailable (faulty or low battery)

2. View individual drone status:
   - **Operational:** Green circle icon, ready for dispatch
   - **In Flight:** Purple plane icon, showing mission details and ETA
   - **Low Battery:** Orange battery icon (<30% charge)
   - **Faulty:** Red warning icon

3. Each drone card shows:
   - Drone ID
   - Battery percentage with visual bar
   - Current GPS coordinates
   - Active mission details (if in flight)

### Simulation Tab

**Purpose:** Test weather-based drone rerouting and cancellation scenarios

**How to Use:**

#### Weather Simulation Controls

1. **Enable Bad Weather:**
   - Check weather conditions to simulate:
     - ☑ High Wind (>40 km/h)
     - ☑ Heavy Rain (>10mm/h)
     - ☑ Thunderstorm
     - ☑ Tornado
   - Adjust wind speed and rainfall values
   - Click "Enable Bad Weather" to activate simulation

2. **Grid-Based Hazard Zones:**
   - Enable "Grid Hazards" checkbox for advanced simulation
   - Enter hazard zone coordinates:
     - Latitude (e.g., 1.3521 for Central Singapore)
     - Longitude (e.g., 103.8198)
     - Radius in km (0.3 - 1.5 recommended)
   - Click "+ Add Hazard Zone" to place the hazard
   - Or use preset locations:
     - Central Singapore
     - Marina Bay
     - Changi Airport
     - Jurong
     - Woodlands

3. **Auto-Place Hazard on Active Mission:**
   - Requires an active IN_FLIGHT mission
   - Automatically calculates the flight path midpoint
   - Recommends a hazard zone radius (12% of remaining distance)
   - Populates the hazard input fields
   - Click "+ Add Hazard Zone" to confirm placement

4. **Trigger Weather Poll:**
   - Select a mission from the active missions list
   - Click "Trigger Weather Poll" to immediately check weather conditions
   - Watch for reroute or abort in the mission list

5. **Disable Simulation:**
   - Click "Disable Simulation" to return to normal weather mode

#### Active Missions Panel

Shows all currently active delivery missions with:
- Order ID and drone assignment
- Current dispatch status (IN_FLIGHT or REROUTED_IN_FLIGHT)
- Remaining ETA in minutes
- Reroute details (if rerouted):
  - Detour percentage
  - Number of waypoints
  - Original vs new distance

## User Scenarios

### Scenario 1: Order Lifecycle

Doctor submits a medical supply delivery request. The Order Service reserves inventory, publishes an `order.confirmed` event to RabbitMQ, and the Drone Dispatch Service picks it up. If stock is insufficient, an `order.failed` event triggers an SMS notification to the doctor.

### Scenario 2: Drone Dispatch

Upon receiving an `order.confirmed` event, the Drone Dispatch Service:
1. Resolves hospital coordinates (Hospital Service) and customer coordinates (Geolocation Service with caching) in parallel
2. Checks drone availability (battery >= 30%, operational status)
3. Checks weather safety at destination (wind speed <= 40 km/h)
4. Plans the optimal route using Haversine distance + scoring algorithm
5. Assigns the best drone and confirms dispatch

If any step fails (no drones, unsafe weather, no viable route), compensating transactions release reserved inventory and notify the doctor via SMS.

### Scenario 3.1: Successful Mid-Flight Rerouting

**Via UI:**
1. Dispatch an order and wait for it to be IN_FLIGHT
2. Go to Simulation tab
3. Click "Auto-Place Hazard on Active Mission"
4. Click "+ Add Hazard Zone" to place the hazard
5. Click "Trigger Weather Poll" for the mission
6. Watch the mission status change to `REROUTED_IN_FLIGHT`
7. View reroute details in the Orders or Missions panel

**What happens:**
- Weather Service detects hazard zone on flight path
- Route Planning Service uses A* pathfinding to calculate alternate route
- Mission continues with new waypoints avoiding the hazard
- Order updated with detour percentage, waypoints, and battery impact

### Scenario 3.2: Mid-Flight Cancellation

If no safe alternative route exists (A* returns no viable path), the mission is aborted. The drone returns to origin, inventory is released, and the doctor receives an urgent SMS notification.

## Weather Simulation Guide

### Understanding Hazard Zones

The weather simulation uses grid-based hazard zones to test drone rerouting:

- **Hazard Zone Radius:** 12% of flight distance (min 0.3km, max 1.5km)
- **Grid Resolution:** 0.002 degrees (~220m per grid cell)
- **A* Pathfinding:** Navigates around hazard zones using 8-directional movement

### Testing Rerouting

1. **Create an order** via Dashboard tab
2. **Wait for dispatch** (status becomes DISPATCHED)
3. **Go to Simulation tab**
4. **Enable simulation mode** with your desired weather conditions
5. **Auto-place hazard** or manually add a hazard zone
6. **Trigger weather poll** for the active mission

### Expected Behaviors

| Condition | Result |
|---|---|
| Hazard zone on direct path, small radius | Successful reroute with waypoints |
| Hazard zone on direct path, large radius | May abort if detour exceeds 10 minutes |
| Multiple hazard zones | Merged into single bounding zone for pathfinding |
| No hazard zone | Flight continues normally |

## API Endpoints

All API endpoints are accessible via Kong Gateway at `http://localhost:8000/api/<service>/...`

### Orders
- `POST /api/order/order` - Submit a new delivery order
  ```json
  {
    "item_id": "BLOOD-O-NEG",
    "quantity": 1,
    "urgency_level": "CRITICAL",
    "customer_address": "123 Test Street",
    "customer_coords": {"lat": 1.3644, "lng": 103.8190}
  }
  ```
- `GET /api/orders/orders` - List all orders
- `GET /api/orders/orders?status=active` - Filter by status (active/cancelled/completed)
- `GET /api/order/order/<order_id>` - Get order details
- `POST /api/order/order/<order_id>/cancel` - Cancel an order
- `DELETE /api/order/order/<order_id>` - Delete a cancelled/completed order

### Dispatch
- `GET /api/dispatch/dispatch/missions` - List active missions
- `GET /api/dispatch/dispatch/missions/<order_id>` - Get mission details
- `POST /api/dispatch/dispatch/simulate/weather` - Trigger weather poll for demo
  ```json
  {
    "order_id": "ORD-XXXXXX",
    "current_coords": {"lat": 1.36, "lng": 103.8}
  }
  ```

### Weather Simulation
- `POST /api/weather/simulate/enable` - Enable weather simulation
  ```json
  {
    "force_unsafe": true,
    "unsafe_reason": ["HIGH_WIND"],
    "hazard_zones": [{"lat": 1.35, "lng": 103.82, "radius_km": 0.5}]
  }
  ```
- `POST /api/weather/simulate/disable` - Disable simulation
- `GET /api/weather/simulate/status` - Get simulation status
- `POST /api/weather/simulate/auto-hazard` - Auto-place hazard on active mission
  ```json
  {
    "radius_km": 1.0
  }
  ```

### Inventory
- `GET /api/inventory/inventory` - List all inventory items
- `GET /api/inventory/inventory/search?item_id=BLOOD-O-NEG&quantity=1` - Find hospitals with stock
- `POST /api/inventory/inventory/reserve` - Reserve stock for order
- `POST /api/inventory/inventory/release` - Release reserved stock

### Hospitals
- `GET /api/hospitals/hospitals` - List all hospitals
- `GET /api/hospitals/hospital/<id>/location` - Get hospital coordinates

### Drones
- `GET /api/drones/drones` - List all drones
- `GET /api/drones/drones/available?min_battery_pct=30` - Get available drones
- `PATCH /api/drones/<drone_id>/status` - Update drone status
- `PATCH /api/drones/<drone_id>/position` - Update drone position during flight

### Notifications
- `GET /api/notification/notifications/log` - View SMS notification log

## Troubleshooting

### Port Already in Use

If you see "port is already allocated" errors:

```bash
# Find what's using the port (Windows PowerShell)
Get-NetTCPConnection -LocalPort 5672 -State Listen

# Kill the process
Stop-Process -Id <PID> -Force

# Or stop all Docker containers first
docker-compose down -v
```

### Docker Desktop Issues

If Docker Desktop stops unexpectedly during startup:

1. Restart Docker Desktop from Start menu
2. Wait for whale icon to be steady (not animating)
3. Run `docker-compose down -v` to clean up
4. Run `docker-compose up -d --build` to start fresh

### Services Not Starting

If services fail to start:

1. Check all containers are running: `docker-compose ps`
2. Check logs for errors: `docker-compose logs <service_name>`
3. Restart specific service: `docker-compose restart <service_name>`
4. Full restart: `docker-compose down && docker-compose up -d`

### Kong Connection Issues

If Kong shows 502/504 errors:

1. Verify backend services are healthy: `docker-compose ps`
2. Check Kong admin API: `curl http://localhost:8001/services`
3. Kong now waits for order and drone-dispatch to be healthy before starting

### Weather Simulation Not Working

If weather simulation doesn't trigger rerouting:

1. Ensure simulation is enabled: Check "Simulation Status" in UI
2. Verify mission has ETA ≥ 2 minutes (too late to reroute if less)
3. Check hazard zone radius (use 0.3-1.5km for best results)
4. Trigger weather poll manually via "Trigger Weather Poll" button

### Database Connection Errors

If you see MySQL connection errors:

1. Wait for database health checks to pass (up to 30 seconds on first start)
2. Check database containers are healthy: `docker-compose ps`
3. Verify `.env` file has correct MySQL password

## Technology Stack

- **Backend:** Python 3.11, Flask
- **Message Broker:** RabbitMQ 3.x (AMQP protocol)
- **Databases:** MySQL 8.0 (3 separate containers)
- **API Gateway:** Kong 3.8 (DB-less declarative mode) - BTL
- **Frontend:** HTML5, CSS3, JavaScript (ES6+)
- **Web Server:** Nginx Alpine
- **Containerization:** Docker, Docker Compose
- **External APIs:** Twilio (SMS), OpenWeatherMap, Google Maps Geocoding

## Beyond-the-Labs (BTL) Components

1. **Kong API Gateway** - Centralized routing, CORS handling, and request proxying for all microservices
2. **Advanced AMQP Patterns** - Event-driven choreography with topic exchanges and multiple routing keys
3. **A* Pathfinding** - Grid-based pathfinding algorithm that dynamically excludes weather hazard zones
4. **Health Check Integration** - Service health monitoring with proper startup dependencies

## Project Structure

```
Medi-Drone/
├── docker-compose.yml          # All 15 containers with health checks
├── .env.example                # Environment variable template
├── .env                        # Your actual API keys (not in git)
├── README.md
├── CLAUDE.md                   # Additional documentation for Claude Code
├── kong/
│   └── kong.yml                # Kong declarative config
├── services/
│   ├── order/                  # Composite: Order lifecycle
│   │   ├── Dockerfile          # With curl for health checks
│   │   ├── order.py            # Flask app with /health endpoint
│   │   └── requirements.txt
│   ├── drone_dispatch/         # Composite: Dispatch + rerouting
│   │   ├── Dockerfile          # With curl for health checks
│   │   ├── drone_dispatch.py   # Flask app with /health endpoint
│   │   └── requirements.txt
│   ├── inventory/              # Atomic: Stock management
│   ├── notification/           # Atomic: Twilio SMS via AMQP
│   ├── hospital_mock/          # Atomic: OutSystems mock
│   ├── weather/                # Atomic: OpenWeatherMap + simulation
│   │   └── weather.py          # Proportional hazard radius calculation
│   ├── geolocation/            # Atomic: Google Maps + cache
│   ├── drone_management/       # Atomic: Drone CRUD
│   ├── route_planning/         # Atomic: Haversine + A*
│   └── common/                 # Shared request tracking module
└── ui/
    ├── index.html              # Web UI
    ├── nginx.conf              # Nginx config
    └── js/
        └── app.js              # Frontend logic with weather simulation
```

## License

This project is for educational purposes demonstrating microservices architecture, event-driven systems, and autonomous drone delivery coordination.
