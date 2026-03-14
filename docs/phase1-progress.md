# Phase 1 Fixes Progress

This document tracks progress on Phase 1 fixes (adding observability without changing behavior).

**TO CONTINUE THESE FIXES**: Read the section below for the next fix and follow the steps exactly.

**IMPORTANT**: A fix is only considered complete after:
1. Code changes are made
2. Services are rebuilt with `docker-compose up --build`
3. Logs are verified to show the new observability output
4. This document is updated with actual test results

---

## Fix Status Legend

| Status | Meaning |
|--------|---------|
| ⏳ **Code Complete** | Code changes written, NOT yet tested |
| ✅ **Complete & Tested** | Code changes written AND verified working |
| ❌ **Failed** | Code changes didn't work, needs revision |

---

## Current Fixes Status

### ⏳ Fix 1: Request ID Tracking
- **Branch**: `fix/phase1-add-request-id-tracking`
- **Status**: Code Complete, NOT Tested
- **Changes**:
  - Created `services/common/request_tracking.py` utility module
  - Updated Order Service to include request IDs in logs and AMQP headers
  - Added structured logging with request context
  - Updated Order Service Dockerfile to copy common module
- **To Test**: Run `docker-compose up --build` from the fix branch, then test order creation

### 🔲 Fix 2: AMQP Connection Lifecycle Logging
- **Branch**: Not started
- **Status**: Not started
- See detailed steps below

### 🔲 Fix 3: active_missions Size Tracking
- **Status**: Not started (blocked by Fix 2)

### 🔲 Fix 4: Health Check Endpoints
- **Status**: Not started (blocked by Fix 3)

---

## Next Fix to Implement: Fix 2 - AMQP Connection Lifecycle Logging

### Step-by-Step Instructions

**STEP 0**: **IMPORTANT - First test Fix 1**

Before starting Fix 2, verify Fix 1 actually works:

```bash
# Switch to Fix 1 branch
git checkout fix/phase1-add-request-id-tracking

# Stop existing services
docker-compose down

# Rebuild and start with Fix 1 changes
docker-compose up --build

# Wait 30 seconds for services to start
sleep 30

# Place a test order
curl -X POST http://localhost:8000/api/order/order \
  -H "Content-Type: application/json" \
  -d '{
    "item_id": "BLOOD-O-NEG",
    "quantity": 1,
    "urgency_level": "CRITICAL",
    "customer_coords": {"lat": 1.35, "lng": 103.8}
  }'

# Check logs for request ID tracking
docker-compose logs order | grep "REQ:"

# Expected output should include:
# [INFO] POST /order - Creating order: item_id=BLOOD-O-NEG... | REQ:REQ-XXXXXXXXXXXX
# [INFO] Generated order_id: ORD-XXXXXX | REQ:REQ-XXXXXXXXXXXX
# [INFO] Order ORD-XXXXXX CONFIRMED | REQ:REQ-XXXXXXXXXXXX
# [INFO] AMQP Published to orders/order.confirmed: ORD-XXXXXX | REQ:REQ-XXXXXXXXXXXX

# If you see the REQ: entries in logs, Fix 1 works. Update this document.
# If NOT, Fix 1 needs debugging before proceeding.
```

**STEP 1**: Only after Fix 1 is tested and working, switch to main and create new branch
```bash
git checkout main
git checkout -b fix/phase2-amqp-logging
```

**STEP 2**: Update `services/order/amqp_setup.py`

Find the `wait_for_rabbitmq` function and add logging. The file should look like this after changes:

```python
import os
import time
import pika

RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.environ.get("RABBITMQ_PORT", 5672))

EXCHANGES = {
    "orders": "topic",
    "notifications": "topic",
}


def wait_for_rabbitmq(max_retries=12, delay=5):
    for attempt in range(max_retries):
        try:
            print(f"  [AMQP] Attempting connection to {RABBITMQ_HOST}:{RABBITMQ_PORT} (attempt {attempt + 1}/{max_retries})...")
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT,
                                          heartbeat=300, blocked_connection_timeout=300)
            )
            print(f"  [AMQP] Connected successfully to {RABBITMQ_HOST}:{RABBITMQ_PORT}")
            return connection
        except pika.exceptions.AMQPConnectionError as e:
            print(f"  [AMQP] Connection failed: {e} - retrying in {delay}s...")
            time.sleep(delay)
    raise Exception("Could not connect to RabbitMQ after retries")


def setup_exchanges(channel):
    for exchange_name, exchange_type in EXCHANGES.items():
        try:
            channel.exchange_declare(exchange=exchange_name, exchange_type=exchange_type, durable=True)
            print(f"  [AMQP] Declared exchange: {exchange_name} ({exchange_type})")
        except Exception as e:
            print(f"  [AMQP] Failed to declare exchange {exchange_name}: {e}")
            raise


def get_connection():
    print(f"  [AMQP] Initializing AMQP connection...")
    connection = wait_for_rabbitmq()
    channel = connection.channel()
    setup_exchanges(channel)
    print(f"  [AMQP] AMQP initialization complete - channel and exchanges ready")
    return connection, channel
```

**STEP 3**: Copy the updated `amqp_setup.py` to the other two services:
```bash
cp services/order/amqp_setup.py services/drone_dispatch/amqp_setup.py
cp services/order/amqp_setup.py services/notification/amqp_setup.py
```

**STEP 4**: Update `services/drone_dispatch/drone_dispatch.py` - add logging to `start_consumer` function

Find the `start_consumer` function (around line 380-392) and update it:

```python
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
```

**STEP 5**: Update `services/notification/notification.py` - add logging to `start_consumer` function

Find the `start_consumer` function (around line 61-74) and update it:

```python
def start_consumer():
    """Start the AMQP consumer in a background thread."""
    print(f"  [AMQP] Starting notification consumer...")
    connection, channel = amqp_setup.get_connection()

    queue_name = "notification_queue"
    print(f"  [AMQP] Declaring queue: {queue_name} (durable=True)")
    channel.queue_declare(queue=queue_name, durable=True)

    print(f"  [AMQP] Binding queue '{queue_name}' to exchange 'notifications' with routing key 'notify.sms'")
    channel.queue_bind(exchange="notifications", queue=queue_name, routing_key="notify.sms")

    print(f"  [AMQP] Binding queue '{queue_name}' to exchange 'orders' with routing key 'order.failed'")
    channel.queue_bind(exchange="orders", queue=queue_name, routing_key="order.failed")

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=queue_name, on_message_callback=on_notification)

    print(f"  [AMQP] Listening for notification messages on queue '{queue_name}'...")
    channel.start_consuming()
```

**STEP 6**: Test the changes
```bash
# Stop existing services
docker-compose down

# Rebuild and start
docker-compose up --build

# Wait 30 seconds for services to start, then check logs
sleep 30

# Check for AMQP logging
docker-compose logs order | grep "\[AMQP\]"
docker-compose logs drone-dispatch | grep "\[AMQP\]"
docker-compose logs notification | grep "\[AMQP\]"
```

Expected output should include:
```
[AMQP] Attempting connection to rabbitmq:5672 (attempt 1/12)...
[AMQP] Connected successfully to rabbitmq:5672
[AMQP] Declared exchange: orders (topic)
[AMQP] Declared exchange: notifications (topic)
[AMQP] AMQP initialization complete - channel and exchanges ready
[AMQP] Starting consumer thread...
[AMQP] Declaring queue: dispatch_queue (durable=True)
[AMQP] Binding queue 'dispatch_queue' to exchange 'orders' with routing key 'order.confirmed'
[AMQP] Listening for order.confirmed events on queue 'dispatch_queue'...
```

**STEP 7**: Verify the drone-dispatch consumer actually starts (this was the bug we found)

```bash
# Check if drone-dispatch shows "Listening for order.confirmed events"
docker-compose logs drone-dispatch | grep "Listening"

# If this message is missing, the consumer thread failed to start
# This confirms the bug we identified earlier
```

**STEP 8**: Commit changes
```bash
git add -A
git commit -m "Phase 1 Fix: Add AMQP connection lifecycle logging

- Log connection attempts with attempt numbers
- Log successful connections with host:port
- Log exchange declarations
- Log queue declarations and bindings
- Log consumer startup

Services updated: order, drone_dispatch, notification"
```

**STEP 9**: Update this document with test results

Add actual test results to this section after running STEP 6:

```markdown
### ✅ Fix 2: AMQP Connection Lifecycle Logging
- **Branch**: `fix/phase2-amqp-logging`
- **Status**: Complete & Tested
- **Test Results**:
  - Date tested: YYYY-MM-DD
  - All AMQP logs appearing correctly
  - drone-dispatch consumer: [WORKING/NOT_WORKING]
```

---

## Quick Reference Commands

### Place a test order
```bash
curl -X POST http://localhost:8000/api/order/order \
  -H "Content-Type: application/json" \
  -d '{
    "item_id": "BLOOD-O-NEG",
    "quantity": 1,
    "urgency_level": "CRITICAL",
    "customer_coords": {"lat": 1.35, "lng": 103.8}
  }'
```

### Check logs by service
```bash
docker-compose logs order | tail -50
docker-compose logs drone-dispatch | tail -50
docker-compose logs notification | tail -50
```

### Restart specific service
```bash
docker-compose restart order
docker-compose restart drone-dispatch
docker-compose restart notification
```

### Check container status
```bash
docker-compose ps
```

---

## Important Reminders

- **NO co-author tags** in commit messages
- Each fix gets its own branch
- **A fix is NOT complete until tested**
- No behavioral changes - only observability
- Update this document with test results
- If tests fail, update document with error details before proceeding
