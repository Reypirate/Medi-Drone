# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Git Conventions

**DO NOT include co-author information in commits.** All commits, pushes, and other git commands should be made without `Co-Authored-By:` or any attribution tags.

## Project Overview

Medi-Drone is an emergency medical supply drone delivery platform built on a microservices architecture. Doctors/hospitals request urgent delivery of medical supplies (blood, defibrillators, organ transport kits) via autonomous drones.

## Common Commands

### Starting the application
```bash
docker-compose up --build
```

First startup takes 2-3 minutes. Wait for all services to report "running on port XXXX" in logs.

### Stopping the application
```bash
docker-compose down              # Stop containers
docker-compose down -v           # Also remove database volumes
```

### Accessing services
- **Web UI**: http://localhost:8080
- **Kong Gateway**: http://localhost:8000
- **Kong Admin API**: http://localhost:8001
- **RabbitMQ Management**: http://localhost:15672 (guest/guest)
- **MySQL ports**: 3306 (inventory), 3307 (drone), 3308 (hospital)

### Triggering mid-flight weather simulation
```bash
curl -X POST http://localhost:5002/dispatch/simulate/weather \
  -H "Content-Type: application/json" \
  -d '{"order_id": "YOUR_ORDER_ID"}'
```

### Database initialization
Database schemas are auto-initialized via `init.sql` files in each service folder on first container startup.

## Architecture

### Microservices Pattern
The application uses **Composite vs Atomic microservices**:

**Composite Services** (orchestrate business logic across atomic services):
- `order` (5001): Order lifecycle, hospital auto-selection, inventory reservation
- `drone_dispatch` (5002): Dispatch orchestration, weather polling, mid-flight rerouting

**Atomic Services** (single responsibility, stateless or single DB):
- `inventory` (5003): Stock management with MySQL (inventory_db)
- `notification` (5004): AMQP consumer, publishes to Twilio SMS
- `hospital_mock` (5005): Hospital data with MySQL (hospital_db)
- `weather` (5006): OpenWeatherMap API wrapper
- `geolocation` (5007): Google Maps API with in-memory coordinate cache
- `drone_management` (5008): Drone CRUD with MySQL (drone_db)
- `route_planning` (5009): Haversine distance + A* pathfinding (BTL component)

### Message Flow (AMQP)
RabbitMQ acts as the event bus. Key exchanges and routing keys:

**Exchange: `orders`**
- `order.confirmed` → consumed by `drone_dispatch`
- `order.failed` → consumed by `notification`

**Exchange: `notifications`**
- `notify.sms` → consumed by `notification` service

AMQP setup is handled via `amqp_setup.py` in relevant services. Each service declares its own queue and binds to the appropriate exchange/routing key.

### API Gateway
Kong (port 8000/8001) routes all external traffic using declarative config in `kong/kong.yml`:
- Centralized CORS handling
- Service routes prefixed with `/api/<service>`
- Strips path prefix before proxying to backend

### User Scenarios

**Scenario 1 & 2: Order & Dispatch Flow**
1. User submits order via Web UI → Kong → `order` service
2. `order` auto-selects nearest hospital with stock (Haversine distance)
3. `order` reserves inventory, publishes `order.confirmed`
4. `drone_dispatch` consumes event, orchestrates: hospital coords + customer coords (parallel), drone availability, weather check, route planning
5. Any failure triggers compensating transaction: cancel order, release inventory, notify via SMS

**Scenario 3.1: Mid-Flight Rerouting**
1. `drone_dispatch` polls weather service every 30s (configurable via `POLL_INTERVAL`)
2. If unsafe weather detected, requests reroute from `route_planning`
3. A* pathfinding returns waypoints avoiding hazard zone
4. Mission continues on new route, order status updated

**Scenario 3.2: Mid-Flight Cancellation**
1. If A* returns no viable route, mission aborts
2. Drone status set to RETURNING, inventory released
3. Urgent SMS notification sent to doctor

## Environment Variables

Required in `.env` (copy from `.env.example`):
```
OPENWEATHER_API_KEY=your_key
GOOGLE_MAPS_API_KEY=your_key
TWILIO_ACCOUNT_SID=your_sid
TWILIO_AUTH_TOKEN=your_token
TWILIO_FROM_NUMBER=+6598765432
TWILIO_TO_NUMBER=+6512345678
MYSQL_ROOT_PASSWORD=root_password
```

The system works without external API keys - weather/geolocation will fail gracefully, core flow remains functional.

## Setup & Troubleshooting

### First-Time Setup Prerequisites
1. **Docker Desktop must be running** before starting services
2. **Create `.env` file** from `.env.example` with your API keys
3. **Ensure ports are available**:
   - 5672, 15672 (RabbitMQ)
   - 3306, 3307, 3308 (MySQL databases)
   - 5001-5009 (Microservices)
   - 8000, 8001 (Kong)
   - 8080 (Web UI)

### Common Port Conflicts
If you see "port is already allocated" errors:

```bash
# Check what's using the port (Windows)
netstat -ano | grep 5672

# Kill the process using PowerShell
powershell -Command "Stop-Process -Id <PID> -Force"

# Or stop all Docker containers first
docker-compose down -v
```

### Docker Desktop Issues
If Docker Desktop stops unexpectedly during `docker-compose up`:
1. Restart Docker Desktop from Start menu
2. Wait for whale icon to be steady (not animating)
3. Run `docker-compose down -v` to clean up
4. Run `docker-compose up -d --build` to start fresh

### Verifying Services Are Healthy
```bash
# Check all containers are running
docker-compose ps

# View logs for a specific service
docker-compose logs -f order
docker-compose logs -f drone-dispatch

# Check RabbitMQ is accessible
curl http://localhost:15672

# Check Kong gateway is routing
curl http://localhost:8001/services
```

### Clean Restart Procedure
If services are misbehaving:
```bash
# Full clean restart
docker-compose down -v
docker-compose up -d --build

# Wait 2-3 minutes for all services to start
# Check logs: docker-compose logs -f
```

## Key Service Endpoints

All routes go through Kong at `/api/<service>/...`

**Order Service** (`/api/order/`):
- `POST /api/order/order` - Create order (requires customer_coords with lat/lng)
- `GET /api/orders/orders` - List all orders
- `GET /api/order/order/<order_id>` - Get order details
- `POST /api/order/order/<order_id>/cancel` - Cancel order

**NOTE**: Kong routes both `/api/order` and `/api/orders` to the order service, but the order service endpoints use `/order` (singular). Use the full paths above.

**Dispatch Service** (`/api/dispatch/`):
- `GET /dispatch/missions` - List active missions
- `POST /dispatch/simulate/weather` - Trigger manual weather poll (debug)

**Inventory Service** (`/api/inventory/`):
- `GET /inventory` - List inventory
- `GET /inventory/search?item_id=X&quantity=N` - Find hospitals with stock
- `POST /inventory/reserve` - Reserve stock
- `POST /inventory/release` - Release reserved stock

## Service Patterns

### AMQP Consumer Pattern
Services that consume AMQP messages (Order, Drone Dispatch, Notification):
1. Initialize connection via `amqp_setup.get_connection()`
2. Declare queue, bind to exchange/routing key
3. Set `basic_qos(prefetch_count=1)` for fair dispatch
4. Start `basic_consume` in daemon thread
5. Handle connection failures with reconnect logic

### Database Pattern
MySQL services (Inventory, Hospital, Drone Management):
1. Use `wait_for_db()` with retries before starting Flask
2. Use `FOR UPDATE` in SELECT for row-level locking (inventory reservation)
3. Explicit commit/rollback in try/except/finally blocks
4. Close cursor and connection in finally blocks

### Inter-Service Communication
Composite services call atomic services via HTTP:
- Use environment variables for service URLs (e.g., `INVENTORY_URL`)
- Set 10-15 second timeouts
- Handle failures gracefully with compensating transactions

## Item Weights
Defined in `drone_dispatch.py`:
- BLOOD bags: 0.6 kg
- DEFIB-01: 2.5 kg
- ORGAN-KIT-01: 3.0 kg
- EPINEPHRINE-01: 0.2 kg
- Default: 1.0 kg

## Constants

**Drone Operations**:
- `MAX_DELIVERY_DISTANCE_KM`: 50
- `DRONE_SPEED_KMH`: 36.0
- `EARTH_RADIUS_KM`: 6371.0

**Route Planning**:
- `GRID_RESOLUTION`: 0.002 (~220m per grid cell)
- `BASE_CONSUMPTION_PER_KM`: 1.8% battery at base weight
- `DRONE_BASE_WEIGHT_KG`: 2.5
