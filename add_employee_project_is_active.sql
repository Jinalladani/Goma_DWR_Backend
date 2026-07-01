ALTER TABLE employee_projects
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

UPDATE employee_projects
SET is_active = TRUE
WHERE is_active IS NULL;
