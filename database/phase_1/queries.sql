-- ============================================================================
-- Church Service Scheduling System - Design Documentation & Queries
-- ============================================================================

-- ============================================================================
-- SCHEMA DESIGN OVERVIEW
-- ============================================================================

/**
NORMALIZATION APPROACH: 3NF (Third Normal Form)

1. MEMBERS
   - Stores all members, one row per person
   - Indexed by name and email for quick lookup

2. ROLES
   - Centralized role definitions
   - Extensible: add new roles easily without schema changes
   - people_needed and same_gender_required for scheduling constraints

3. MEMBER_ROLES (Many-to-Many Junction)
   - Links members to roles they're qualified for
   - Eliminates data duplication (vs. storing roles in members table)
   - Supports members with multiple roles
   - unique_member_role prevents duplicate qualifications

4. MONTHLY_FORMS
   - One form per month (enforced by unique_month constraint)
   - Tracks form lifecycle: draft → open → closed → published
   - Stores service_weeks (4 or 5) for variable month lengths
   - Central reference point for a scheduling cycle

4.5. SERVICE_DATES
   - Maps abstract week numbers (1-5) to actual Friday calendar dates
   - Helps members understand which weeks they're marking availability
   - Tracks holidays via is_holiday flag
   - One row per week per month

5. AVAILABILITY_ENTRIES
   - Records member availability for each Friday
   - One row per member per week per form
   - Unique constraint prevents duplicate entries
   - Efficiently supports queries like "who's available week 3?"

6. SCHEDULES
   - Final assignments after admin scheduling
   - Contains member ID + role ID + week
   - unique_week_role_assignment ensures only one person per role per week
   - confirmed flag tracks when assignments are finalized

7. ROLE_CONFLICTS
   - Defines which role combinations conflict
   - conflict_type: 'strong' (always prevent) or 'weak' (allow in shortages)
   - Flexible design for business logic

FOREIGN KEY STRATEGY:
- All FKs use ON DELETE CASCADE
- Rationale: Deleting a form also deletes all availability and schedule entries
- Rationale: Deleting a member removes them from all relationships

INDEX STRATEGY:
- PK indexes: Automatic
- FK columns: Indexed for join performance
- Status/active fields: Indexed for filtering queries
- Date fields: Indexed where used in range queries
*/


-- ============================================================================
-- USEFUL QUERIES FOR FASTAPI ENDPOINTS
-- ============================================================================

-- ============================================================================
-- 1. GET CURRENT MONTH'S FORM STATUS
-- ============================================================================
SELECT 
    f.form_id,
    f.form_month,
    f.service_weeks,
    f.status,
    COUNT(DISTINCT ae.member_id) as responses_submitted,
    COUNT(DISTINCT m.member_id) as total_active_members,
    ROUND(100 * COUNT(DISTINCT ae.member_id) / COUNT(DISTINCT m.member_id), 1) as response_rate
FROM monthly_forms f
LEFT JOIN availability_entries ae ON f.form_id = ae.form_id AND ae.submitted_at IS NOT NULL
CROSS JOIN members m WHERE m.is_active = TRUE
WHERE f.form_month = CURDATE() - INTERVAL DAY(CURDATE())-1 DAY
GROUP BY f.form_id;


-- ============================================================================
-- 1.5. GET SERVICE DATES FOR A MONTH (WITH HOLIDAY FLAGS)
-- ============================================================================
-- Returns the actual Friday dates for each week in a month
-- Helps members understand which calendar dates they're marking availability for
SELECT 
    sd.service_date_id,
    f.form_id,
    f.form_month,
    sd.service_week,
    sd.friday_date,
    DATE_FORMAT(sd.friday_date, '%W, %M %d, %Y') as formatted_date,
    sd.is_holiday,
    sd.notes,
    CASE WHEN sd.is_holiday THEN 'HOLIDAY' ELSE 'Regular' END as week_type
FROM service_dates sd
JOIN monthly_forms f ON sd.form_id = f.form_id
WHERE f.form_id = ?  -- parameterized by form_id
ORDER BY sd.service_week;


-- ============================================================================
-- 2. GET ALL AVAILABILITY FOR A GIVEN MONTH
-- ============================================================================
SELECT 
    ae.service_week,
    r.role_id,
    r.role_name,
    COUNT(CASE WHEN ae.is_available = TRUE THEN 1 END) as available_count,
    GROUP_CONCAT(DISTINCT CASE WHEN ae.is_available = TRUE 
        THEN CONCAT(m.first_name, ' ', m.last_name) END) as available_members
FROM availability_entries ae
JOIN monthly_forms f ON ae.form_id = f.form_id
JOIN members m ON ae.member_id = m.member_id
CROSS JOIN roles r
WHERE f.form_id = ?  -- parameterized
GROUP BY ae.service_week, r.role_id
ORDER BY ae.service_week, r.role_id;


-- ============================================================================
-- 3. GET MEMBER'S AVAILABILITY & QUALIFICATIONS FOR MONTH
-- ============================================================================
SELECT 
    m.member_id,
    CONCAT(m.first_name, ' ', m.last_name) as member_name,
    ae.service_week,
    ae.is_available,
    ae.notes,
    GROUP_CONCAT(r.role_name SEPARATOR ', ') as qualified_roles
FROM members m
LEFT JOIN availability_entries ae ON m.member_id = ae.member_id AND ae.form_id = ?
LEFT JOIN member_roles mr ON m.member_id = mr.member_id AND mr.is_current = TRUE
LEFT JOIN roles r ON mr.role_id = r.role_id
WHERE m.is_active = TRUE
GROUP BY m.member_id, ae.service_week
ORDER BY m.last_name, ae.service_week;


-- ============================================================================
-- 4. GET CANDIDATES FOR A SPECIFIC ROLE IN A SPECIFIC WEEK
-- ============================================================================
-- Returns qualified members who were available that week
SELECT 
    m.member_id,
    CONCAT(m.first_name, ' ', m.last_name) as member_name,
    m.email
FROM members m
WHERE m.member_id IN (
    SELECT mr.member_id 
    FROM member_roles mr 
    WHERE mr.role_id = ? AND mr.is_current = TRUE
)
AND m.member_id IN (
    SELECT ae.member_id 
    FROM availability_entries ae 
    WHERE ae.form_id = ? AND ae.service_week = ? AND ae.is_available = TRUE
)
AND m.member_id NOT IN (
    SELECT s.member_id 
    FROM schedules s 
    WHERE s.form_id = ? AND s.service_week = ?
)
ORDER BY m.last_name;


-- ============================================================================
-- 5. GET CURRENT SCHEDULE FOR A MONTH
-- ============================================================================
SELECT 
    s.schedule_id,
    s.service_week,
    r.role_name,
    CONCAT(m.first_name, ' ', m.last_name) as member_name,
    s.confirmed,
    s.notes
FROM schedules s
JOIN monthly_forms f ON s.form_id = f.form_id
JOIN roles r ON s.role_id = r.role_id
JOIN members m ON s.member_id = m.member_id
WHERE s.form_id = ?
ORDER BY s.service_week, r.role_name;


-- ============================================================================
-- 6. GET SCHEDULE GAPS (Missing assignments)
-- ============================================================================
-- Shows which roles haven't been assigned for each week
SELECT 
    f.form_id,
    w.week_num as service_week,
    r.role_id,
    r.role_name,
    r.is_critical,
    CASE WHEN s.schedule_id IS NULL THEN 'UNASSIGNED' ELSE 'FILLED' END as status
FROM monthly_forms f
CROSS JOIN (SELECT 1 as week_num UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5) w
CROSS JOIN roles r
LEFT JOIN schedules s ON f.form_id = s.form_id 
    AND w.week_num = s.service_week 
    AND r.role_id = s.role_id
WHERE f.form_id = ? AND w.week_num <= (SELECT service_weeks FROM monthly_forms WHERE form_id = ?)
ORDER BY w.week_num, r.is_critical DESC, r.role_name;


-- ============================================================================
-- 7. VALIDATE MEMBER'S AVAILABILITY COVERAGE
-- ============================================================================
-- Shows if enough members are available each week for staffing
SELECT 
    ae.service_week,
    COUNT(CASE WHEN ae.is_available = TRUE THEN 1 END) as available_members,
    COUNT(DISTINCT m.member_id) as submitted_responses,
    COUNT(DISTINCT m.member_id) - COUNT(CASE WHEN ae.is_available = TRUE THEN 1 END) as unavailable_members
FROM availability_entries ae
JOIN monthly_forms f ON ae.form_id = f.form_id
JOIN members m ON ae.member_id = m.member_id
WHERE f.form_id = ?
GROUP BY ae.service_week
ORDER BY ae.service_week;


-- ============================================================================
-- 9. CHECK FOR ROLE CONFLICTS BEFORE SCHEDULING
-- ============================================================================
-- Returns any existing assignments that would conflict with a proposed assignment
-- @param: conflict_check_type - 'all', 'strong_only', 'weak_allowed'
SELECT 
    s.schedule_id,
    r.role_name as existing_role,
    s.service_week,
    s.confirmed,
    rc.conflict_type,
    rc.conflict_reason
FROM schedules s
JOIN roles r ON s.role_id = r.role_id
LEFT JOIN role_conflicts rc ON rc.is_active = TRUE AND (
    (rc.role_id_1 = s.role_id AND rc.role_id_2 = ?) OR
    (rc.role_id_1 = ? AND rc.role_id_2 = s.role_id)
)
WHERE s.form_id = ? 
  AND s.service_week = ?
  AND s.member_id = ?
  AND rc.conflict_id IS NOT NULL
  AND (
    ? = 'all' OR
    (? = 'strong_only' AND rc.conflict_type = 'strong') OR
    (? = 'weak_allowed' AND rc.conflict_type = 'strong')
  );


-- ============================================================================
-- 10. GET ALL ACTIVE ROLE CONFLICTS
-- ============================================================================
SELECT 
    rc.conflict_id,
    r1.role_name as role_1_name,
    r2.role_name as role_2_name,
    rc.conflict_reason,
    rc.conflict_type,
    rc.created_at
FROM role_conflicts rc
JOIN roles r1 ON rc.role_id_1 = r1.role_id
JOIN roles r2 ON rc.role_id_2 = r2.role_id
WHERE rc.is_active = TRUE
ORDER BY rc.conflict_type, r1.role_name, r2.role_name;


-- ============================================================================
-- 11. VALIDATE SCHEDULE FOR CONFLICTS (Complete check)
-- ============================================================================
-- Shows all members who have conflicting role assignments in the same week
-- @param: check_type - 'all', 'strong_only', 'weak_allowed'
SELECT 
    mf.form_month,
    s.service_week,
    m.member_name,
    GROUP_CONCAT(DISTINCT r.role_name ORDER BY r.role_name) as assigned_roles,
    GROUP_CONCAT(DISTINCT CONCAT(rc.conflict_type, ': ', rc.conflict_reason)) as conflict_details,
    COUNT(DISTINCT s.schedule_id) as role_count
FROM schedules s
JOIN monthly_forms mf ON s.form_id = mf.form_id
JOIN members m ON s.member_id = m.member_id
JOIN roles r ON s.role_id = r.role_id
LEFT JOIN role_conflicts rc ON rc.is_active = TRUE AND (
    (rc.role_id_1 = s.role_id AND rc.role_id_2 IN (
        SELECT s2.role_id FROM schedules s2 
        WHERE s2.form_id = s.form_id 
        AND s2.service_week = s.service_week 
        AND s2.member_id = s.member_id
    )) OR
    (rc.role_id_2 = s.role_id AND rc.role_id_1 IN (
        SELECT s2.role_id FROM schedules s2 
        WHERE s2.form_id = s.form_id 
        AND s2.service_week = s.service_week 
        AND s2.member_id = s.member_id
    ))
)
WHERE mf.form_id = ?
  AND rc.conflict_id IS NOT NULL
  AND (
    ? = 'all' OR
    (? = 'strong_only' AND rc.conflict_type = 'strong') OR
    (? = 'weak_allowed' AND rc.conflict_type = 'strong')
  )
GROUP BY s.form_id, s.service_week, s.member_id
HAVING COUNT(DISTINCT s.schedule_id) > 1
ORDER BY mf.form_month, s.service_week, m.member_name;


-- ============================================================================
-- 12. GET CONFLICT-FREE CANDIDATES FOR A ROLE
-- ============================================================================
-- Returns qualified members who are available AND won't create conflicts
SELECT DISTINCT
    m.member_id,
    m.member_name,
    m.email,
    ae.is_available,
    CASE WHEN existing_conflicts.conflict_count > 0 THEN 'HAS_CONFLICTS' ELSE 'AVAILABLE' END as status
FROM members m
JOIN member_roles mr ON m.member_id = mr.member_id AND mr.is_current = TRUE
LEFT JOIN availability_entries ae ON ae.member_id = m.member_id 
    AND ae.form_id = ? 
    AND ae.service_week = ?
LEFT JOIN (
    -- Find members who already have conflicting assignments this week
    SELECT 
        s.member_id,
        COUNT(*) as conflict_count
    FROM schedules s
    WHERE s.form_id = ? AND s.service_week = ?
    GROUP BY s.member_id
    HAVING COUNT(*) > 0
) existing_conflicts ON existing_conflicts.member_id = m.member_id
WHERE m.is_active = TRUE
  AND mr.role_id = ?
  AND ae.is_available = TRUE
  AND (existing_conflicts.conflict_count IS NULL OR existing_conflicts.conflict_count = 0)
ORDER BY m.member_name;


-- ============================================================================
-- 13. SCHEDULE VALIDATION REPORT
-- ============================================================================
-- Comprehensive report of all scheduling issues for a month
SELECT 
    'ROLE_CONFLICTS' as issue_type,
    COUNT(*) as count,
    GROUP_CONCAT(DISTINCT m.member_name) as affected_members
FROM (
    SELECT s.member_id
    FROM schedules s
    WHERE s.form_id = ?
    GROUP BY s.form_id, s.service_week, s.member_id
    HAVING COUNT(*) > 1
) conflicts
JOIN members m ON conflicts.member_id = m.member_id

UNION ALL

SELECT 
    'UNQUALIFIED_ASSIGNMENTS' as issue_type,
    COUNT(*) as count,
    GROUP_CONCAT(DISTINCT m.member_name) as affected_members
FROM schedules s
LEFT JOIN member_roles mr ON s.member_id = mr.member_id 
    AND s.role_id = mr.role_id 
    AND mr.is_current = TRUE
JOIN members m ON s.member_id = m.member_id
WHERE s.form_id = ? AND mr.member_role_id IS NULL

UNION ALL

SELECT 
    'UNAVAILABLE_ASSIGNMENTS' as issue_type,
    COUNT(*) as count,
    GROUP_CONCAT(DISTINCT m.member_name) as affected_members
FROM schedules s
LEFT JOIN availability_entries ae ON s.form_id = ae.form_id 
    AND s.member_id = ae.member_id 
    AND s.service_week = ae.service_week 
    AND ae.is_available = TRUE
JOIN members m ON s.member_id = m.member_id
WHERE s.form_id = ? AND ae.availability_id IS NULL;


-- ============================================================================
-- MAINTENANCE & CLEANUP QUERIES
-- ============================================================================

-- ============================================================================
-- FIND INACTIVE MEMBERS NOT RECENTLY USING SYSTEM
-- ============================================================================
SELECT 
    member_id,
    CONCAT(first_name, ' ', last_name) as name,
    email,
    DATEDIFF(CURDATE(), created_at) as days_since_joined,
    DATEDIFF(CURDATE(), updated_at) as days_since_updated
FROM members
WHERE is_active = TRUE 
AND updated_at < CURDATE() - INTERVAL 6 MONTH
ORDER BY updated_at DESC;


-- ============================================================================
-- IDENTIFY OVER-SCHEDULED MEMBERS (Assigned multiple roles same week - usually error)
-- ============================================================================
SELECT 
    f.form_month,
    s.service_week,
    CONCAT(m.first_name, ' ', m.last_name) as member_name,
    COUNT(s.schedule_id) as role_count,
    GROUP_CONCAT(r.role_name SEPARATOR ', ') as roles_assigned
FROM schedules s
JOIN monthly_forms f ON s.form_id = f.form_id
JOIN members m ON s.member_id = m.member_id
JOIN roles r ON s.role_id = r.role_id
GROUP BY s.form_id, s.service_week, s.member_id
HAVING COUNT(s.schedule_id) > 1;


-- ============================================================================
-- MEMBER WORKLOAD ANALYSIS (How many times each member assigned per month)
-- ============================================================================
SELECT 
    f.form_month,
    CONCAT(m.first_name, ' ', m.last_name) as member_name,
    COUNT(s.schedule_id) as assignments_count,
    GROUP_CONCAT(DISTINCT CONCAT(r.role_name, ' (Wk', s.service_week, ')')) as assignments
FROM schedules s
JOIN monthly_forms f ON s.form_id = f.form_id
JOIN members m ON s.member_id = m.member_id
JOIN roles r ON s.role_id = r.role_id
WHERE f.form_id = ?
GROUP BY s.form_id, s.member_id
ORDER BY assignments_count DESC;


-- ============================================================================
-- DATA INTEGRITY CHECKS
-- ============================================================================

-- Verify no member assigned to role they're not qualified for
SELECT s.* FROM schedules s
WHERE NOT EXISTS (
    SELECT 1 FROM member_roles mr 
    WHERE mr.member_id = s.member_id 
    AND mr.role_id = s.role_id 
    AND mr.is_current = TRUE
)
ORDER BY s.form_id, s.service_week;

-- Verify no assigned member was unavailable that week
SELECT s.* FROM schedules s
WHERE NOT EXISTS (
    SELECT 1 FROM availability_entries ae
    WHERE ae.form_id = s.form_id
    AND ae.member_id = s.member_id
    AND ae.service_week = s.service_week
    AND ae.is_available = TRUE
)
ORDER BY s.form_id, s.service_week;
