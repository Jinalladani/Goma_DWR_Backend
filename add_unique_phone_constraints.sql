CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone_unique
ON users(phone)
WHERE phone IS NOT NULL AND phone <> '';

CREATE UNIQUE INDEX IF NOT EXISTS idx_workers_phone_unique
ON workers(phone)
WHERE phone IS NOT NULL AND phone <> '';
