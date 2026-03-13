CREATE DATABASE IF NOT EXISTS inventory_db;
USE inventory_db;

CREATE TABLE IF NOT EXISTS inventory (
    hospital_id VARCHAR(50) NOT NULL,
    item_id VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    quantity INT NOT NULL DEFAULT 0,
    PRIMARY KEY (hospital_id, item_id)
);

-- HOSP-001: Singapore General Hospital — strong blood supply, general emergency
INSERT INTO inventory (hospital_id, item_id, name, quantity) VALUES
    ('HOSP-001', 'BLOOD-O-NEG', 'O-Negative Blood Bags', 50),
    ('HOSP-001', 'BLOOD-A-POS', 'A-Positive Blood Bags', 30),
    ('HOSP-001', 'BLOOD-B-POS', 'B-Positive Blood Bags', 15),
    ('HOSP-001', 'DEFIB-01', 'Portable Defibrillator', 8),
    ('HOSP-001', 'ORGAN-KIT-01', 'Organ Transport Kit', 5),
    ('HOSP-001', 'EPINEPHRINE-01', 'Epinephrine Auto-Injector', 20)
ON DUPLICATE KEY UPDATE quantity=VALUES(quantity);

-- HOSP-002: Changi General Hospital — moderate blood, high epinephrine
INSERT INTO inventory (hospital_id, item_id, name, quantity) VALUES
    ('HOSP-002', 'BLOOD-O-NEG', 'O-Negative Blood Bags', 20),
    ('HOSP-002', 'BLOOD-B-POS', 'B-Positive Blood Bags', 25),
    ('HOSP-002', 'DEFIB-01', 'Portable Defibrillator', 6),
    ('HOSP-002', 'EPINEPHRINE-01', 'Epinephrine Auto-Injector', 40)
ON DUPLICATE KEY UPDATE quantity=VALUES(quantity);

-- HOSP-003: Tan Tock Seng Hospital — balanced mix
INSERT INTO inventory (hospital_id, item_id, name, quantity) VALUES
    ('HOSP-003', 'BLOOD-O-NEG', 'O-Negative Blood Bags', 35),
    ('HOSP-003', 'BLOOD-A-POS', 'A-Positive Blood Bags', 20),
    ('HOSP-003', 'DEFIB-01', 'Portable Defibrillator', 10),
    ('HOSP-003', 'ORGAN-KIT-01', 'Organ Transport Kit', 3),
    ('HOSP-003', 'EPINEPHRINE-01', 'Epinephrine Auto-Injector', 25)
ON DUPLICATE KEY UPDATE quantity=VALUES(quantity);

-- HOSP-004: National University Hospital — organ transport focus
INSERT INTO inventory (hospital_id, item_id, name, quantity) VALUES
    ('HOSP-004', 'BLOOD-O-NEG', 'O-Negative Blood Bags', 15),
    ('HOSP-004', 'BLOOD-A-POS', 'A-Positive Blood Bags', 10),
    ('HOSP-004', 'ORGAN-KIT-01', 'Organ Transport Kit', 8),
    ('HOSP-004', 'DEFIB-01', 'Portable Defibrillator', 4),
    ('HOSP-004', 'EPINEPHRINE-01', 'Epinephrine Auto-Injector', 15)
ON DUPLICATE KEY UPDATE quantity=VALUES(quantity);

-- HOSP-005: KK Women's and Children's Hospital — pediatric focus, epinephrine heavy
INSERT INTO inventory (hospital_id, item_id, name, quantity) VALUES
    ('HOSP-005', 'BLOOD-O-NEG', 'O-Negative Blood Bags', 25),
    ('HOSP-005', 'BLOOD-A-POS', 'A-Positive Blood Bags', 15),
    ('HOSP-005', 'BLOOD-B-POS', 'B-Positive Blood Bags', 10),
    ('HOSP-005', 'DEFIB-01', 'Portable Defibrillator', 5),
    ('HOSP-005', 'EPINEPHRINE-01', 'Epinephrine Auto-Injector', 45)
ON DUPLICATE KEY UPDATE quantity=VALUES(quantity);
