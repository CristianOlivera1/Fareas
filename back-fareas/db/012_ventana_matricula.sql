ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS enrollment_start DATE;
ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS enrollment_end   DATE;
