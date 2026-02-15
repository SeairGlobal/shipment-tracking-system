-- VHC Shipment Management System Database Schema

-- Shippers Table
CREATE TABLE shippers (
    shipper_id SERIAL PRIMARY KEY,
    shipper_name VARCHAR(255) NOT NULL,
    shipper_code VARCHAR(50) UNIQUE NOT NULL,
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Shipments (Containers) Table
CREATE TABLE shipments (
    shipment_id SERIAL PRIMARY KEY,
    booking_number VARCHAR(100) UNIQUE NOT NULL,
    container_number VARCHAR(50),
    vessel_name VARCHAR(255),
    steamship_line VARCHAR(255),
    rail_provider VARCHAR(255),
    master_bl VARCHAR(100),
    house_bl VARCHAR(100),

    -- Dates
    booking_date DATE,
    container_stuffing_date TIMESTAMP,
    vessel_departure_date TIMESTAMP,
    pod_date TIMESTAMP, -- Port of Discharge
    poe_date TIMESTAMP, -- Port of Entry
    rail_departure_date TIMESTAMP,
    rail_arrival_date TIMESTAMP,
    discharge_date TIMESTAMP,
    pickup_date TIMESTAMP,
    customs_release_date TIMESTAMP,

    -- Status
    current_status VARCHAR(50) DEFAULT 'BOOKING_CREATED',
    current_milestone VARCHAR(100),

    -- Origins and Destinations
    origin_port VARCHAR(100),
    destination_port VARCHAR(100),
    final_destination VARCHAR(255),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Purchase Orders Table
CREATE TABLE purchase_orders (
    po_id SERIAL PRIMARY KEY,
    shipment_id INTEGER REFERENCES shipments(shipment_id) ON DELETE CASCADE,
    shipper_id INTEGER REFERENCES shippers(shipper_id),
    po_number VARCHAR(100) NOT NULL,
    po_date DATE,
    vendor_reference VARCHAR(100),
    total_amount DECIMAL(12, 2),
    currency VARCHAR(10) DEFAULT 'USD',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Documents Table
CREATE TABLE documents (
    document_id SERIAL PRIMARY KEY,
    shipment_id INTEGER REFERENCES shipments(shipment_id) ON DELETE CASCADE,
    shipper_id INTEGER REFERENCES shippers(shipper_id),
    po_id INTEGER REFERENCES purchase_orders(po_id),

    document_type VARCHAR(50) NOT NULL, -- 'PO', 'INVOICE', 'PACKING_LIST', 'CBP_7501', 'ENTRY_SUMMARY', 'COMMERCIAL', 'SEAIR_INVOICE'
    document_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_size INTEGER,
    mime_type VARCHAR(100),
    uploaded_by VARCHAR(100),
    upload_source VARCHAR(50), -- 'SHIPPER', 'SEAIR_ORIGIN', 'SEAIR_US'

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Milestones Table
CREATE TABLE milestones (
    milestone_id SERIAL PRIMARY KEY,
    shipment_id INTEGER REFERENCES shipments(shipment_id) ON DELETE CASCADE,
    milestone_name VARCHAR(100) NOT NULL,
    milestone_status VARCHAR(50) DEFAULT 'PENDING', -- 'PENDING', 'COMPLETED', 'DELAYED'
    expected_date TIMESTAMP,
    actual_date TIMESTAMP,
    location VARCHAR(255),
    notes TEXT,
    notification_sent BOOLEAN DEFAULT FALSE,
    created_by VARCHAR(100),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Milestone Types Reference
CREATE TABLE milestone_types (
    milestone_type_id SERIAL PRIMARY KEY,
    milestone_name VARCHAR(100) UNIQUE NOT NULL,
    milestone_order INTEGER NOT NULL,
    description TEXT,
    notification_template TEXT
);

-- Insert standard milestones
INSERT INTO milestone_types (milestone_name, milestone_order, description) VALUES
('BOOKING_CONFIRMED', 1, 'Container booking created and confirmed'),
('CONTAINER_LOADED', 2, 'Container stuffed and loaded at origin'),
('VESSEL_DEPARTED', 3, 'Vessel departed from origin port'),
('PORT_OF_DISCHARGE', 4, 'Arrived at Port of Discharge (POD)'),
('RAIL_DEPARTED', 5, 'Container loaded on rail and departed'),
('PORT_OF_ENTRY', 6, 'Arrived at Port of Entry (POE)'),
('CUSTOMS_RELEASED', 7, 'Customs clearance completed'),
('DISCHARGE_COMPLETE', 8, 'Container discharged and available'),
('DOCUMENTS_AVAILABLE', 9, 'All documentation uploaded and available'),
('PICKUP_COMPLETE', 10, 'Container picked up by customer'),
('INVOICE_SENT', 11, 'Final invoice generated and sent');

-- Invoices Table
CREATE TABLE invoices (
    invoice_id SERIAL PRIMARY KEY,
    shipment_id INTEGER REFERENCES shipments(shipment_id) ON DELETE CASCADE,
    invoice_number VARCHAR(100) UNIQUE NOT NULL,
    invoice_date DATE NOT NULL,
    invoice_type VARCHAR(50), -- 'SEAIR_ORIGIN', 'SEAIR_US', 'FINAL'

    -- Fee breakdown
    freight_charges DECIMAL(12, 2),
    customs_clearance DECIMAL(12, 2),
    documentation_fee DECIMAL(12, 2),
    handling_charges DECIMAL(12, 2),
    rail_charges DECIMAL(12, 2),
    other_charges DECIMAL(12, 2),
    total_amount DECIMAL(12, 2) NOT NULL,

    currency VARCHAR(10) DEFAULT 'USD',
    payment_status VARCHAR(50) DEFAULT 'PENDING', -- 'PENDING', 'PAID', 'OVERDUE'
    payment_date DATE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Users Table (for authentication)
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) NOT NULL, -- 'VHC_VIEWER', 'SEAIR_ORIGIN', 'SEAIR_US', 'ADMIN'
    team VARCHAR(50), -- 'ORIGIN', 'DESTINATION', 'VHC'
    is_active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Notifications Table
CREATE TABLE notifications (
    notification_id SERIAL PRIMARY KEY,
    shipment_id INTEGER REFERENCES shipments(shipment_id) ON DELETE CASCADE,
    milestone_id INTEGER REFERENCES milestones(milestone_id),
    notification_type VARCHAR(50), -- 'MILESTONE', 'EXCEPTION', 'DOCUMENT', 'INVOICE'
    recipient_emails TEXT, -- Comma-separated emails
    subject VARCHAR(255),
    message TEXT,
    sent_at TIMESTAMP,
    status VARCHAR(50) DEFAULT 'PENDING', -- 'PENDING', 'SENT', 'FAILED'

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Exceptions/Alerts Table
CREATE TABLE exceptions (
    exception_id SERIAL PRIMARY KEY,
    shipment_id INTEGER REFERENCES shipments(shipment_id) ON DELETE CASCADE,
    exception_type VARCHAR(50), -- 'HOLD', 'EXAM', 'DELAY', 'DAMAGE', 'OTHER'
    severity VARCHAR(20), -- 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    title VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50) DEFAULT 'OPEN', -- 'OPEN', 'IN_PROGRESS', 'RESOLVED'
    reported_by VARCHAR(100),
    assigned_to VARCHAR(100),
    resolved_at TIMESTAMP,
    resolution_notes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audit Log Table
CREATE TABLE audit_log (
    log_id SERIAL PRIMARY KEY,
    shipment_id INTEGER REFERENCES shipments(shipment_id),
    user_id INTEGER REFERENCES users(user_id),
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50), -- 'SHIPMENT', 'DOCUMENT', 'MILESTONE', 'INVOICE'
    entity_id INTEGER,
    old_value TEXT,
    new_value TEXT,
    ip_address VARCHAR(50),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_shipments_booking ON shipments(booking_number);
CREATE INDEX idx_shipments_status ON shipments(current_status);
CREATE INDEX idx_shipments_container ON shipments(container_number);
CREATE INDEX idx_po_shipment ON purchase_orders(shipment_id);
CREATE INDEX idx_documents_shipment ON documents(shipment_id);
CREATE INDEX idx_documents_type ON documents(document_type);
CREATE INDEX idx_milestones_shipment ON milestones(shipment_id);
CREATE INDEX idx_notifications_shipment ON notifications(shipment_id);
CREATE INDEX idx_exceptions_shipment ON exceptions(shipment_id);
CREATE INDEX idx_exceptions_status ON exceptions(status);

-- Create triggers for updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_shippers_updated_at BEFORE UPDATE ON shippers FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_shipments_updated_at BEFORE UPDATE ON shipments FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_purchase_orders_updated_at BEFORE UPDATE ON purchase_orders FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_milestones_updated_at BEFORE UPDATE ON milestones FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_invoices_updated_at BEFORE UPDATE ON invoices FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_exceptions_updated_at BEFORE UPDATE ON exceptions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
