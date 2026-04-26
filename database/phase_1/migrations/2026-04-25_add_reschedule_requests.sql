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
