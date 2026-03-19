const API_BASE = window.location.protocol + "//" + window.location.hostname + ":8000";
const WEATHER_URL = API_BASE;  // All routes go through Kong gateway
const DISPATCH_URL = window.location.protocol + "//" + window.location.hostname + ":5002";  // Direct service URL
const WEATHER_DIRECT_URL = window.location.protocol + "//" + window.location.hostname + ":5006";  // Direct service URL

let selectedUrgency = "CRITICAL";
let pollInterval = null;
let addressMode = "postalcode";
let validatedAddress = null;
let addressConfirmed = false;
let currentOrderTab = "active";
let deletePendingOrderId = null;

// ── Urgency selector ──────────────────────────────────────────────

function setUrgency(el) {
    document.querySelectorAll(".urgency-btn").forEach(b => b.classList.remove("active"));
    el.classList.add("active");
    selectedUrgency = el.dataset.level;
}

// ── Logging ───────────────────────────────────────────────────────

function addLog(message, type) {
    const area = document.getElementById("log-area");
    if (area.querySelector(".empty-state")) area.innerHTML = "";

    const time = new Date().toLocaleTimeString();
    const entry = document.createElement("div");
    entry.className = "notif-entry";
    entry.innerHTML = `<span class="notif-time">[${time}]</span> <span class="notif-msg">${message}</span>`;
    area.prepend(entry);
}

// ── Retry helper with exponential backoff ──────────────────────────

async function fetchWithRetry(url, options = {}, maxRetries = 3) {
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            const resp = await fetch(url, options);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            return await resp.json();
        } catch (e) {
            const isLastAttempt = attempt === maxRetries;
            const delayMs = Math.min(1000 * Math.pow(2, attempt - 1), 5000);

            console.error(`[Inventory Load Error] Attempt ${attempt}/${maxRetries} failed: ${e.message}`);

            if (isLastAttempt) {
                throw new Error(`Failed after ${maxRetries} attempts: ${e.message}`);
            }

            await new Promise(resolve => setTimeout(resolve, delayMs));
        }
    }
}

// ── Load inventory on page load ──────────────────────────────────

async function loadInventory() {
    const select = document.getElementById("item-select");
    const FALLBACK_ITEMS = [
        { item_id: "BLOOD-O-NEG", name: "O-Negative Blood Bags", total_quantity: "?" },
        { item_id: "BLOOD-A-POS", name: "A-Positive Blood Bags", total_quantity: "?" },
        { item_id: "BLOOD-B-POS", name: "B-Positive Blood Bags", total_quantity: "?" },
        { item_id: "DEFIB-01", name: "Portable Defibrillator", total_quantity: "?" },
        { item_id: "EPINEPHRINE-01", name: "Epinephrine Auto-Injector", total_quantity: "?" },
        { item_id: "ORGAN-KIT-01", name: "Organ Transport Kit", total_quantity: "?" }
    ];

    try {
        const items = await fetchWithRetry(`${API_BASE}/api/inventory/inventory/items`);
        select.innerHTML = items.map(i =>
            `<option value="${i.item_id}">${i.name} (${i.item_id}) - Total: ${i.total_quantity}</option>`
        ).join("");
        addLog(`Loaded ${items.length} medical supply types`, "info");
    } catch (e) {
        console.error("[Inventory Load Error] Using fallback items due to:", e);
        select.innerHTML = FALLBACK_ITEMS.map(i =>
            `<option value="${i.item_id}">${i.name} (${i.item_id}) - Total: ${i.total_quantity}</option>`
        ).join("");
        addLog(`Inventory API unavailable - using fallback list (${FALLBACK_ITEMS.length} items)`, "warn");
    }
}

// ── Address mode switching ────────────────────────────────────────

function setAddressMode(mode) {
    addressMode = mode;
    document.getElementById("tab-postalcode").classList.toggle("active", mode === "postalcode");
    document.getElementById("tab-latlng").classList.toggle("active", mode === "latlng");
    document.getElementById("fields-postalcode").classList.toggle("hidden", mode !== "postalcode");
    document.getElementById("fields-latlng").classList.toggle("hidden", mode !== "latlng");
    clearAddressValidation();
}

// ── Current location ───────────────────────────────────────────────

async function getCurrentLocation() {
    const btn = document.getElementById("location-btn");
    btn.disabled = true;
    btn.textContent = "Getting location...";

    if (!navigator.geolocation) {
        addLog("Geolocation is not supported by your browser", "error");
        btn.disabled = false;
        btn.innerHTML = "&#128205; Use My Current Location";
        return;
    }

    navigator.geolocation.getCurrentPosition(
        async (position) => {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;

            // Switch to lat/lng mode and fill in the coordinates
            setAddressMode("latlng");
            document.getElementById("input-lat").value = lat.toFixed(6);
            document.getElementById("input-lng").value = lng.toFixed(6);

            addLog(`Current location: ${lat.toFixed(4)}, ${lng.toFixed(4)}`, "info");

            // Auto-check the address
            await checkAddress();

            btn.disabled = false;
            btn.innerHTML = "&#128205; Use My Current Location";
        },
        (error) => {
            let errorMsg = "Unable to get location";
            switch (error.code) {
                case error.PERMISSION_DENIED:
                    errorMsg = "Location access denied. Please enable location services.";
                    break;
                case error.POSITION_UNAVAILABLE:
                    errorMsg = "Location information unavailable.";
                    break;
                case error.TIMEOUT:
                    errorMsg = "Location request timed out.";
                    break;
            }
            addLog(errorMsg, "error");
            btn.disabled = false;
            btn.innerHTML = "&#128205; Use My Current Location";
        }
    );
}

// ── Address validation ────────────────────────────────────────────

function clearAddressValidation() {
    validatedAddress = null;
    addressConfirmed = false;
    const preview = document.getElementById("address-preview");
    preview.className = "address-preview";
    preview.style.display = "none";
    preview.innerHTML = "";
    updateSubmitButton();
}

function updateSubmitButton() {
    const btn = document.getElementById("submit-btn");
    if (addressConfirmed && validatedAddress && validatedAddress.region_valid) {
        btn.disabled = false;
        btn.textContent = "Submit Emergency Order";
    } else if (validatedAddress && !validatedAddress.region_valid) {
        btn.disabled = true;
        btn.textContent = "Address out of delivery range";
    } else if (validatedAddress && !addressConfirmed) {
        btn.disabled = true;
        btn.textContent = "Confirm address to submit";
    } else {
        btn.disabled = true;
        btn.textContent = "Check address to submit";
    }
}

async function checkAddress() {
    const checkBtn = document.getElementById("check-btn");
    checkBtn.disabled = true;
    checkBtn.textContent = "Checking...";
    clearAddressValidation();

    let url;

    if (addressMode === "postalcode") {
        const postalCode = document.getElementById("postal-code").value.trim();
        if (!postalCode) {
            addLog("Please enter a postal code", "warn");
            checkBtn.disabled = false;
            checkBtn.textContent = "Check Address";
            return;
        }
        const params = new URLSearchParams({ address: postalCode + " Singapore", region: "sg" });
        url = `${API_BASE}/api/geolocation/maps/api/geocode/json?${params}`;
    } else {
        const lat = parseFloat(document.getElementById("input-lat").value);
        const lng = parseFloat(document.getElementById("input-lng").value);
        if (isNaN(lat) || isNaN(lng)) {
            addLog("Please enter valid latitude and longitude", "warn");
            checkBtn.disabled = false;
            checkBtn.textContent = "Check Address";
            return;
        }
        const params = new URLSearchParams({ lat, lng });
        url = `${API_BASE}/api/geolocation/maps/api/reverse-geocode?${params}`;
    }

    try {
        const resp = await fetch(url);
        const data = await resp.json();

        if (!resp.ok) {
            const detail = data.detail || data.error || "Geocoding service error";
            const hint = data.api_status === "REQUEST_DENIED"
                ? " Please enable the Geocoding API in Google Cloud Console."
                : "";
            showAddressPreview(null, detail + hint);
            addLog(`Address check failed: ${detail}`, "error");
            return;
        }

        if (!data.customer_coords) {
            showAddressPreview(null, "Could not resolve this address. Please try again.");
            addLog("Address resolution failed", "error");
            return;
        }

        validatedAddress = data;

        if (addressMode === "postalcode") {
            const details = document.getElementById("postal-details").value.trim();
            if (details) {
                validatedAddress.additional_details = details;
            }
        }

        if (data.region_valid) {
            showAddressPreview(data, null);
            addLog(`Address resolved: ${data.formatted_address} (${data.country})`, "success");
        } else {
            showAddressPreview(data, "This address is outside Singapore's drone delivery zone.");
            addLog(`Address REJECTED: ${data.formatted_address} — outside Singapore (${data.country})`, "error");
        }
    } catch (e) {
        showAddressPreview(null, `Validation service unavailable: ${e.message}`);
        addLog(`Address check error: ${e.message}`, "error");
    } finally {
        checkBtn.disabled = false;
        checkBtn.textContent = "Check Address";
        updateSubmitButton();
    }
}

function confirmAddress() {
    addressConfirmed = true;
    const preview = document.getElementById("address-preview");
    preview.className = "address-preview confirmed";

    const data = validatedAddress;
    const mapsUrl = `https://www.google.com/maps?q=${data.customer_coords.lat},${data.customer_coords.lng}`;

    preview.innerHTML = `
        <div class="preview-title">&#10003; Address Confirmed</div>
        <div class="preview-grid">
            <div>Address:</div><div class="val">${data.formatted_address}</div>
            <div>Coordinates:</div><div class="val">${data.customer_coords.lat}, ${data.customer_coords.lng}</div>
            ${data.postal_code ? `<div>Postal Code:</div><div class="val">${data.postal_code}</div>` : ""}
            <div>Country:</div><div class="val">${data.country || "Singapore"}</div>
        </div>
        <a class="gmaps-link" href="${mapsUrl}" target="_blank" rel="noopener">View on Google Maps &rarr;</a>
    `;

    addLog("Address confirmed by user", "success");
    updateSubmitButton();
}

function showAddressPreview(data, errorMessage) {
    const preview = document.getElementById("address-preview");

    if (!data || (errorMessage && !data)) {
        preview.className = "address-preview invalid";
        preview.style.display = "block";
        preview.innerHTML = `
            <div class="preview-title">Address Validation Failed</div>
            <div style="color: #f87171;">${errorMessage}</div>
        `;
        return;
    }

    const isValid = data.region_valid;
    preview.className = `address-preview ${isValid ? "valid" : "invalid"}`;
    preview.style.display = "block";

    const mapsUrl = `https://www.google.com/maps?q=${data.customer_coords.lat},${data.customer_coords.lng}`;

    if (isValid) {
        preview.innerHTML = `
            <div class="preview-title">&#10003; Resolved Address — Within Singapore delivery zone</div>
            <div class="preview-grid">
                <div>Address:</div><div class="val">${data.formatted_address}</div>
                <div>Coordinates:</div><div class="val">${data.customer_coords.lat}, ${data.customer_coords.lng}</div>
                ${data.postal_code ? `<div>Postal Code:</div><div class="val">${data.postal_code}</div>` : ""}
                <div>Country:</div><div class="val">${data.country || "Singapore"}</div>
                <div>Source:</div><div class="val">${data.source}</div>
            </div>
            <a class="gmaps-link" href="${mapsUrl}" target="_blank" rel="noopener">View on Google Maps &rarr;</a>
            <button class="confirm-btn" onclick="confirmAddress()">Confirm Address</button>
        `;
    } else {
        preview.innerHTML = `
            <div class="preview-title">&#10007; REJECTED — ${errorMessage || "Outside delivery zone"}</div>
            <div class="preview-grid">
                <div>Address:</div><div class="val">${data.formatted_address}</div>
                <div>Country:</div><div class="val">${data.country || "Unknown"}</div>
                <div>Coordinates:</div><div class="val">${data.customer_coords.lat}, ${data.customer_coords.lng}</div>
            </div>
            <a class="gmaps-link" href="${mapsUrl}" target="_blank" rel="noopener">View on Google Maps &rarr;</a>
        `;
    }
}

// ── Submit order ──────────────────────────────────────────────────

async function submitOrder() {
    if (!addressConfirmed || !validatedAddress || !validatedAddress.region_valid) {
        addLog("Please check and confirm the delivery address first", "warn");
        return;
    }

    const btn = document.getElementById("submit-btn");
    btn.disabled = true;
    btn.textContent = "Submitting...";

    let customerAddress = validatedAddress.formatted_address;
    if (validatedAddress.additional_details) {
        customerAddress = validatedAddress.additional_details + ", " + customerAddress;
    }

    const payload = {
        item_id: document.getElementById("item-select").value,
        quantity: parseInt(document.getElementById("quantity").value),
        urgency_level: selectedUrgency,
        customer_address: customerAddress,
        customer_coords: validatedAddress.customer_coords,
    };

    addLog(`Submitting order: ${payload.item_id} x${payload.quantity}...`, "info");

    try {
        const resp = await fetch(`${API_BASE}/api/order/order`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();

        if (resp.ok) {
            const hospInfo = data.hospital_name ? ` from ${data.hospital_name}` : "";
            addLog(`Order ${data.order_id} CONFIRMED${hospInfo}. Awaiting dispatch...`, "success");
        } else {
            addLog(`Order FAILED: ${data.reason || data.message || "Unknown error"}`, "error");
        }

        setTimeout(refreshOrders, 1500);
    } catch (e) {
        addLog(`Error: ${e.message}`, "error");
    } finally {
        btn.disabled = false;
        updateSubmitButton();
    }
}

// ── Order tabs ─────────────────────────────────────────────────────

function setOrderTab(tab) {
    currentOrderTab = tab;
    document.getElementById("tab-active").classList.toggle("active", tab === "active");
    document.getElementById("tab-cancelled").classList.toggle("active", tab === "cancelled");
    document.getElementById("tab-completed").classList.toggle("active", tab === "completed");

    // Show Delete All button only for cancelled and completed tabs
    const deleteAllBtn = document.getElementById("delete-all-btn");
    if (tab === "cancelled" || tab === "completed") {
        deleteAllBtn.style.display = "inline-block";
    } else {
        deleteAllBtn.style.display = "none";
    }

    refreshOrders();
}

// ── Delete order with confirmation ───────────────────────────────────

function showDeleteDialog(orderId, orderInfo) {
    deletePendingOrderId = orderId;
    const messageEl = document.getElementById("confirm-message");
    const confirmBtn = document.getElementById("confirm-delete-btn");

    messageEl.textContent = `Are you sure you want to delete order ${orderId}? This action cannot be undone.`;
    confirmBtn.onclick = () => confirmDeleteOrder();
    document.getElementById("confirm-dialog").classList.remove("hidden");
}

function closeConfirmDialog() {
    deletePendingOrderId = null;
    deleteAllMode = false;
    document.getElementById("confirm-dialog").classList.add("hidden");
}

async function confirmDeleteOrder() {
    if (!deletePendingOrderId) return;

    try {
        const resp = await fetch(`${API_BASE}/api/order/order/${deletePendingOrderId}`, {
            method: "DELETE"
        });

        if (resp.ok) {
            addLog(`Order ${deletePendingOrderId} deleted`, "success");
            refreshOrders();
        } else {
            const data = await resp.json();
            addLog(`Delete failed: ${data.error || data.message}`, "error");
        }
    } catch (e) {
        addLog(`Error deleting order: ${e.message}`, "error");
    } finally {
        closeConfirmDialog();
    }
}

// ── Delete all orders in current tab ───────────────────────────────

let deleteAllMode = false;

function deleteAllOrders() {
    deleteAllMode = true;
    const messageEl = document.getElementById("confirm-message");
    const confirmBtn = document.getElementById("confirm-delete-btn");

    const tabName = currentOrderTab === "cancelled" ? "cancelled" : "completed";
    messageEl.textContent = `Are you sure you want to delete ALL ${tabName} orders? This action cannot be undone.`;
    confirmBtn.onclick = () => confirmDeleteAllOrders();
    document.getElementById("confirm-dialog").classList.remove("hidden");
}

async function confirmDeleteAllOrders() {
    try {
        let url = `${API_BASE}/api/order/orders`;
        if (currentOrderTab !== "active") {
            url += `?status=${currentOrderTab}`;
        }

        const resp = await fetch(url);
        const data = await resp.json();
        let orders = data.orders || [];

        if (currentOrderTab === "active") {
            orders = orders.filter(o => o.status === "DISPATCHED" || o.status === "IN_TRANSIT");
        }

        if (orders.length === 0) {
            addLog(`No ${currentOrderTab} orders to delete`, "info");
            closeConfirmDialog();
            return;
        }

        // Delete all orders in parallel
        const deletePromises = orders.map(async (order) => {
            try {
                const deleteResp = await fetch(`${API_BASE}/api/order/order/${order.order_id}`, {
                    method: "DELETE"
                });
                return { orderId: order.order_id, success: deleteResp.ok };
            } catch (e) {
                return { orderId: order.order_id, success: false, error: e.message };
            }
        });

        const results = await Promise.all(deletePromises);
        const successCount = results.filter(r => r.success).length;
        const failCount = results.length - successCount;

        if (failCount === 0) {
            addLog(`Deleted ${successCount} ${currentOrderTab} order(s)`, "success");
        } else {
            addLog(`Deleted ${successCount} order(s), ${failCount} failed`, "warn");
        }

        refreshOrders();
    } catch (e) {
        addLog(`Error deleting orders: ${e.message}`, "error");
    } finally {
        deleteAllMode = false;
        closeConfirmDialog();
    }
}

// ── Refresh orders ────────────────────────────────────────────────

async function refreshOrders() {
    try {
        let url = `${API_BASE}/api/order/orders`;
        if (currentOrderTab !== "active") {
            url += `?status=${currentOrderTab}`;
        }

        const resp = await fetch(url);
        const data = await resp.json();
        let orders = data.orders || [];

        // For active tab, also filter by status
        if (currentOrderTab === "active") {
            orders = orders.filter(o => ["CONFIRMED", "DISPATCHED", "IN_TRANSIT"].includes(o.status));
        }

        const list = document.getElementById("orders-list");

        if (orders.length === 0) {
            const emptyMessages = {
                active: "No active orders. Submit a delivery request to get started.",
                cancelled: "No cancelled orders.",
                completed: "No completed orders yet."
            };
            list.innerHTML = `<div class="empty-state">${emptyMessages[currentOrderTab]}</div>`;
            return;
        }

        // Update active count in header
        if (currentOrderTab === "active") {
            document.getElementById("active-count").textContent = `${orders.length} active mission${orders.length !== 1 ? "s" : ""}`;
        }

        const canDelete = currentOrderTab !== "active";

        list.innerHTML = orders.reverse().map(o => {
            const badgeClass = getBadgeClass(o.status);

            // Display ETA countdown for dispatched orders
            let etaDisplay = "";
            if (o.eta_minutes !== undefined && o.eta_minutes !== null) {
                const eta = Math.max(0, o.eta_minutes);
                etaDisplay = `<div>ETA: <span class="order-detail-value" style="color:${eta <= 5 ? '#f87171' : eta <= 10 ? '#fbbf24' : '#4ade80'}">${eta} min</span></div>`;
                if (eta <= 0 && o.status !== "DELIVERED") {
                    etaDisplay += `<div style="color:#4ade80; font-size:11px; grid-column:1/-1;">&#10003; Delivered!</div>`;
                }
            }

            // Display reroute details if available
            let rerouteDetailsHtml = "";
            if (o.dispatch_status === "REROUTED_IN_FLIGHT" || o.reroute_details) {
                rerouteDetailsHtml = displayRerouteDetails(o);
            }

            return `
                <div class="order-card">
                    <div class="order-header">
                        <span class="order-id">${o.order_id}</span>
                        <span class="badge ${badgeClass}">${o.status}</span>
                        ${canDelete ? `<button class="delete-btn" onclick="showDeleteDialog('${o.order_id}')">Delete</button>` : ""}
                    </div>
                    <div class="order-details">
                        <div>Hospital: <span class="order-detail-value">${o.hospital_name || o.hospital_id || "Auto"}</span></div>
                        <div>Item: <span class="order-detail-value">${o.item_id}</span></div>
                        <div>Qty: <span class="order-detail-value">${o.quantity}</span></div>
                        <div>Urgency: <span class="order-detail-value">${o.urgency_level}</span></div>
                        ${o.drone_id ? `<div>Drone: <span class="order-detail-value">${o.drone_id}</span></div>` : ""}
                        ${etaDisplay}
                        ${o.dispatch_status ? `<div>Dispatch: <span class="order-detail-value">${o.dispatch_status}</span></div>` : ""}
                        ${o.route_id ? `<div>Route: <span class="order-detail-value">${o.route_id}</span></div>` : ""}
                        ${o.cancel_message ? `<div style="grid-column:1/-1; margin-top:4px; padding:8px; background:rgba(239,68,68,0.08); border-radius:6px; color:#f87171; font-size:12px;">${o.cancel_message}</div>` : ""}
                    </div>
                    ${rerouteDetailsHtml}
                </div>
            `;
        }).join("");
    } catch (e) {
        addLog(`Failed to refresh orders: ${e.message}`, "error");
    }
}

function getBadgeClass(status) {
    if (!status) return "badge-pending";
    const s = status.toUpperCase();
    if (s === "CONFIRMED") return "badge-confirmed";
    if (s === "DISPATCHED") return "badge-dispatched";
    if (s === "IN_TRANSIT") return "badge-transit";
    if (s === "DELIVERED") return "badge-delivered";
    if (s.includes("REROUTE")) return "badge-rerouted";
    if (s.includes("FAIL") || s.includes("ERROR")) return "badge-failed";
    if (s.includes("CANCEL")) return "badge-cancelled";
    return "badge-pending";
}

// ── SMS notification log ──────────────────────────────────────────

async function refreshNotifications() {
    try {
        const resp = await fetch(`${API_BASE}/api/notification/notifications/log`);
        if (!resp.ok) return;
        const data = await resp.json();
        const notifications = data.notifications || [];

        const area = document.getElementById("sms-log");
        if (notifications.length === 0) return;

        area.innerHTML = notifications.reverse().map(n =>
            `<div class="notif-entry"><span class="notif-time">[${n.status}]</span> <span class="notif-msg">${n.body || "N/A"}</span></div>`
        ).join("");
    } catch (e) {
        // Silently ignore
    }
}

// ── Page navigation ──────────────────────────────────────────────

let searchItemsLoaded = false;
let hospitalNameCache = null;
let selectedMissionId = null;

function navigateTo(page) {
    const pages = ["dashboard", "inventory", "drones", "simulation"];
    pages.forEach(p => {
        document.getElementById(`page-${p}`).classList.toggle("page-hidden", p !== page);
        document.getElementById(`nav-${p}`).classList.toggle("active", p === page);
    });

    if (page === "inventory" && !searchItemsLoaded) loadSearchItems();
    if (page === "drones") loadDrones();
    if (page === "simulation") {
        refreshSimulationStatus();
        refreshActiveMissions();
    }
}

async function loadSearchItems() {
    const select = document.getElementById("search-item-select");
    const FALLBACK_ITEMS = [
        { item_id: "BLOOD-O-NEG", name: "O-Negative Blood Bags" },
        { item_id: "BLOOD-A-POS", name: "A-Positive Blood Bags" },
        { item_id: "BLOOD-B-POS", name: "B-Positive Blood Bags" },
        { item_id: "DEFIB-01", name: "Portable Defibrillator" },
        { item_id: "EPINEPHRINE-01", name: "Epinephrine Auto-Injector" },
        { item_id: "ORGAN-KIT-01", name: "Organ Transport Kit" }
    ];

    try {
        const items = await fetchWithRetry(`${API_BASE}/api/inventory/inventory/items`);
        select.innerHTML = '<option value="">-- Select an item --</option>' + items.map(i =>
            `<option value="${i.item_id}" data-name="${i.name}">${i.name} (${i.item_id})</option>`
        ).join("");
        searchItemsLoaded = true;
    } catch (e) {
        console.error("[Search Items Load Error] Using fallback items due to:", e);
        select.innerHTML = '<option value="">-- Select an item --</option>' + FALLBACK_ITEMS.map(i =>
            `<option value="${i.item_id}" data-name="${i.name}">${i.name} (${i.item_id})</option>`
        ).join("");
        searchItemsLoaded = true;
    }
}

async function fetchHospitalNames() {
    if (hospitalNameCache) return hospitalNameCache;
    try {
        const resp = await fetch(`${API_BASE}/api/hospitals/hospitals`);
        const data = await resp.json();
        const hospitals = Array.isArray(data) ? data : data.hospitals || [];
        const map = {};
        hospitals.forEach(h => { map[h.hospital_id] = h.name; });
        hospitalNameCache = map;
        return map;
    } catch (e) {
        return {};
    }
}

async function searchInventory() {
    const select = document.getElementById("search-item-select");
    const itemId = select.value;
    const summaryEl = document.getElementById("search-summary");
    const resultsEl = document.getElementById("search-results");

    if (!itemId) {
        summaryEl.innerHTML = "";
        resultsEl.innerHTML = '<div class="empty-state">Select a medical supply to see hospital stock levels.</div>';
        return;
    }

    summaryEl.innerHTML = "Loading...";
    resultsEl.innerHTML = "";

    try {
        const [invResp, hospNames] = await Promise.all([
            fetch(`${API_BASE}/api/inventory/inventory`),
            fetchHospitalNames()
        ]);
        const allRows = await invResp.json();
        const rows = (Array.isArray(allRows) ? allRows : allRows.inventory || []).filter(r => r.item_id === itemId);

        rows.sort((a, b) => b.quantity - a.quantity);

        const itemName = select.options[select.selectedIndex].dataset.name || itemId;
        const total = rows.reduce((s, r) => s + r.quantity, 0);

        summaryEl.innerHTML = `Results for: <strong>${itemName}</strong> &mdash; Total across all hospitals: <strong>${total}</strong>`;

        if (rows.length === 0) {
            resultsEl.innerHTML = '<div class="empty-state">No hospitals stock this item.</div>';
            return;
        }

        resultsEl.innerHTML = rows.map(r => {
            const name = hospNames[r.hospital_id] || r.hospital_id;
            const qtyClass = r.quantity >= 30 ? "high" : r.quantity >= 10 ? "medium" : r.quantity > 0 ? "low" : "zero";
            return `
                <div class="inventory-row">
                    <div class="hosp-info">
                        <span class="hosp-name">${name}</span>
                        <span class="hosp-id">${r.hospital_id}</span>
                    </div>
                    <span class="stock-qty ${qtyClass}">${r.quantity}</span>
                </div>
            `;
        }).join("");
    } catch (e) {
        summaryEl.innerHTML = "";
        resultsEl.innerHTML = `<div class="empty-state">Failed to load inventory: ${e.message}</div>`;
    }
}

// ── Drone fleet ──────────────────────────────────────────────────

async function loadDrones() {
    const listEl = document.getElementById("drone-list");
    const statsEl = document.getElementById("drone-stats");

    try {
        const [dronesResp, missionsResp] = await Promise.all([
            fetch(`${API_BASE}/api/drones/drones`),
            fetch(`${DISPATCH_URL}/dispatch/missions`).catch(() => null)
        ]);

        const drones = await dronesResp.json();
        const allDrones = Array.isArray(drones) ? drones : [];

        let missionsByDrone = {};
        if (missionsResp && missionsResp.ok) {
            const mData = await missionsResp.json();
            const missions = mData.active_missions || [];
            missions.forEach(m => { missionsByDrone[m.drone_id] = m; });
        }

        const operational = allDrones.filter(d => d.status === "OPERATIONAL").length;
        const inFlight = Object.keys(missionsByDrone).length;
        const faulty = allDrones.filter(d => d.status === "FAULTY").length;
        const lowBat = allDrones.filter(d => d.status === "LOW_BATTERY" || (d.status === "OPERATIONAL" && d.battery < 30)).length;

        statsEl.innerHTML = `
            <div class="drone-stat-card">
                <div class="stat-value">${allDrones.length}</div>
                <div class="stat-label">Total Fleet</div>
            </div>
            <div class="drone-stat-card">
                <div class="stat-value" style="color:#4ade80">${operational}</div>
                <div class="stat-label">Operational</div>
            </div>
            <div class="drone-stat-card">
                <div class="stat-value" style="color:#c084fc">${inFlight}</div>
                <div class="stat-label">In Flight</div>
            </div>
            <div class="drone-stat-card">
                <div class="stat-value" style="color:#f87171">${faulty + lowBat}</div>
                <div class="stat-label">Unavailable</div>
            </div>
        `;

        if (allDrones.length === 0) {
            listEl.innerHTML = '<div class="empty-state">No drones registered in the fleet.</div>';
            return;
        }

        const statusOrder = { "IN_FLIGHT": 0, "OPERATIONAL": 1, "LOW_BATTERY": 2, "FAULTY": 3 };
        allDrones.sort((a, b) => {
            const aFlight = missionsByDrone[a.drone_id] ? 0 : 1;
            const bFlight = missionsByDrone[b.drone_id] ? 0 : 1;
            if (aFlight !== bFlight) return aFlight - bFlight;
            return (statusOrder[a.status] ?? 9) - (statusOrder[b.status] ?? 9);
        });

        listEl.innerHTML = allDrones.map(d => {
            const mission = missionsByDrone[d.drone_id];
            const isFlying = !!mission;
            const displayStatus = isFlying ? "IN_FLIGHT" : d.status;

            let iconClass = "operational";
            let icon = "&#9673;";
            if (isFlying) { iconClass = "in-flight"; icon = "&#9992;"; }
            else if (d.status === "FAULTY") { iconClass = "faulty"; icon = "&#9888;"; }
            else if (d.status === "LOW_BATTERY" || d.battery < 30) { iconClass = "low-battery"; icon = "&#9889;"; }

            const batClass = d.battery >= 60 ? "high" : d.battery >= 30 ? "medium" : "low";

            let missionHtml = "";
            if (mission) {
                const mStatus = mission.dispatch_status || "IN_FLIGHT";
                missionHtml = `
                    <div class="drone-mission">
                        Order <strong>${mission.order_id}</strong> &mdash; ${mStatus}
                        ${mission.eta_minutes ? ` &mdash; ETA ${mission.eta_minutes} min` : ""}
                    </div>
                `;
            }

            return `
                <div class="drone-card">
                    <div class="drone-icon ${iconClass}">${icon}</div>
                    <div class="drone-info">
                        <div class="drone-name">${d.drone_id}</div>
                        <div class="drone-meta">
                            <span>
                                <span class="battery-bar"><span class="battery-fill ${batClass}" style="width:${d.battery}%"></span></span>
                                ${d.battery}%
                            </span>
                            <span class="badge ${getBadgeClassForDrone(displayStatus)}">${displayStatus}</span>
                            <span>Pos: ${d.lat.toFixed(4)}, ${d.lng.toFixed(4)}</span>
                        </div>
                        ${missionHtml}
                    </div>
                </div>
            `;
        }).join("");
    } catch (e) {
        statsEl.innerHTML = "";
        listEl.innerHTML = `<div class="empty-state">Failed to load drone data: ${e.message}</div>`;
    }
}

function getBadgeClassForDrone(status) {
    switch (status) {
        case "OPERATIONAL": return "badge-dispatched";
        case "IN_FLIGHT": return "badge-transit";
        case "REROUTED_IN_FLIGHT": return "badge-rerouted";
        case "FAULTY": return "badge-failed";
        case "LOW_BATTERY": return "badge-cancelled";
        default: return "badge-pending";
    }
}

// ── Polling ───────────────────────────────────────────────────────

function startPolling() {
    pollInterval = setInterval(() => {
        refreshOrders();
        refreshNotifications();
    }, 5000);
}

// ── Init ──────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    loadInventory();
    refreshOrders();
    startPolling();
    updateSubmitButton();
    addLog("Medi-Drone UI initialized", "info");
});

// ── Weather Simulation ──────────────────────────────────────────────

function addSimLog(message) {
    const area = document.getElementById("sim-log");
    if (area.querySelector(".empty-state")) area.innerHTML = "";

    const time = new Date().toLocaleTimeString();
    const entry = document.createElement("div");
    entry.className = "notif-entry";
    entry.innerHTML = `<span class="notif-time">[${time}]</span> <span class="notif-msg">${message}</span>`;
    area.prepend(entry);
}

async function refreshSimulationStatus() {
    try {
        const resp = await fetch(`${WEATHER_URL}/api/weather/simulate/status`);
        const data = await resp.json();

        const statusEl = document.getElementById("sim-status-content");
        if (data.simulation_enabled) {
            const config = data.config;
            statusEl.innerHTML = `
                <div style="color:#f87171;">&#9888; Simulation <strong>ENABLED</strong></div>
                <div style="margin-top:8px; font-size:12px;">
                    <div>Force Unsafe: ${config.force_unsafe ? "Yes" : "No"}</div>
                    <div>Conditions: ${config.unsafe_reason ? config.unsafe_reason.join(", ") : "None"}</div>
                    <div>Wind Speed: ${config.wind_speed_kmh} km/h</div>
                    <div>Rainfall: ${config.rain_mm} mm/h</div>
                </div>
            `;
        } else {
            statusEl.innerHTML = `
                <div style="color:#4ade80;">&#10003; Simulation <strong>DISABLED</strong></div>
                <div style="margin-top:8px; font-size:12px; color:#94a3b8;">Weather service using real API data or dev mode</div>
            `;
        }
    } catch (e) {
        document.getElementById("sim-status-content").innerHTML = `
            <div style="color:#f87171;">Failed to fetch simulation status: ${e.message}</div>
        `;
    }
}

async function enableSimulation() {
    const unsafe = document.getElementById("sim-unsafe").checked;
    const highWind = document.getElementById("sim-high-wind").checked;
    const heavyRain = document.getElementById("sim-heavy-rain").checked;
    const thunderstorm = document.getElementById("sim-thunderstorm").checked;
    const tornado = document.getElementById("sim-tornado").checked;
    const windSpeed = parseFloat(document.getElementById("sim-wind-speed").value) || 65;
    const rainMm = parseFloat(document.getElementById("sim-rain-mm").value) || 15;

    const reasons = [];
    if (highWind) reasons.push("HIGH_WIND");
    if (heavyRain) reasons.push("HEAVY_RAIN");
    if (thunderstorm) reasons.push("THUNDERSTORM");
    if (tornado) reasons.push("TORNADO");

    const payload = {
        force_unsafe: unsafe,
        unsafe_reason: reasons.length > 0 ? reasons : ["HIGH_WIND"],
        wind_speed_kmh: windSpeed,
        rain_mm: rainMm,
        hazard_zones: window.hazardZones || []
    };

    try {
        const resp = await fetch(`${WEATHER_URL}/api/weather/simulate/enable`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await resp.json();

        if (resp.ok) {
            addSimLog(`Simulation ENABLED: ${data.config.unsafe_reason.join(", ")} (${data.config.wind_speed_kmh} km/h wind)`);
            refreshSimulationStatus();
        } else {
            addSimLog(`Failed to enable simulation: ${data.message || "Unknown error"}`);
        }
    } catch (e) {
        addSimLog(`Error enabling simulation: ${e.message}`);
    }
}

async function disableSimulation() {
    try {
        const resp = await fetch(`${WEATHER_URL}/api/weather/simulate/disable`, {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        const data = await resp.json();

        if (resp.ok) {
            addSimLog("Simulation DISABLED - weather service using normal mode");
            refreshSimulationStatus();
        } else {
            addSimLog(`Failed to disable simulation: ${data.message || "Unknown error"}`);
        }
    } catch (e) {
        addSimLog(`Error disabling simulation: ${e.message}`);
    }
}

// ── Display Reroute Details Helper ──────────────────────────────────────

function displayRerouteDetails(orderData) {
    // Check if reroute_details exists
    if (!orderData.reroute_details) {
        return "";
    }

    const details = orderData.reroute_details;
    const originalDistance = Math.round(details.original_distance_km);
    const newDistance = Math.round(details.new_distance_km);
    const detourPercent = Math.round(details.detour_percentage);
    const waypointCount = details.waypoint_count;
    const additionalBattery = Math.round(details.additional_battery_consumption);

    // Create styled HTML div with comprehensive reroute information
    return `
        <div style="margin-top:12px; padding:12px; background:rgba(34,197,94,0.08); border:1px solid rgba(34,197,94,0.3); border-radius:8px;">
            <div style="font-size:13px; font-weight:600; color:#4ade80; margin-bottom:10px; display:flex; align-items:center; gap:6px;">
                &#10003; Rerouted Successfully
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:12px;">
                <div style="color:#94a3b8;">Original Distance:</div>
                <div style="color:#e2e8f0;">${originalDistance} km</div>
                <div style="color:#94a3b8;">New Distance:</div>
                <div style="color:#e2e8f0;">${newDistance} km</div>
                <div style="color:#fbbf24;">Detour:</div>
                <div style="color:#fbbf24; font-weight:600;">+${detourPercent}%</div>
                <div style="color:#94a3b8;">Waypoints:</div>
                <div style="color:#e2e8f0;">${waypointCount}</div>
                <div style="color:#94a3b8;">Additional Battery:</div>
                <div style="color:#e2e8f0;">+${additionalBattery}%</div>
            </div>
        </div>
    `;
}

async function refreshActiveMissions() {
    try {
        const resp = await fetch(`${DISPATCH_URL}/dispatch/missions`);
        const data = await resp.json();
        const missions = data.active_missions || [];

        let listEl = document.getElementById("active-missions-list");

        // Create element if it doesn't exist
        if (!listEl) {
            listEl = document.createElement("div");
            listEl.id = "active-missions-list";
            const missionTestingSection = document.querySelector('[onclick="triggerWeatherPoll()"]')?.parentElement?.parentElement;
            if (missionTestingSection) {
                // Insert before the action buttons
                const actionButtons = missionTestingSection.querySelector('div[style*="display:flex"]');
                if (actionButtons) {
                    missionTestingSection.insertBefore(listEl, actionButtons);
                } else {
                    missionTestingSection.appendChild(listEl);
                }
            }
        }

        if (missions.length === 0) {
            listEl.innerHTML = '<div class="empty-state" style="padding:16px;">No active missions. Create an order first to test weather cancellation.</div>';
            selectedMissionId = null;
            return;
        }

        listEl.innerHTML = `
            <div style="font-size:12px; color:#94a3b8; margin-bottom:8px;">Select a mission to test weather poll:</div>
            ${missions.map(m => {
                // Determine status color
                let statusColor = "#4ade80"; // Default green for IN_FLIGHT
                if (m.dispatch_status === "REROUTED_IN_FLIGHT") {
                    statusColor = "#c084fc"; // Purple for rerouted
                }

                // Build reroute details HTML if available
                let rerouteHtml = "";
                if (m.reroute_details) {
                    const detourPercent = Math.round(m.reroute_details.detour_percentage);
                    const waypointCount = m.reroute_details.waypoint_count;
                    rerouteHtml = `
                        <div style="font-size:11px; color:#fbbf24; margin-top:4px;">
                            &#8674; Detour: +${detourPercent}% (${waypointCount} waypoints)
                        </div>
                    `;
                }

                return `
                    <div style="padding:10px; background:#0f172a; border:1px solid #334155; border-radius:6px; margin-bottom:8px; cursor:pointer; ${selectedMissionId === m.order_id ? 'border-color:#3b82f6; background:rgba(59,130,246,0.1);' : ''}"
                         onclick="selectMission('${m.order_id}')" id="mission-${m.order_id}">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <div style="font-weight:600; color:#f8fafc;">${m.order_id}</div>
                            <div style="font-size:11px; padding:2px 8px; border-radius:10px; background:rgba(${m.dispatch_status === "REROUTED_IN_FLIGHT" ? "192,132,252" : "74,222,128"},0.15); color:${statusColor}; font-weight:600;">${m.dispatch_status}</div>
                        </div>
                        <div style="font-size:12px; color:#94a3b8; margin-top:4px;">
                            Drone: ${m.drone_id} | ETA: ${Math.round(m.eta_minutes)} min
                        </div>
                        ${rerouteHtml}
                        <button onclick="event.stopPropagation(); triggerWeatherPollForMission('${m.order_id}')" style="margin-top:8px; padding:6px 12px; background:#f59e0b; color:white; border:none; border-radius:4px; font-size:11px; font-weight:600; cursor:pointer; transition:background 0.2s;" onmouseover="this.style.background='#d97706'" onmouseout="this.style.background='#f59e0b'">
                            &#9889; Trigger Weather Poll
                        </button>
                    </div>
                `;
            }).join("")}
        `;

        // Auto-select first mission if none selected
        if (!selectedMissionId && missions.length > 0) {
            selectedMissionId = missions[0].order_id;
        }

        // Update selection visual
        if (selectedMissionId) {
            updateMissionSelection();
        }
    } catch (e) {
        const listEl = document.getElementById("active-missions-list");
        if (listEl) {
            listEl.innerHTML = `
                <div class="empty-state" style="padding:16px;">Failed to load missions: ${e.message}</div>
            `;
        }
    }
}

function selectMission(orderId) {
    selectedMissionId = orderId;
    updateMissionSelection();
    addSimLog(`Selected mission: ${orderId}`);
}

async function triggerWeatherPollForMission(orderId) {
    addSimLog(`Triggering weather poll for mission ${orderId}...`);

    try {
        const resp = await fetch(`${DISPATCH_URL}/dispatch/simulate/weather`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ order_id: orderId })
        });
        const data = await resp.json();

        if (resp.ok) {
            addSimLog(`Weather poll triggered for ${orderId} - checking for unsafe conditions...`);
            // Refresh missions after 2 second delay to allow backend processing
            setTimeout(() => {
                refreshActiveMissions();
                refreshOrders();
                addSimLog("Refreshed mission and order lists - check for reroute/abort status");
            }, 2000);
        } else {
            addSimLog(`Failed to trigger weather poll: ${data.error || data.message || "Unknown error"}`);
        }
    } catch (e) {
        addSimLog(`Error triggering weather poll: ${e.message}`);
    }
}

function updateMissionSelection() {
    document.querySelectorAll('[id^="mission-"]').forEach(el => {
        el.style.borderColor = "#334155";
        el.style.background = "#0f172a";
    });
    const selected = document.getElementById(`mission-${selectedMissionId}`);
    if (selected) {
        selected.style.borderColor = "#3b82f6";
        selected.style.background = "rgba(59,130,246,0.1)";
    }
}

async function triggerWeatherPoll() {
    if (!selectedMissionId) {
        addSimLog("No mission selected. Please select a mission first.");
        alert("Please select an active mission first.");
        return;
    }

    addSimLog(`Triggering weather poll for mission ${selectedMissionId}...`);

    try {
        const resp = await fetch(`${DISPATCH_URL}/dispatch/simulate/weather`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ order_id: selectedMissionId })
        });
        const data = await resp.json();

        if (resp.ok) {
            addSimLog(`Weather poll triggered for ${selectedMissionId} - checking for unsafe conditions...`);
            setTimeout(() => {
                refreshActiveMissions();
                addSimLog("Refreshed mission list - check if mission was aborted/rerouted");
            }, 3000);
        } else {
            addSimLog(`Failed to trigger weather poll: ${data.error || "Unknown error"}`);
        }
    } catch (e) {
        addSimLog(`Error triggering weather poll: ${e.message}`);
    }
}

// ---------------------------------------------------------------------------
// Grid-Based Hazard Zone Management
// ---------------------------------------------------------------------------

window.hazardZones = [];

function addHazardZone() {
    const lat = parseFloat(document.getElementById("sim-hazard-lat").value);
    const lng = parseFloat(document.getElementById("sim-hazard-lng").value);
    const radius = parseFloat(document.getElementById("sim-hazard-radius").value);

    if (isNaN(lat) || isNaN(lng) || isNaN(radius)) {
        alert("Please enter valid latitude, longitude, and radius values.");
        return;
    }

    if (lat < -90 || lat > 90) {
        alert("Latitude must be between -90 and 90.");
        return;
    }

    if (lng < -180 || lng > 180) {
        alert("Longitude must be between -180 and 180.");
        return;
    }

    const zone = {
        lat: lat,
        lng: lng,
        radius_km: radius,
        id: Date.now()
    };

    window.hazardZones.push(zone);
    updateHazardZonesList();
    addSimLog(`Added hazard zone: (${lat.toFixed(4)}, ${lng.toFixed(4)}) - ${radius}km radius`);
}

function removeHazardZone(id) {
    window.hazardZones = window.hazardZones.filter(z => z.id !== id);
    updateHazardZonesList();
    addSimLog(`Removed hazard zone`);
}

function clearHazardZones() {
    window.hazardZones = [];
    updateHazardZonesList();
    addSimLog(`Cleared all hazard zones`);
}

function updateHazardZonesList() {
    const listEl = document.getElementById("hazard-zones-list");

    if (window.hazardZones.length === 0) {
        listEl.innerHTML = '<div class="empty-state" style="padding:12px; font-size:12px; color:#64748b;">No hazard zones defined. Add zones above to test grid-based rerouting.</div>';
        return;
    }

    listEl.innerHTML = window.hazardZones.map(zone => `
        <div style="display:flex; align-items:center; justify-content:space-between; padding:8px 12px; background:#0f172a; border:1px solid #334155; border-radius:4px; margin-bottom:6px;">
            <div style="font-size:11px; color:#e2e8f0;">
                <span style="color:#f87171;">&#128165;</span>
                (${zone.lat.toFixed(4)}, ${zone.lng.toFixed(4)}) - ${zone.radius_km}km
            </div>
            <button onclick="removeHazardZone(${zone.id})" style="padding:4px 8px; background:#dc2626; color:white; border:none; border-radius:3px; font-size:10px; cursor:pointer;">&times;</button>
        </div>
    `).join("");
}

// Singapore region preset hazard zones
const HAZARD_PRESETS = {
    central: { lat: 1.3521, lng: 103.8198, name: "Central Singapore" },
    marina_bay: { lat: 1.2834, lng: 103.8607, name: "Marina Bay" },
    changi: { lat: 1.3644, lng: 103.9915, name: "Changi Airport" },
    jurong: { lat: 1.3174, lng: 103.7441, name: "Jurong" },
    woodlands: { lat: 1.4361, lng: 103.7865, name: "Woodlands" }
};

function addPresetHazard(location) {
    const preset = HAZARD_PRESETS[location];
    if (!preset) {
        alert(`Unknown preset: ${location}`);
        return;
    }

    const zone = {
        lat: preset.lat,
        lng: preset.lng,
        radius_km: 1.5,
        id: Date.now()
    };

    window.hazardZones.push(zone);
    updateHazardZonesList();
    addSimLog(`Added preset hazard zone: ${preset.name}`);
}

// ── Auto-Place Hazard on Active Mission ────────────────────────────────

async function autoPlaceHazard() {
    const btn = document.getElementById("auto-hazard-btn");
    if (!btn) return;

    // Disable button and show loading state
    btn.disabled = true;
    const originalText = btn.textContent;
    btn.textContent = "Calculating...";
    btn.style.background = "#64748b";

    try {
        addSimLog("&#128202; Fetching active mission flight path...");

        // Fetch active missions first to get the path
        const missionsResp = await fetch(`${DISPATCH_URL}/dispatch/missions`);
        const missionsData = await missionsResp.json();

        if (!missionsData.active_missions || missionsData.active_missions.length === 0) {
            addSimLog(`&#9888; No active missions found. Please create an order first.`);
            return;
        }

        // Use selected mission if available, otherwise find first IN_FLIGHT mission
        let mission;
        if (selectedMissionId) {
            mission = missionsData.active_missions.find(m => m.order_id === selectedMissionId);
            if (!mission) {
                addSimLog(`&#9888; Selected mission ${selectedMissionId} not found. Using first IN_FLIGHT mission.`);
                mission = missionsData.active_missions.find(m =>
                    m.dispatch_status === "IN_FLIGHT" || m.dispatch_status === "REROUTED_IN_FLIGHT"
                );
            }
        } else {
            mission = missionsData.active_missions.find(m =>
                m.dispatch_status === "IN_FLIGHT" || m.dispatch_status === "REROUTED_IN_FLIGHT"
            );
        }

        if (!mission) {
            addSimLog(`&#9888; No in-flight missions found.`);
            return;
        }

        const current = mission.current_coords;
        const customer = mission.customer_coords;

        // Calculate midpoint
        const midLat = (current.lat + customer.lat) / 2;
        const midLng = (current.lng + customer.lng) / 2;

        // Calculate recommended radius (about 12% of remaining distance)
        // Using Haversine formula for distance
        const R = 6371; // Earth's radius in km
        const dLat = (customer.lat - current.lat) * Math.PI / 180;
        const dLng = (customer.lng - current.lng) * Math.PI / 180;
        const a = Math.sin(dLat / 2) ** 2 +
                  Math.cos(current.lat * Math.PI / 180) *
                  Math.cos(customer.lat * Math.PI / 180) *
                  Math.sin(dLng / 2) ** 2;
        const c = 2 * Math.asin(Math.sqrt(a));
        const remainingDistanceKm = R * c;

        // Recommended radius: 12% of remaining distance, min 0.3km, max 1.5km
        const recommendedRadius = Math.max(0.3, Math.min(1.5, remainingDistanceKm * 0.12));

        // Populate input fields
        const latInput = document.getElementById("sim-hazard-lat");
        const lngInput = document.getElementById("sim-hazard-lng");
        const radiusInput = document.getElementById("sim-hazard-radius");

        if (latInput) latInput.value = midLat.toFixed(6);
        if (lngInput) lngInput.value = midLng.toFixed(6);
        if (radiusInput) radiusInput.value = recommendedRadius.toFixed(2);

        // Show mission info in log
        addSimLog(`&#9989; <strong>Flight Path Calculated</strong>`);
        addSimLog(`&nbsp;&nbsp;&#128205; Order: ${mission.order_id} | Drone: ${mission.drone_id}`);
        addSimLog(`&nbsp;&nbsp;&#129686; Status: ${mission.dispatch_status} | ETA: ${mission.eta_minutes}min`);
        addSimLog(`&nbsp;&nbsp;&#128396; Remaining distance: ${remainingDistanceKm.toFixed(2)}km`);
        addSimLog(`&nbsp;&nbsp;&#10142; <strong>Flight Path:</strong>`);
        addSimLog(`&nbsp;&nbsp;&nbsp;&nbsp;From: (${current.lat.toFixed(4)}, ${current.lng.toFixed(4)})`);
        addSimLog(`&nbsp;&nbsp;&nbsp;&nbsp;To: (${customer.lat.toFixed(4)}, ${customer.lng.toFixed(4)})`);
        addSimLog(`&nbsp;&nbsp;&#128165; <strong>Hazard inputs populated:</strong>`);
        addSimLog(`&nbsp;&nbsp;&nbsp;&nbsp;Lat: ${midLat.toFixed(6)}, Lng: ${midLng.toFixed(6)}, Radius: ${recommendedRadius.toFixed(2)}km (recommended)`);
        addSimLog(`&nbsp;&nbsp;&#9888; <strong>Review above, then click "Add Hazard Zone" to add it</strong>`);

    } catch (e) {
        addSimLog(`&#10060; Error: ${e.message}`);
    } finally {
        // Re-enable button
        btn.disabled = false;
        btn.textContent = originalText;
        btn.style.background = "#3b82f6";
    }
}

function renderHazardZones(zones) {
    let listEl = document.getElementById("hazard-zones-list");

    // Create element if it doesn't exist
    if (!listEl) {
        listEl = document.createElement("div");
        listEl.id = "hazard-zones-list";
        listEl.style.marginTop = "12px";
        listEl.style.maxHeight = "150px";
        listEl.style.overflowY = "auto";

        // Find the hazard zones section and append the list
        const hazardSection = document.querySelector('[onclick="addHazardZone()"]')?.parentElement?.parentElement;
        if (hazardSection) {
            hazardSection.appendChild(listEl);
        }
    }

    // Show empty state if no zones
    if (!zones || zones.length === 0) {
        listEl.innerHTML = '<div class="empty-state" style="padding:12px; font-size:12px; color:#64748b;">No hazard zones defined. Add zones above to test grid-based rerouting.</div>';
        return;
    }

    // Render each zone with remove button
    listEl.innerHTML = zones.map((zone, index) => `
        <div style="display:flex; align-items:center; justify-content:space-between; padding:8px 12px; background:#0f172a; border:1px solid #334155; border-radius:4px; margin-bottom:6px;">
            <div style="font-size:11px; color:#e2e8f0;">
                <span style="color:#f87171;">&#128165;</span>
                (${zone.lat.toFixed(4)}, ${zone.lng.toFixed(4)}) - ${zone.radius_km}km
            </div>
            <button onclick="removeHazardZoneByIndex(${index})" style="padding:4px 8px; background:#dc2626; color:white; border:none; border-radius:3px; font-size:10px; cursor:pointer;">&times;</button>
        </div>
    `).join("");

    // Update global hazard zones array
    window.hazardZones = zones;
}

function removeHazardZoneByIndex(index) {
    addSimLog(`&#9888; Remove hazard zone functionality not yet implemented for index ${index}`);
}
