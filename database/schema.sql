-- Email Automation Pipeline Database Schema
-- MySQL Database Schema for Order Processing System

-- Create database if it doesn't exist
CREATE DATABASE IF NOT EXISTS email_automation
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE email_automation;

-- Main order records table
CREATE TABLE IF NOT EXISTS order_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    message_id VARCHAR(255) NOT NULL UNIQUE COMMENT 'Unique email message ID',
    reference_number VARCHAR(100) COMMENT 'Order reference number',
    first_name VARCHAR(100) COMMENT 'Subject first name',
    middle_name VARCHAR(50) COMMENT 'Subject middle name/initial',
    last_name VARCHAR(100) COMMENT 'Subject last name',
    date_of_birth DATE COMMENT 'Subject date of birth',
    search_type VARCHAR(100) COMMENT 'Type of search (e.g., Criminal, Civil)',
    state VARCHAR(50) COMMENT 'State abbreviation',
    county VARCHAR(100) COMMENT 'County name',
    source_location VARCHAR(200) COMMENT 'Court or Town Hall location',
    special_instructions TEXT COMMENT 'Special handling notes',
    raw_json JSON COMMENT 'Complete extracted data from AI',
    processing_status ENUM('PENDING', 'SUCCESS', 'FAILED') DEFAULT 'PENDING' COMMENT 'Processing status',
    error_message TEXT COMMENT 'Error details if processing failed',
    pdf_filename VARCHAR(255) COMMENT 'Original PDF filename',
    email_subject VARCHAR(500) COMMENT 'Original email subject',
    email_sender VARCHAR(255) COMMENT 'Original email sender',
    email_received_at TIMESTAMP COMMENT 'When email was received',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update time',

    -- Indexes for common queries
    INDEX idx_message_id (message_id),
    INDEX idx_processing_status (processing_status),
    INDEX idx_created_at (created_at),
    INDEX idx_email_received_at (email_received_at),
    INDEX idx_reference_number (reference_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Main table for order records extracted from PDFs';

-- Audit log table for tracking all operations
CREATE TABLE IF NOT EXISTS audit_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    record_id INT COMMENT 'Reference to order_records.id',
    message_id VARCHAR(255) COMMENT 'Email message ID',
    action_type ENUM('EMAIL_RECEIVED', 'PDF_DOWNLOADED', 'AI_PARSING', 'DATABASE_INSERT', 'CSV_EXPORT', 'ERROR', 'RETRY') NOT NULL,
    action_description TEXT COMMENT 'Description of the action',
    status ENUM('SUCCESS', 'FAILED', 'IN_PROGRESS') DEFAULT 'IN_PROGRESS',
    error_details TEXT COMMENT 'Error details if action failed',
    metadata JSON COMMENT 'Additional context data',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Log entry time',

    INDEX idx_record_id (record_id),
    INDEX idx_message_id (message_id),
    INDEX idx_action_type (action_type),
    INDEX idx_created_at (created_at),

    FOREIGN KEY (record_id) REFERENCES order_records(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Audit log for tracking all system operations';

-- Processing statistics table
CREATE TABLE IF NOT EXISTS processing_stats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    stat_date DATE NOT NULL UNIQUE COMMENT 'Date of statistics',
    emails_processed INT DEFAULT 0 COMMENT 'Total emails processed',
    pdfs_downloaded INT DEFAULT 0 COMMENT 'Total PDFs downloaded',
    records_extracted INT DEFAULT 0 COMMENT 'Total records extracted',
    records_successful INT DEFAULT 0 COMMENT 'Successfully processed records',
    records_failed INT DEFAULT 0 COMMENT 'Failed records',
    csvs_generated INT DEFAULT 0 COMMENT 'CSV files generated',
    api_calls_made INT DEFAULT 0 COMMENT 'Total AI API calls',
    avg_processing_time_seconds DECIMAL(10,2) COMMENT 'Average processing time',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_stat_date (stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Daily processing statistics';

-- Error tracking table for failed records
CREATE TABLE IF NOT EXISTS error_tracking (
    id INT AUTO_INCREMENT PRIMARY KEY,
    record_id INT COMMENT 'Reference to order_records.id',
    message_id VARCHAR(255) COMMENT 'Email message ID',
    error_type VARCHAR(100) NOT NULL COMMENT 'Type of error (e.g., MISSING_FIELD, PDF_UNREADABLE, API_ERROR)',
    error_message TEXT NOT NULL COMMENT 'Detailed error message',
    stack_trace TEXT COMMENT 'Full stack trace if available',
    retry_count INT DEFAULT 0 COMMENT 'Number of retry attempts',
    last_retry_at TIMESTAMP NULL COMMENT 'Last retry timestamp',
    resolved BOOLEAN DEFAULT FALSE COMMENT 'Whether error was resolved',
    resolved_at TIMESTAMP NULL COMMENT 'When error was resolved',
    resolved_by VARCHAR(100) COMMENT 'Who resolved the error',
    resolution_notes TEXT COMMENT 'Notes on resolution',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_record_id (record_id),
    INDEX idx_message_id (message_id),
    INDEX idx_error_type (error_type),
    INDEX idx_resolved (resolved),
    INDEX idx_created_at (created_at),

    FOREIGN KEY (record_id) REFERENCES order_records(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Detailed tracking of all errors for analysis and resolution';

-- Create view for recent successful records
CREATE OR REPLACE VIEW v_recent_successful_records AS
SELECT
    id,
    message_id,
    reference_number,
    CONCAT(first_name, ' ', COALESCE(middle_name, ''), ' ', last_name) AS full_name,
    date_of_birth,
    search_type,
    state,
    county,
    processing_status,
    created_at
FROM order_records
WHERE processing_status = 'SUCCESS'
ORDER BY created_at DESC
LIMIT 100;

-- Create view for failed records needing attention
CREATE OR REPLACE VIEW v_failed_records AS
SELECT
    o.id,
    o.message_id,
    o.reference_number,
    o.first_name,
    o.last_name,
    o.processing_status,
    o.error_message,
    o.created_at,
    e.error_type,
    e.retry_count
FROM order_records o
LEFT JOIN error_tracking e ON o.id = e.record_id AND e.resolved = FALSE
WHERE o.processing_status = 'FAILED'
ORDER BY o.created_at DESC;

-- Create view for daily statistics
CREATE OR REPLACE VIEW v_daily_stats AS
SELECT
    stat_date,
    emails_processed,
    pdfs_downloaded,
    records_extracted,
    records_successful,
    records_failed,
    CASE
        WHEN records_extracted > 0
        THEN ROUND((records_successful / records_extracted) * 100, 2)
        ELSE 0
    END AS success_rate_percentage
FROM processing_stats
ORDER BY stat_date DESC
LIMIT 30;

-- Insert initial statistics entry for today
INSERT IGNORE INTO processing_stats (stat_date) VALUES (CURDATE());
