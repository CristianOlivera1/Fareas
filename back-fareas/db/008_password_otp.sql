CREATE TABLE IF NOT EXISTS password_otp (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT       NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    purpose     VARCHAR(20)  NOT NULL,
    code_hash   VARCHAR(128) NOT NULL,
    sent_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ  NOT NULL,
    attempts    SMALLINT     NOT NULL DEFAULT 0,
    verified    BOOLEAN      NOT NULL DEFAULT FALSE,
    consumed_at TIMESTAMPTZ
);

DO $$
BEGIN
    ALTER TABLE password_otp
        ADD CONSTRAINT uq_password_otp_user_purpose UNIQUE (user_id, purpose);
EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE password_otp
        ADD CONSTRAINT chk_password_otp_expiry CHECK (expires_at > sent_at);
EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_password_otp_user ON password_otp (user_id);
