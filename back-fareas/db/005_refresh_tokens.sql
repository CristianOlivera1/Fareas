-- FAREAS - 005_refresh_tokens.sql (2026-10-22)
-- Motivo: refresh tokens opacos, hasheados y rotativos por sesión.
-- Ejecutar una vez sobre una BD existente:
--   psql -U postgres -d fareas -v ON_ERROR_STOP=1 -f db/005_refresh_tokens.sql
-- Re-ejecutable: no borra datos.

CREATE TABLE IF NOT EXISTS refresh_token (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT      NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    family_id       UUID        NOT NULL,
    token_hash      VARCHAR(64) NOT NULL UNIQUE,
    token_version   INTEGER     NOT NULL DEFAULT 0,
    issued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    last_used_at    TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    revoked_reason  VARCHAR(40),
    replaced_by_id  BIGINT REFERENCES refresh_token(id) ON DELETE SET NULL,
    user_agent      VARCHAR(300),
    ip_address      VARCHAR(45),
    CONSTRAINT chk_refresh_expiry CHECK (expires_at > issued_at)
);

CREATE INDEX IF NOT EXISTS idx_refresh_user   ON refresh_token (user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_family ON refresh_token (family_id);
CREATE INDEX IF NOT EXISTS idx_refresh_active ON refresh_token (user_id) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_refresh_expiry ON refresh_token (expires_at) WHERE revoked_at IS NULL;
