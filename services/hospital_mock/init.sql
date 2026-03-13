CREATE DATABASE IF NOT EXISTS hospital_db;
USE hospital_db;

CREATE TABLE IF NOT EXISTS hospital (
    hospital_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'ACTIVE',
    lat DOUBLE NOT NULL,
    lng DOUBLE NOT NULL
);

INSERT INTO hospital (hospital_id, name, status, lat, lng) VALUES
    ('HOSP-001', 'Singapore General Hospital', 'ACTIVE', 1.2836, 103.8333),
    ('HOSP-002', 'Changi General Hospital', 'ACTIVE', 1.3401, 103.9494),
    ('HOSP-003', 'Tan Tock Seng Hospital', 'ACTIVE', 1.3215, 103.8468),
    ('HOSP-004', 'National University Hospital', 'ACTIVE', 1.2937, 103.7830),
    ('HOSP-005', 'KK Women''s and Children''s Hospital', 'ACTIVE', 1.3103, 103.8464)
ON DUPLICATE KEY UPDATE name=VALUES(name);
