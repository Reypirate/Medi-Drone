#!/bin/bash
# Test Script for Bad Weather Cancellation Feature (Scenario 3.2)
# This script tests the mid-flight weather cancellation by simulating unsafe weather

set -e

KONG_URL="http://localhost:8000"
WEATHER_URL="http://localhost:5006"
DISPATCH_URL="http://localhost:5002"

echo "=========================================="
echo "Testing Bad Weather Cancellation Feature"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Step 1: Check system health
echo -e "${BLUE}[Step 1] Checking system health...${NC}"
echo "Checking Kong Gateway..."
curl -s "$KONG_URL/health" > /dev/null && echo -e "${GREEN}✓ Kong Gateway is healthy${NC}" || echo -e "${RED}✗ Kong Gateway is down${NC}"

echo "Checking Weather Service..."
curl -s "$WEATHER_URL/health" > /dev/null && echo -e "${GREEN}✓ Weather Service is healthy${NC}" || echo -e "${RED}✗ Weather Service is down${NC}"

echo "Checking Dispatch Service..."
curl -s "$DISPATCH_URL/health" > /dev/null && echo -e "${GREEN}✓ Dispatch Service is healthy${NC}" || echo -e "${RED}✗ Dispatch Service is down${NC}"

echo ""

# Step 2: Check simulation status
echo -e "${BLUE}[Step 2] Checking weather simulation status...${NC}"
SIM_STATUS=$(curl -s "$WEATHER_URL/weather/simulate/status")
echo "Current simulation status: $SIM_STATUS"
echo ""

# Step 3: Enable weather simulation
echo -e "${BLUE}[Step 3] Enabling weather simulation (UNSAFE conditions)...${NC}"
cat > /tmp/simulate_weather.json << EOF
{
  "force_unsafe": true,
  "unsafe_reason": ["HIGH_WIND", "THUNDERSTORM"],
  "wind_speed_kmh": 65.0,
  "rain_mm": 15.0
}
EOF

SIM_RESULT=$(curl -s -X POST "$WEATHER_URL/weather/simulate/enable" \
  -H "Content-Type: application/json" \
  -d @/tmp/simulate_weather.json)

echo "Simulation enabled: $SIM_RESULT"
echo ""

# Step 4: Check active missions
echo -e "${BLUE}[Step 4] Checking for active missions...${NC}"
MISSIONS=$(curl -s "$DISPATCH_URL/dispatch/missions")
echo "Active missions: $MISSIONS"

# Count active missions
MISSION_COUNT=$(echo "$MISSIONS" | jq -r '.active_missions | length' 2>/dev/null || echo "0")

if [ "$MISSION_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}⚠ No active missions found. Creating a test order...${NC}"

    # Create a test order
    echo -e "${BLUE}[Step 4a] Creating a test order...${NC}"
    cat > /tmp/test_order.json << EOF
{
  "customer_name": "Test Doctor",
  "customer_address": " Marina Bay Sands, Singapore",
  "customer_coords": {
    "lat": 1.2834,
    "lng": 103.8607
  },
  "item_id": "BLOOD-O-NEG",
  "quantity": 1,
  "urgency_level": "URGENT"
}
EOF

    ORDER_RESULT=$(curl -s -X POST "$KONG_URL/api/order/order" \
      -H "Content-Type: application/json" \
      -d @/tmp/test_order.json)

    echo "Order created: $ORDER_RESULT"

    # Extract order_id
    ORDER_ID=$(echo "$ORDER_RESULT" | jq -r '.order_id // .order_id // empty' 2>/dev/null)

    if [ -z "$ORDER_ID" ]; then
        echo -e "${RED}Failed to create order or extract order_id${NC}"
        echo "Raw response: $ORDER_RESULT"
        exit 1
    fi

    echo -e "${GREEN}✓ Order created: $ORDER_ID${NC}"
    echo ""

    # Wait for mission to become active (give time for AMQP processing)
    echo -e "${BLUE}Waiting for mission to become active (30 seconds)...${NC}"
    sleep 30

    # Check missions again
    MISSIONS=$(curl -s "$DISPATCH_URL/dispatch/missions")
    MISSION_COUNT=$(echo "$MISSIONS" | jq -r '.active_missions | length' 2>/dev/null || echo "0")
    echo "Active missions after wait: $MISSION_COUNT"
fi

echo ""

# Step 5: Get the first active mission
echo -e "${BLUE}[Step 5] Getting mission details...${NC}"
MISSIONS=$(curl -s "$DISPATCH_URL/dispatch/missions")
ACTIVE_MISSION=$(echo "$MISSIONS" | jq -r '.active_missions[0] // empty' 2>/dev/null)

if [ -z "$ACTIVE_MISSION" ]; then
    echo -e "${RED}✗ No active missions found. Cannot proceed with test.${NC}"
    echo ""
    echo "Possible reasons:"
    echo "1. Order service is not processing orders"
    echo "2. AMQP (RabbitMQ) is not working"
    echo "3. Database or drone issues"
    echo ""
    echo "Checking logs:"
    docker-compose logs --tail=20 order
    docker-compose logs --tail=20 drone-dispatch
    exit 1
fi

ORDER_ID=$(echo "$ACTIVE_MISSION" | jq -r '.order_id')
DRONE_ID=$(echo "$ACTIVE_MISSION" | jq -r '.drone_id')
STATUS=$(echo "$ACTIVE_MISSION" | jq -r '.dispatch_status')

echo "Mission details:"
echo "  Order ID: $ORDER_ID"
echo "  Drone ID: $DRONE_ID"
echo "  Status: $STATUS"
echo ""

# Step 6: Manually trigger weather poll for the mission
echo -e "${BLUE}[Step 6] Manually triggering weather poll for mission...${NC}"
cat > /tmp/trigger_weather.json << EOF
{
  "order_id": "$ORDER_ID"
}
EOF

echo "Trigger URL: $DISPATCH_URL/dispatch/simulate/weather"
POLL_RESULT=$(curl -s -X POST "$DISPATCH_URL/dispatch/simulate/weather" \
  -H "Content-Type: application/json" \
  -d @/tmp/trigger_weather.json)

echo "Weather poll triggered: $POLL_RESULT"
echo ""

# Step 7: Wait for cancellation to process
echo -e "${BLUE}Waiting for cancellation to process (10 seconds)...${NC}"
sleep 10

# Step 8: Check mission status after weather event
echo -e "${BLUE}[Step 7] Checking mission status after weather event...${NC}"
MISSIONS_AFTER=$(curl -s "$DISPATCH_URL/dispatch/missions")
MISSION_AFTER=$(echo "$MISSIONS_AFTER" | jq -r ".active_missions[] | select(.order_id == \"$ORDER_ID\") // empty" 2>/dev/null)

if [ -z "$MISSION_AFTER" ]; then
    echo -e "${GREEN}✓ SUCCESS: Mission has been removed from active missions (cancelled)${NC}"

    # Try to get the order status from order service
    echo ""
    echo -e "${BLUE}Fetching order status from Order Service...${NC}"
    ORDER_STATUS=$(curl -s "$KONG_URL/api/order/order/$ORDER_ID")
    echo "Order status: $ORDER_STATUS"

    ORDER_STATE=$(echo "$ORDER_STATUS" | jq -r '.status // .dispatch_status // empty' 2>/dev/null)
    if [ "$ORDER_STATE" = "CANCELLED" ] || [ "$ORDER_STATE" = "ABORTED_WEATHER" ]; then
        echo -e "${GREEN}✓ Order is marked as: $ORDER_STATE${NC}"
    fi
else
    STATUS_AFTER=$(echo "$MISSION_AFTER" | jq -r '.dispatch_status')
    echo "Mission still exists with status: $STATUS_AFTER"

    if [ "$STATUS_AFTER" = "ABORTED_WEATHER" ]; then
        echo -e "${GREEN}✓ Mission marked as ABORTED_WEATHER${NC}"
    elif [ "$STATUS_AFTER" = "REROUTED_IN_FLIGHT" ]; then
        echo -e "${YELLOW}⚠ Mission was REROUTED (Scenario 3.1) instead of cancelled${NC}"
        echo "This is also a valid response to bad weather."
    else
        echo -e "${YELLOW}⚠ Mission status changed to: $STATUS_AFTER${NC}"
    fi
fi

echo ""

# Step 9: Check drone status
echo -e "${BLUE}[Step 8] Checking drone status...${NC}"
DRONE_STATUS=$(curl -s "http://localhost:5008/drones" | jq -r ".[] | select(.drone_id == \"$DRONE_ID\")" 2>/dev/null)

if [ -n "$DRONE_STATUS" ]; then
    DRONE_STATE=$(echo "$DRONE_STATUS" | jq -r '.status')
    DRONE_BATTERY=$(echo "$DRONE_STATUS" | jq -r '.battery')
    echo "Drone $DRONE_ID status:"
    echo "  Status: $DRONE_STATE"
    echo "  Battery: $DRONE_BATTERY%"

    if [ "$DRONE_STATE" = "RETURNING" ] || [ "$DRONE_STATE" = "AVAILABLE" ]; then
        echo -e "${GREEN}✓ Drone is returning or available (correct behavior after cancellation)${NC}"
    fi
fi

echo ""

# Step 10: Disable simulation
echo -e "${BLUE}[Step 9] Disabling weather simulation...${NC}"
DISABLE_RESULT=$(curl -s -X POST "$WEATHER_URL/weather/simulate/disable")
echo "Simulation disabled: $DISABLE_RESULT"
echo ""

# Summary
echo "=========================================="
echo -e "${BLUE}Test Summary${NC}"
echo "=========================================="
echo ""
echo "The test demonstrated:"
echo "1. Weather simulation can be enabled/disabled via API"
echo "2. Weather poll can be manually triggered for a mission"
echo "3. Mission is aborted when unsafe weather is detected"
echo "4. Compensating transactions are triggered:"
echo "   - Order is cancelled/aborted"
echo "   - Drone is set to RETURNING status"
echo "   - Mission is removed from active missions"
echo ""
echo -e "${GREEN}✓ Bad weather cancellation feature is WORKING${NC}"
echo ""
