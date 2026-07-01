CREATE TABLE IF NOT EXISTS workers (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    phone VARCHAR(20),
    worker_type VARCHAR(80),
    assigned_employee_id INT NOT NULL REFERENCES users(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_by INT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS worker_work_entries (
    id SERIAL PRIMARY KEY,
    worker_id INT NOT NULL REFERENCES workers(id),
    employee_id INT NOT NULL REFERENCES users(id),
    project_id INT NOT NULL REFERENCES projects(id),
    worksheet_id INT NULL REFERENCES daily_work_sheets(id) ON DELETE SET NULL,
    work_date DATE NOT NULL,
    work_type VARCHAR(80) NOT NULL,
    task_title VARCHAR(200) NOT NULL,
    description TEXT,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    total_minutes INT DEFAULT 0,
    status VARCHAR(30) DEFAULT 'DRAFT',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_workers_assigned_employee_id
ON workers(assigned_employee_id);

CREATE INDEX IF NOT EXISTS idx_worker_work_entries_worker_id
ON worker_work_entries(worker_id);

CREATE INDEX IF NOT EXISTS idx_worker_work_entries_employee_id
ON worker_work_entries(employee_id);

CREATE INDEX IF NOT EXISTS idx_worker_work_entries_project_id
ON worker_work_entries(project_id);

CREATE INDEX IF NOT EXISTS idx_worker_work_entries_worksheet_id
ON worker_work_entries(worksheet_id);
