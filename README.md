# Medi-Drone

Emergency medical supply drone delivery platform built on a microservices architecture. Hospitals and clinics can request urgent delivery of critical medical supplies (blood bags, defibrillators, organ transport kits) via autonomous drones, bypassing traffic congestion and reaching remote or accident sites faster.

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
During flight, the Drone Dispatch Service polls the Weather Service for corridor safety. If unsafe conditions are detected, it requests a reroute from the Route Planning Service using A* pathfinding to avoid the hazard zone. The mission continues on the new route.

### Scenario 3.2: Mid-Flight Cancellation
If no safe alternative route exists (A* returns no viable path), the mission is aborted. The drone returns to origin, inventory is released, and the doctor receives an urgent SMS notification.

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

| Interface | URL |
|---|---|
| **Web UI** | http://localhost:8080 |
| **Kong API Gateway** | http://localhost:8000 |
| **RabbitMQ Management** | http://localhost:15672 (guest/guest) |
| **Kong Admin API** | http://localhost:8001 |

### 5. Stop all services

```bash
docker-compose down
```

To also remove database volumes:

```bash
docker-compose down -v
```

## Demo Walkthrough

### Scenario 1 & 2: Place an Order

1. Open the Web UI at http://localhost:8080
2. Select a source hospital (e.g., Singapore General Hospital)
3. Choose a medical supply (e.g., O-Negative Blood Bags)
4. Set quantity and urgency level to CRITICAL
5. Enter a delivery address
6. Click **Submit Emergency Order**
7. Watch the Activity Log and Orders panel for status updates:
   - `PENDING` -> `CONFIRMED` -> `DISPATCHED`

### Scenario 3: Trigger Mid-Flight Rerouting

After an order is dispatched, use the simulate endpoint to trigger a weather poll:

```bash
curl -X POST http://localhost:5002/dispatch/simulate/weather \
  -H "Content-Type: application/json" \
  -d '{"order_id": "YOUR_ORDER_ID"}'
```

If the weather is currently unsafe at the destination, you will see the reroute or abort flow execute.

## API Endpoints (via Kong Gateway)

### Orders
- `POST /api/order/order` - Submit a new delivery order
- `GET /api/orders/orders` - List all orders
- `GET /api/order/order/<order_id>` - Get order details

### Dispatch
- `GET /api/dispatch/dispatch/missions` - List active missions
- `POST /api/dispatch/dispatch/simulate/weather` - Trigger weather poll for demo

### Inventory
- `GET /api/inventory/inventory` - List all inventory items

### Hospitals
- `GET /api/hospitals/hospitals` - List all hospitals
- `GET /api/hospital/hospital/<id>/location` - Get hospital coordinates

### Drones
- `GET /api/drones/drones` - List all drones
- `GET /api/drones/drones/available` - Get available drones

## Technology Stack

- **Backend:** Python 3.11, Flask
- **Message Broker:** RabbitMQ 3.x (AMQP protocol)
- **Databases:** MySQL 8.0 (3 separate containers)
- **API Gateway:** Kong 3.9 (DB-less declarative mode) - BTL
- **Frontend:** HTML, CSS, JavaScript (vanilla)
- **Web Server:** Nginx Alpine
- **Containerization:** Docker, Docker Compose
- **External APIs:** Twilio (SMS), OpenWeatherMap, Google Maps Geocoding

## Beyond-the-Labs (BTL) Components

1. **Kong API Gateway** - Centralized routing, CORS handling, and request proxying for all microservices. Not covered in labs.
2. **Advanced AMQP Patterns** - Event-driven choreography with topic exchanges and multiple routing keys (order.confirmed, order.failed, notify.sms).
3. **A* Pathfinding with Hazard Avoidance** - Grid-based pathfinding algorithm that dynamically excludes weather hazard zones for mid-flight drone rerouting.

## Project Structure

```
Medi-Drone/
├── docker-compose.yml          # All 15 containers
├── .env.example                # Environment variable template
├── README.md
├── kong/
│   └── kong.yml                # Kong declarative config
├── services/
│   ├── order/                  # Composite: Order lifecycle
│   ├── drone_dispatch/         # Composite: Dispatch + rerouting
│   ├── inventory/              # Atomic: Stock management
│   ├── notification/           # Atomic: Twilio SMS via AMQP
│   ├── hospital_mock/          # Atomic: OutSystems mock
│   ├── weather/                # Atomic: OpenWeatherMap
│   ├── geolocation/            # Atomic: Google Maps + cache
│   ├── drone_management/       # Atomic: Drone CRUD
│   └── route_planning/         # Atomic: Haversine + A*
└── ui/
    ├── index.html              # Web UI
    ├── nginx.conf              # Nginx config
    └── js/
        └── app.js              # Frontend logic
```
