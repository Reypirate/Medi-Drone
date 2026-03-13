const API_BASE = window.location.protocol + "//" + window.location.hostname + ":8000";

let selectedUrgency = "CRITICAL";
let pollInterval = null;
let addressMode = "postalcode";
let validatedAddress = null;
let addressConfirmed = false;

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

// ── Load inventory on page load ──────────────────────────────────

async function loadInventory() {
    try {
        const resp = await fetch(`${API_BASE}/api/inventory/inventory/items`);
        const items = await resp.json();
        const select = document.getElementById("item-select");
        select.innerHTML = items.map(i =>
            `<option value="${i.item_id}">${i.name} (${i.item_id}) - Total: ${i.total_quantity}</option>`
        ).join("");
        addLog(`Loaded ${items.length} medical supply types`, "info");
    } catch (e) {
        document.getElementById("item-select").innerHTML = '<option value="BLOOD-O-NEG">O-Negative Blood Bags</option><option value="DEFIB-01">Portable Defibrillator</option>';
        addLog("Using fallback inventory list", "warn");
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

// ── Refresh orders ────────────────────────────────────────────────

async function refreshOrders() {
    try {
        const resp = await fetch(`${API_BASE}/api/orders/orders`);
        const data = await resp.json();
        const orders = data.orders || [];

        const list = document.getElementById("orders-list");

        if (orders.length === 0) {
            list.innerHTML = '<div class="empty-state">No orders yet. Submit a delivery request to get started.</div>';
            return;
        }

        const activeCount = orders.filter(o => ["CONFIRMED", "DISPATCHED", "IN_TRANSIT"].includes(o.status)).length;
        document.getElementById("active-count").textContent = `${activeCount} active mission${activeCount !== 1 ? "s" : ""}`;

        list.innerHTML = orders.reverse().map(o => {
            const badgeClass = getBadgeClass(o.status);
            return `
                <div class="order-card">
                    <div class="order-header">
                        <span class="order-id">${o.order_id}</span>
                        <span class="badge ${badgeClass}">${o.status}</span>
                    </div>
                    <div class="order-details">
                        <div>Hospital: <span class="order-detail-value">${o.hospital_name || o.hospital_id || "Auto"}</span></div>
                        <div>Item: <span class="order-detail-value">${o.item_id}</span></div>
                        <div>Qty: <span class="order-detail-value">${o.quantity}</span></div>
                        <div>Urgency: <span class="order-detail-value">${o.urgency_level}</span></div>
                        ${o.drone_id ? `<div>Drone: <span class="order-detail-value">${o.drone_id}</span></div>` : ""}
                        ${o.eta_minutes ? `<div>ETA: <span class="order-detail-value">${o.eta_minutes} min</span></div>` : ""}
                        ${o.dispatch_status ? `<div>Dispatch: <span class="order-detail-value">${o.dispatch_status}</span></div>` : ""}
                        ${o.route_id ? `<div>Route: <span class="order-detail-value">${o.route_id}</span></div>` : ""}
                        ${o.cancel_message ? `<div style="grid-column:1/-1; margin-top:4px; padding:8px; background:rgba(239,68,68,0.08); border-radius:6px; color:#f87171; font-size:12px;">${o.cancel_message}</div>` : ""}
                    </div>
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

function navigateTo(page) {
    const pages = ["dashboard", "inventory", "drones"];
    pages.forEach(p => {
        document.getElementById(`page-${p}`).classList.toggle("page-hidden", p !== page);
        document.getElementById(`nav-${p}`).classList.toggle("active", p === page);
    });

    if (page === "inventory" && !searchItemsLoaded) loadSearchItems();
    if (page === "drones") loadDrones();
}

async function loadSearchItems() {
    try {
        const resp = await fetch(`${API_BASE}/api/inventory/inventory/items`);
        const items = await resp.json();
        const select = document.getElementById("search-item-select");
        select.innerHTML = '<option value="">-- Select an item --</option>' + items.map(i =>
            `<option value="${i.item_id}" data-name="${i.name}">${i.name} (${i.item_id})</option>`
        ).join("");
        searchItemsLoaded = true;
    } catch (e) {
        document.getElementById("search-item-select").innerHTML = '<option value="">Failed to load items</option>';
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
            fetch(`${API_BASE}/api/dispatch/dispatch/missions`).catch(() => null)
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
