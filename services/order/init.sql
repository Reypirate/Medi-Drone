CREATE DATABASE IF NOT EXISTS order_db;
USE order_db;

CREATE TABLE IF NOT EXISTS orders (
    order_id        VARCHAR(50)  PRIMARY KEY,
    hospital_id     VARCHAR(50),
    hospital_name   VARCHAR(100),
    item_id         VARCHAR(50),
    quantity        INT          NOT NULL DEFAULT 1,
    urgency_level   VARCHAR(20)  NOT NULL DEFAULT 'NORMAL',
    customer_address TEXT,
    customer_lat    DOUBLE NOT NULL,
    customer_lng    DOUBLE NOT NULL,
    status          VARCHAR(50)  NOT NULL DEFAULT 'PENDING',
    dispatch_status VARCHAR(50),
    mission_phase   VARCHAR(50),
    drone_id        VARCHAR(50),
    eta_minutes     DOUBLE,
    distance_km     DOUBLE,
    route_id        VARCHAR(50),
    updated_eta     VARCHAR(50),
    cancel_message  TEXT,
    reroute_details JSON,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);