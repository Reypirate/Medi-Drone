# Medi-Drone Bug Fix Strategy

## Overview

This document outlines a safe, incremental approach to fixing identified bugs without breaking existing functionality.

## Guiding Principles

1. **One fix at a time** - No bundled changes
2. **Observability first** - Add logging before making changes
3. **Incremental deployment** - Each fix should be independently testable
4. **Backward compatible** - New features should coexist with old behavior temporarily
5. **Rollback ready** - Each commit should be easily revertable

## Risk-Based Fix Order

### Phase 1: No-Risk Observation (Start Here)
**Goal**: Add visibility without changing behavior

| Issue | Action | Risk |
|-------|--------|------|
| All | Add structured logging with request IDs | NONE |
| All | Add health check endpoints for AMQP connection status | NONE |
| Drone Dispatch | Log active_missions size changes | NONE |
| All Services | Add startup logging showing configuration | NONE |

**Why start here**: These changes add visibility to help verify fixes later work correctly, and cannot break anything.

### Phase 2: Isolated Low-Risk Fixes
**Goal**: Fix issues that don't affect cross-service behavior

| Issue | File | Fix Strategy |
|-------|------|--------------|
| Duplicate amqp_setup.py | Multiple services | Create shared utility module |
| Max quantity validation | order/order.py | Add simple check, no service calls |
| Inventory release quantity bug | inventory/inventory.py | Fix conditional logic |
| Hardcoded constants | Multiple files | Create shared constants module |

**Why these are safe**: Each is contained within one service and doesn't change message formats or API contracts.

### Phase 3: Medium-Risk Fixes with Monitoring
**Goal**: Fix issues requiring careful testing

| Issue | File | Fix Strategy | Validation |
|-------|------|--------------|------------|
| AMQP connection leaks | order/order.py | Add connection manager with proper lifecycle | Monitor connection count, test reconnect |
| Graceful AMQP shutdown | All consumers | Add signal handlers for SIGTERM | Test container stop/restart |
| SQL dynamic queries | drone_management/drone_management.py | Use whitelist + parameterized queries | Run existing operations, verify same results |

**Why medium risk**: These touch core infrastructure but have clear validation criteria.

### Phase 4: High-Risk Concurrency Fixes
**Goal**: Fix race conditions with careful analysis

| Issue | File | Fix Strategy |
|-------|------|--------------|
| active_missions race condition | drone_dispatch/drone_dispatch.py | Use threading.Lock or replace with thread-safe structure |
| Memory leak (completed missions) | drone_dispatch/drone_dispatch.py | Add mission completion endpoint and cleanup |

**Why high risk**: Concurrency bugs are subtle. Need to:
1. Add extensive logging first
2. Reproduce the issue if possible
3. Add lock/structure incrementally
4. Load test before and after

### Phase 5: Architecture Improvements (Optional)
**Goal**: Long-term improvements after bugs are fixed

| Issue | Approach |
|-------|----------|
| Database connection pooling | Add SQLAlchemy or connection pool |
| Request tracing | Add correlation IDs through AMQP headers |
| Silent fallback improvements | Add metrics and alerting |

## Detailed Fix Strategies

### Fix 1: Thread-Safe active_missions (High Priority)

**Current Problem**: Dictionary modified concurrently without locks.

**Safe Approach**:
```python
# Add at module level
import threading
missions_lock = threading.Lock()

# Wrap all access:
with missions_lock:
    # read or modify active_missions
```

**Rollback Plan**: Keep dict as-is, add lock around all access paths. If lock causes performance issues, we can optimize later.

**Testing**:
1. Start service
2. Place order
3. Immediately call simulate endpoint
4. Verify no "dictionary changed size" errors in logs

### Fix 2: AMQP Connection Lifecycle

**Current Problem**: Connections created but never closed.

**Safe Approach**:
```python
# Create connection manager class
class AMQPConnectionManager:
    def __init__(self):
        self._connection = None
        self._channel = None
        self._lock = threading.Lock()

    def get_channel(self):
        with self._lock:
            if self._channel is None or self._channel.is_closed:
                self._reconnect()
            return self._channel

    def close(self):
        with self._lock:
            if self._connection:
                self._connection.close()

# Add graceful shutdown
import signal
def signal_handler(signum, frame):
    amqp_manager.close()
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
```

**Rollback Plan**: Keep existing code path, add manager as optional wrapper. Can revert to old behavior by removing manager usage.

### Fix 3: Memory Leak - Mission Cleanup

**Current Problem**: Completed missions never removed.

**Safe Approach**:
```python
# Add new endpoint for mission completion
@app.route("/dispatch/missions/<order_id>/complete", methods=["POST"])
def complete_mission(order_id):
    with missions_lock:
        if order_id in active_missions:
            del active_missions[order_id]
    return jsonify({"status": "COMPLETED"})

# For now, log when missions would be cleaned up
# Can be called by external system or add timeout-based cleanup
```

**Rollback Plan**: New endpoint is additive. Doesn't break existing flows.

### Fix 4: Quantity Validation

**Current Problem**: No max quantity check.

**Safe Approach**:
```python
# Add in create_order()
MAX_QUANTITY_PER_ORDER = 100  # Make configurable via env var
quantity = data.get("quantity", 1)
if quantity <= 0 or quantity > MAX_QUANTITY_PER_ORDER:
    return jsonify({"status": "FAILED", "reason": "INVALID_QUANTITY"}), 400
```

**Rollback Plan**: Simple validation, easy to adjust threshold or remove.

## Testing Strategy

### Before Each Fix
1. Start services: `docker-compose up`
2. Run manual test: Place order via UI
3. Verify end-to-end flow works
4. Save working state as baseline

### After Each Fix
1. Restart services
2. Run same manual test
3. Verify same behavior + bug is fixed
4. Check logs for new errors

### Integration Tests
Create simple test script:
```bash
#!/bin/bash
# test-basic-flow.sh

# 1. Check all services are healthy
curl -f http://localhost:8001/health || exit 1

# 2. Place an order
ORDER_ID=$(curl -s -X POST http://localhost:8000/api/order/order \
  -H "Content-Type: application/json" \
  -d '{"item_id":"BLOOD-O-NEG","quantity":2,"urgency_level":"CRITICAL","customer_coords":{"lat":1.35,"lng":103.8}}' \
  | jq -r '.order_id')

# 3. Verify order confirmed
curl -s http://localhost:8000/api/order/order/$ORDER_ID | jq '.status'

# 4. Verify drone dispatched
sleep 5
curl -s http://localhost:8000/api/dispatch/dispatch/missions | jq '.active_missions | length'

echo "Basic flow test passed!"
```

## Deployment Strategy

1. **Branch per fix**: Each fix gets its own branch
2. **Test locally**: Docker compose test environment
3. **Merge to main**: Only after manual testing passes
4. **Tag releases**: Tag after each phase completion

## Rollback Plan

If a fix breaks something:
1. Revert the specific commit: `git revert <commit>`
2. Restart services: `docker-compose down && docker-compose up`
3. Verify baseline functionality restored
4. File issue for re-analysis

## Success Criteria

- ✅ All services start without errors
- ✅ Order flow works end-to-end
- ✅ No "dictionary changed size" errors
- ✅ AMQP connections stay stable (no continuous growth)
- ✅ Memory usage stable over time
- ✅ All existing scenarios still work

## Timeline Estimate

| Phase | Time Estimate | Dependencies |
|-------|---------------|--------------|
| Phase 1: Observation | 2 hours | None |
| Phase 2: Low-risk fixes | 4 hours | Phase 1 |
| Phase 3: Medium-risk fixes | 6 hours | Phase 2 |
| Phase 4: Concurrency fixes | 8 hours | Phase 3 |
| **Total** | **20 hours** | Sequential |

## Next Steps

1. **Start with Phase 1** - Add logging and observability
2. **Create test script** - Automate baseline testing
3. **Fix one issue at a time** - Don't bundle changes
4. **Commit frequently** - Small, revertable commits
5. **Test after each fix** - Verify no regression
