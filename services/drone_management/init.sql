CREATE DATABASE IF NOT EXISTS drone_db;
USE drone_db;

CREATE TABLE IF NOT EXISTS drone (
    drone_id VARCHAR(50) PRIMARY KEY,
    battery INT NOT NULL DEFAULT 100,
    status VARCHAR(20) NOT NULL DEFAULT 'OPERATIONAL',
    lat DOUBLE NOT NULL,
    lng DOUBLE NOT NULL,
    current_lat DOUBLE,
    current_lng DOUBLE,
    target_lat DOUBLE,
    target_lng DOUBLE
);

CREATE TABLE IF NOT EXISTS charging_station (
    station_id INT AUTO_INCREMENT PRIMARY KEY,
    drone_id VARCHAR(50),
    status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE',
    FOREIGN KEY (drone_id) REFERENCES drone(drone_id) ON DELETE SET NULL
);

INSERT INTO drone (drone_id, battery, status, lat, lng, current_lat, current_lng) VALUES
    ('D-01', 100, 'AVAILABLE', 1.3644, 103.8190, 1.3644, 103.8190),
    ('D-02', 18, 'LOW_BATTERY', 1.2750, 103.8200, 1.2750, 103.8200),
    ('D-03', 55, 'FAULTY', 1.3000, 103.8500, 1.3000, 103.8500),
    ('D-04', 100, 'AVAILABLE', 1.3644, 103.8190, 1.3644, 103.8190),
    ('D-05', 100, 'AVAILABLE', 1.3644, 103.8190, 1.3644, 103.8190),
    ('D-06', 100, 'AVAILABLE', 1.3644, 103.8190, 1.3644, 103.8190),
    -- Additional drones at depot
    ('D-07', 100, 'AVAILABLE', 1.3644, 103.8190, 1.3644, 103.8190),
    ('D-08', 100, 'AVAILABLE', 1.3644, 103.8190, 1.3644, 103.8190),
    ('D-09', 100, 'AVAILABLE', 1.3644, 103.8190, 1.3644, 103.8190)
ON DUPLICATE KEY UPDATE battery=VALUES(battery), status=VALUES(status);
