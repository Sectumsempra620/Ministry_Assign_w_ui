-- ============================================================================
-- Church Service Scheduling System - MySQL Schema
-- ============================================================================
-- Supports monthly availability submission and service scheduling
-- Normalized design for efficient queries and data integrity

-- ============================================================================
-- 1. MEMBERS TABLE
-- ============================================================================
-- Stores all church members who can be scheduled for services
-- Purpose: Central directory of all available team members
-- 
CREATE TABLE members (
    member_id INT AUTO_INCREMENT PRIMARY KEY,
    member_name VARCHAR(100) NOT NULL,
    member_gender ENUM('male', 'female'),
    email VARCHAR(255) UNIQUE,
    phone VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    joined_date DATE,
    bible_study_group ENUM('group_a', 'group_b') COMMENT 'Which bible study group this member leads/belongs to',
    is_senior_for_pairing BOOLEAN DEFAULT FALSE COMMENT 'Manual pairing flag for worship leader senior/junior matching',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_full_name (member_name),
    INDEX idx_email (email),
    INDEX idx_is_active (is_active),
    INDEX idx_bible_study_group (bible_study_group)
);


-- ============================================================================
-- 2. ROLES TABLE
-- ============================================================================
-- Defines all service roles (worship leader, AV, cleaning, etc.)
-- Purpose: Centralized role management, easily extensible
-- 
CREATE TABLE roles (
    role_id INT AUTO_INCREMENT PRIMARY KEY,
    role_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    people_needed INT DEFAULT 1 COMMENT 'How many people needed per service for this role',
    same_gender_required BOOLEAN DEFAULT FALSE COMMENT 'If TRUE, all people assigned to this role must be same gender (e.g., worship leaders)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_role_name (role_name)
);


-- ============================================================================
-- 3. MEMBER_ROLES TABLE
-- ============================================================================
-- Bridge table: Records which members are qualified for which roles
-- Purpose: Many-to-many relationship between members and roles
-- Allows flexible role qualification management
--
CREATE TABLE member_roles (
    member_role_id INT AUTO_INCREMENT PRIMARY KEY,
    member_id INT NOT NULL,
    role_id INT NOT NULL,
    qualified_date DATE,
    is_current BOOLEAN DEFAULT TRUE,
    notes VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY fk_member_roles_member (member_id) 
        REFERENCES members(member_id) ON DELETE CASCADE,
    FOREIGN KEY fk_member_roles_role (role_id) 
        REFERENCES roles(role_id) ON DELETE CASCADE,
    
    UNIQUE KEY unique_member_role (member_id, role_id),
    INDEX idx_member_id (member_id),
    INDEX idx_role_id (role_id),
    INDEX idx_is_current (is_current)
);


-- ============================================================================
-- 4. MONTHLY_FORMS TABLE
-- ============================================================================
-- Represents a monthly availability form (one form per month)
-- Purpose: Track form submission cycles and metadata
-- Scope: All availability entries for one month bound to a single form
--
CREATE TABLE monthly_forms (
    form_id INT AUTO_INCREMENT PRIMARY KEY,
    form_month DATE NOT NULL,  -- First day of the month (e.g., 2026-04-01)
    service_weeks INT NOT NULL DEFAULT 4,  -- How many Fridays in this month (4 or 5)
    submission_deadline DATE,
    status ENUM('draft', 'open', 'closed', 'published') DEFAULT 'draft',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    UNIQUE KEY unique_month (form_month),
    INDEX idx_status (status),
    INDEX idx_form_month (form_month)
);


-- ============================================================================
-- 4.5. SERVICE_DATES TABLE
-- ============================================================================
-- Maps each week of a monthly form to the actual Friday date
-- Purpose: Give members actual calendar dates when submitting availability
-- One row per week per form (e.g., 4-5 rows per month)
--
CREATE TABLE service_dates (
    service_date_id INT AUTO_INCREMENT PRIMARY KEY,
    form_id INT NOT NULL,
    service_week INT NOT NULL,  -- Week number 1-5
    friday_date DATE NOT NULL,  -- The actual Friday of that week
    is_holiday BOOLEAN DEFAULT FALSE COMMENT 'TRUE for holidays (e.g., Easter Friday)',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY fk_service_dates_form (form_id) 
        REFERENCES monthly_forms(form_id) ON DELETE CASCADE,
    
    UNIQUE KEY unique_week_date (form_id, service_week),
    UNIQUE KEY unique_friday_per_form (form_id, friday_date),
    INDEX idx_form_id (form_id),
    INDEX idx_friday_date (friday_date),
    INDEX idx_is_holiday (is_holiday)
);


-- ============================================================================
-- 5. AVAILABILITY_ENTRIES TABLE
-- ============================================================================
-- Stores individual availability responses from members
-- Purpose: Records member availability for each Friday in the month
-- One row per member per Friday per form
--
CREATE TABLE availability_entries (
    availability_id INT AUTO_INCREMENT PRIMARY KEY,
    form_id INT NOT NULL,
    member_id INT NOT NULL,
    service_week INT NOT NULL,  -- Week number 1-5
    is_available BOOLEAN NOT NULL,
    notes VARCHAR(500),
    submitted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY fk_availability_form (form_id) 
        REFERENCES monthly_forms(form_id) ON DELETE CASCADE,
    FOREIGN KEY fk_availability_member (member_id) 
        REFERENCES members(member_id) ON DELETE CASCADE,
    
    UNIQUE KEY unique_member_form_week (form_id, member_id, service_week),
    INDEX idx_form_id (form_id),
    INDEX idx_member_id (member_id),
    INDEX idx_is_available (is_available),
    INDEX idx_submitted_at (submitted_at)
);


-- ============================================================================
-- 6. SCHEDULES TABLE
-- ============================================================================
-- Final service schedule assignments (after admin scheduling)
-- Purpose: Records the final assignments of members to roles for each week
-- Constraint: Only one member per role per week per month
--
CREATE TABLE schedules (
    schedule_id INT AUTO_INCREMENT PRIMARY KEY,
    form_id INT NOT NULL,
    service_week INT NOT NULL,  -- Week number 1-5
    role_id INT NOT NULL,
    assignment_slot INT NOT NULL DEFAULT 1 COMMENT 'Slot number when a role needs multiple people for the same week',
    member_id INT NOT NULL,
    notes VARCHAR(500),
    confirmed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY fk_schedule_form (form_id) 
        REFERENCES monthly_forms(form_id) ON DELETE CASCADE,
    FOREIGN KEY fk_schedule_role (role_id) 
        REFERENCES roles(role_id) ON DELETE CASCADE,
    FOREIGN KEY fk_schedule_member (member_id) 
        REFERENCES members(member_id) ON DELETE CASCADE,
    
    UNIQUE KEY unique_week_role_assignment_slot (form_id, service_week, role_id, assignment_slot),
    INDEX idx_form_id (form_id),
    INDEX idx_member_id (member_id),
    INDEX idx_role_id (role_id),
    INDEX idx_week (service_week),
    INDEX idx_confirmed (confirmed)
);


-- ============================================================================
-- 7. RESCHEDULE_REQUESTS TABLE
-- ============================================================================
-- Member-submitted requests to replace an existing schedule assignment
-- Purpose: Preserve the published schedule while tracking sudden conflicts and
-- backup suggestions before running the rescheduler.
--
CREATE TABLE reschedule_requests (
    request_id INT AUTO_INCREMENT PRIMARY KEY,
    schedule_id INT NOT NULL,
    form_id INT NOT NULL,
    service_week INT NOT NULL,
    role_id INT NOT NULL,
    requesting_member_id INT NOT NULL,
    original_member_id INT NOT NULL,
    reason VARCHAR(1000) NOT NULL,
    status ENUM('open', 'applied', 'cancelled', 'rejected') DEFAULT 'open',
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP NULL,
    processed_note VARCHAR(1000),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY fk_reschedule_schedule (schedule_id)
        REFERENCES schedules(schedule_id) ON DELETE CASCADE,
    FOREIGN KEY fk_reschedule_form (form_id)
        REFERENCES monthly_forms(form_id) ON DELETE CASCADE,
    FOREIGN KEY fk_reschedule_role (role_id)
        REFERENCES roles(role_id) ON DELETE CASCADE,
    FOREIGN KEY fk_reschedule_requesting_member (requesting_member_id)
        REFERENCES members(member_id) ON DELETE CASCADE,
    FOREIGN KEY fk_reschedule_original_member (original_member_id)
        REFERENCES members(member_id) ON DELETE CASCADE,

    INDEX idx_reschedule_form_week (form_id, service_week),
    INDEX idx_reschedule_status (status),
    INDEX idx_reschedule_original_member (original_member_id)
);


-- ============================================================================
-- 8. RESCHEDULE_REQUEST_CANDIDATES TABLE
-- ============================================================================
-- Optional privately discussed backup candidates attached to a reschedule request
--
CREATE TABLE reschedule_request_candidates (
    request_candidate_id INT AUTO_INCREMENT PRIMARY KEY,
    request_id INT NOT NULL,
    member_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY fk_request_candidates_request (request_id)
        REFERENCES reschedule_requests(request_id) ON DELETE CASCADE,
    FOREIGN KEY fk_request_candidates_member (member_id)
        REFERENCES members(member_id) ON DELETE CASCADE,

    UNIQUE KEY unique_request_candidate_member (request_id, member_id),
    INDEX idx_request_candidate_request (request_id),
    INDEX idx_request_candidate_member (member_id)
);


-- ============================================================================
-- 9. ROLE_CONFLICTS TABLE
-- ============================================================================
-- Defines which role combinations cannot be assigned to the same member
-- Purpose: Prevents scheduling conflicts (e.g., AV + Worship Leader same day)
-- Allows flexible conflict management without hardcoding in application
--
CREATE TABLE role_conflicts (
    conflict_id INT AUTO_INCREMENT PRIMARY KEY,
    role_id_1 INT NOT NULL,
    role_id_2 INT NOT NULL,
    conflict_reason VARCHAR(500),
    conflict_type ENUM('strong', 'weak') DEFAULT 'strong',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY fk_conflict_role1 (role_id_1) 
        REFERENCES roles(role_id) ON DELETE CASCADE,
    FOREIGN KEY fk_conflict_role2 (role_id_2) 
        REFERENCES roles(role_id) ON DELETE CASCADE,
    
    UNIQUE KEY unique_role_pair (role_id_1, role_id_2),
    INDEX idx_role1 (role_id_1),
    INDEX idx_role2 (role_id_2),
    INDEX idx_is_active (is_active),
    INDEX idx_conflict_type (conflict_type),
    
    -- Ensure role_id_1 < role_id_2 to prevent duplicate pairs
    CONSTRAINT chk_role_order CHECK (role_id_1 < role_id_2)
);


-- ============================================================================
-- SAMPLE DATA
-- ============================================================================

-- Insert sample roles
INSERT INTO roles (role_name, description, people_needed, same_gender_required) VALUES
('Worship Leader', 'Leads worship and music during service', 2, TRUE),
('AV Operator', 'Manages audio/visual equipment', 1, FALSE),
('Cleaning Leader', 'Oversees cleaning team', 1, FALSE),
('Cleaner', 'Assists with facility cleaning', 3, FALSE),
('Bible Study Leader', 'Leads bible study segment', 2, FALSE);

-- Insert sample members
INSERT INTO members (member_name, member_gender, email, phone, joined_date, bible_study_group) VALUES
('朱若彤', 'female', 'lamilexico.140355@gmail.com', '3149046265', '2025-01-15', 'group_b'),
('刘源森', 'male', 'mary.j@church.com', '555-0102', '2025-02-20', 'group_b'),
('Jeff', 'male', 'david.w@church.com', '555-0103', '2025-03-10', 'group_b');

-- Assign qualifications
INSERT INTO member_roles (member_id, role_id) VALUES
(1, 1), (1, 4),  -- 朱若彤: Worship Leader, Cleaner
(2, 1), (2, 4),  -- 刘源森: Worship Leader, Cleaner
(3, 2), (3, 5);  -- Jeff: AV Operator, Bible Study Leader

-- Define role conflicts
INSERT INTO role_conflicts (role_id_1, role_id_2, conflict_reason, conflict_type) VALUES
(1, 2, 'Worship Leader and AV Operator roles conflict due to overlapping responsibilities during service', 'strong'),
(1, 3, 'Worship Leader and Cleaning Leader roles conflict due to time overlap', 'weak'),
(2, 3, 'AV Operator and Cleaning Leader roles conflict due to equipment management vs supervision', 'weak'),
(3, 4, 'Cleaning Leader and Cleaner roles conflict due to supervisory vs labor roles', 'strong');

-- Create April 2026 form with 4 Fridays
INSERT INTO monthly_forms (form_month, service_weeks, submission_deadline, status) VALUES
('2026-04-01', 4, '2026-03-27', 'open');

-- Add actual Friday dates for April 2026
INSERT INTO service_dates (form_id, service_week, friday_date, is_holiday, notes) VALUES
(1, 1, '2026-04-03', TRUE, 'Easter Friday - special service'),
(1, 2, '2026-04-10', FALSE, 'Good Friday'),
(1, 3, '2026-04-17', FALSE, 'Post-Easter service'),
(1, 4, '2026-04-24', FALSE, 'Regular service');
