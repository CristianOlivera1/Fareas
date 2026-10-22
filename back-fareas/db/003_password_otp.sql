-- ============================================================================
-- FAREAS - 003_password_otp.sql  (2026-10-22)
-- Motivo: cambio de contraseña con OTP. `token_version` permite invalidar los
--         JWT emitidos antes del cambio (todas las sesiones), mientras el
--         endpoint devuelve un token nuevo para la sesión actual.
-- Ejecutar manualmente en pgAdmin (Query Tool sobre "fareas") o:
--   psql -U postgres -d fareas -f db/003_password_otp.sql
-- Re-ejecutable: ADD COLUMN IF NOT EXISTS.
-- ============================================================================
ALTER TABLE app_user
    ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN app_user.token_version IS
    'Se incrementa al cambiar/restablecer la contraseña; invalida JWT con ver distinto.';
