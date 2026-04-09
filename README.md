# Medi-Drone

Emergency medical supply drone delivery platform built on a microservices architecture. Hospitals and clinics can request urgent delivery of critical medical supplies (blood bags, defibrillators, organ transport kits) via autonomous drones.

**Git Repository Link: https://github.com/Reypirate/Medi-Drone.git**

## Prerequisites

**Required:**
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

**Optional (for full functionality):**
- [OpenWeatherMap API key](https://openweathermap.org/api) (free tier)
- [Google Maps Geocoding API key](https://developers.google.com/maps/documentation/geocoding)
- [Twilio account](https://www.twilio.com/) (free trial) for SMS notifications

> **Note:** The system works without external API keys. Weather and geolocation calls will return errors, but the core order and dispatch flow can still be demonstrated.

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

Edit `.env` and fill in your API keys (optional):

```
OPENWEATHER_API_KEY=your_openweather_key
GOOGLE_MAPS_API_KEY=your_google_maps_key
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_FROM_NUMBER=+6598765432
TWILIO_TO_NUMBER=+6512345678
MYSQL_ROOT_PASSWORD=root_password
```

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
| **Frontend Dev Server** | http://localhost:8080 | (Run via `pnpm run dev` in `/frontend`) |

### 6. Frontend Development
If you want to modify the frontend with Hot Module Replacement (HMR):
1. Navigate to `cd frontend`.
2. Install dependencies: `pnpm install`.
3. Start development server: `pnpm run dev`.
4. The dashboard will be available at `http://localhost:8080` (proxying requests to Kong).

### 5. Stop all services

```bash
docker-compose down
```

To also remove database volumes:

```bash
docker-compose down -v
```

## Troubleshooting

### Port Already in Use

If you see "port is already allocated" errors:

**Windows PowerShell:**
```powershell
Get-NetTCPConnection -LocalPort 5672 -State Listen
Stop-Process -Id <PID> -Force
```

Or stop all Docker containers first:
```bash
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

## Architecture

The application uses a microservices architecture with 9 services:

| Service | Port | Description |
|---|---|---|
| Order Service | 5001 | Order lifecycle, hospital auto-selection, inventory reservation |
| Drone Dispatch Service | 5002 | Dispatch orchestration, weather polling, mid-flight rerouting |
| Inventory Service | 5003 | Stock management with MySQL |
| Notification Service | 5004 | AMQP consumer, publishes to Twilio SMS |
| Hospital Service | 5005 | Hospital data with MySQL |
| Weather Service | 5006 | OpenWeatherMap API wrapper with simulation mode |
| Geolocation Service | 5007 | Google Maps API with in-memory coordinate cache |
| Drone Management Service | 5008 | Drone CRUD with MySQL |
| Route Planning Service | 5009 | Haversine distance + A* pathfinding |

**Infrastructure:**
- Kong API Gateway (8000/8001) - Centralized routing and CORS handling
- RabbitMQ (5672/15672) - Message broker for event-driven communication
- MySQL (3306/3307/3308) - Three separate databases for inventory, drone, and hospital data

## Technology Stack

- **Backend:** Python 3.11, Flask
- **Message Broker:** RabbitMQ 3.x (AMQP protocol)
- **Databases:** MySQL 8.0
- **API Gateway:** Kong 3.8
- **Frontend:** React 19, TypeScript, TanStack Suite (Router, Query, Table, Form)
- **Web Server:** Hono (Bun Runtime)
- **Containerization:** Docker, Docker Compose