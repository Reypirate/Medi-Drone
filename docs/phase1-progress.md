# Phase 1 Fixes Progress

This document tracks progress on Phase 1 fixes (adding observability without changing behavior).

**TO CONTINUE THESE FIXES**: Read the section below for the next fix and follow the steps exactly.

---

## Completed Fixes

### ✅ Fix 1: Request ID Tracking
- **Branch**: `fix/phase1-add-request-id-tracking`
- **Status**: Complete & Tested
- **Changes**:
  - Created `services/common/request_tracking.py` utility module
  - Updated Order Service to include request IDs in logs and AMQP headers
  - Added structured logging with request context
  - Updated Order Service Dockerfile to copy common module
  - Fixed output buffering issue (added `flush=True` to print statements)
- **Testing**:
  - Verified unique request IDs for each request (e.g., REQ-C69A61860CA2, REQ-9FA2A6B98CF1, REQ-DDEEA92F806A)
  - Verified request ID appears throughout entire request flow
  - Verified response headers include X-Request-ID
  - Tested successful orders and failed orders (NO_HOSPITAL_WITH_STOCK)

---

## Next Fix to Implement: Fix 2 - AMQP Connection Lifecycle Logging

### Step-by-Step Instructions

**STEP 1**: Switch to main branch and create new branch
```bash
git checkout main
git checkout -b fix/phase1-amqp-connection-logging
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
```

**STEP 7**: Commit changes
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

---

## Future Fixes (Not Yet Ready)

### Fix 3: active_missions Size Tracking
**WAIT** - Do not start until Fix 2 is complete and tested.

### Fix 4: Health Check Endpoints
**WAIT** - Do not start until Fix 3 is complete and tested.

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
- Test each fix independently before proceeding
- No behavioral changes - only observability
- Update this document after completing each fix
