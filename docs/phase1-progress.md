# Phase 1 Fixes Progress

This document tracks progress on Phase 1 fixes (adding observability without changing behavior).

## Completed Fixes

### ✅ Fix 1: Request ID Tracking
- **Branch**: `fix/phase1-add-request-id-tracking`
- **Status**: Complete
- **Changes**:
  - Created `services/common/request_tracking.py` utility module
  - Updated Order Service to include request IDs in logs and AMQP headers
  - Added structured logging with request context
  - Updated Order Service Dockerfile to copy common module
- **Testing**: Not yet tested

## Remaining Phase 1 Fixes

### 🔄 Fix 2: AMQP Connection Lifecycle Logging
- **Branch**: `fix/phase1-amqp-connection-logging` (to be created)
- **Services to update**:
  - `services/order/order.py`
  - `services/drone_dispatch/drone_dispatch.py`
  - `services/notification/notification.py`
- **Changes needed**:
  - Add connection attempt logging with timestamps
  - Add disconnection/reconnection logging
  - Log queue declaration success/failure
  - Track number of active connections
- **Example logging needed**:
  ```
  [AMQP] Connecting to rabbitmq:5672...
  [AMQP] Connected successfully (conn_id: 123456)
  [AMQP] Declared exchange: orders (topic)
  [AMQP] Declared queue: dispatch_queue (bound to orders/order.confirmed)
  ```

### 🔄 Fix 3: active_missions Size Tracking
- **Branch**: `fix/phase1-missions-tracking` (to be created)
- **Service**: `services/drone_dispatch/drone_dispatch.py`
- **Changes needed**:
  - Log when mission is added to active_missions
  - Log when mission is removed from active_missions
  - Log current active_missions size on changes
  - Add periodic status log (every 30 seconds)
- **Example logging needed**:
  ```
  [MISSIONS] Added ORD-ABC123 to active_missions (count: 1)
  [MISSIONS] Removed ORD-ABC123 from active_missions (count: 0)
  [MISSIONS] Status: 0 active missions
  ```

### 🔄 Fix 4: Health Check Endpoints
- **Branch**: `fix/phase1-health-endpoints` (to be created)
- **Services**: All services
- **Changes needed**:
  - Add `/health` endpoint to each service
  - Include AMQP connection status in health check
  - Include database connection status (where applicable)
  - Return JSON with service name and status
- **Example response**:
  ```json
  {
    "service": "order",
    "status": "healthy",
    "amqp_connected": true,
    "details": {
      "amqp_host": "rabbitmq",
      "amqp_port": 5672
    }
  }
  ```

## How to Continue

1. **Switch to main branch**:
   ```bash
   git checkout main
   ```

2. **Create next branch**:
   ```bash
   git checkout -b fix/phase1-amqp-connection-logging
   ```

3. **Make changes** according to the fix description above

4. **Test changes**:
   ```bash
   docker-compose up --build
   # Check logs for new AMQP connection messages
   docker-compose logs order | grep AMQP
   docker-compose logs drone-dispatch | grep AMQP
   docker-compose logs notification | grep AMQP
   ```

5. **Commit changes** (remember: no co-author):
   ```bash
   git add -A
   git commit -m "Phase 1 Fix: Add AMQP connection lifecycle logging

   - Log connection attempts and results
   - Log exchange/queue declarations
   - Track active connections"
   ```

6. **Repeat** for remaining fixes

## Testing Commands

### Test Request ID Tracking (after Fix 1)
```bash
# Place an order and check logs include request ID
curl -X POST http://localhost:8000/api/order/order \
  -H "Content-Type: application/json" \
  -d '{
    "item_id": "BLOOD-O-NEG",
    "quantity": 1,
    "urgency_level": "CRITICAL",
    "customer_coords": {"lat": 1.35, "lng": 103.8}
  }'

# Check logs for request ID
docker-compose logs order | grep "REQ:"
```

### Test AMQP Logging (after Fix 2)
```bash
# Restart services and check startup logs
docker-compose restart order drone-dispatch notification
docker-compose logs order | grep "\[AMQP\]"
docker-compose logs drone-dispatch | grep "\[AMQP\]"
docker-compose logs notification | grep "\[AMQP\]"
```

### Test Missions Tracking (after Fix 3)
```bash
# Place an order and check mission tracking logs
curl -X POST http://localhost:8000/api/order/order \
  -H "Content-Type: application/json" \
  -d '{
    "item_id": "BLOOD-O-NEG",
    "quantity": 1,
    "urgency_level": "CRITICAL",
    "customer_coords": {"lat": 1.35, "lng": 103.8}
  }'

# Check logs for mission tracking
docker-compose logs drone-dispatch | grep "\[MISSIONS\]"
```

### Test Health Endpoints (after Fix 4)
```bash
curl http://localhost:5001/health
curl http://localhost:5002/health
curl http://localhost:5003/health
curl http://localhost:5004/health
curl http://localhost:5005/health
curl http://localhost:5006/health
curl http://localhost:5007/health
curl http://localhost:5008/health
curl http://localhost:5009/health
```

## Important Notes

- Each fix gets its own branch
- Test each fix independently before merging
- No behavioral changes - only observability
- Remember: NO co-author in commit messages
- Update this document as you complete fixes
