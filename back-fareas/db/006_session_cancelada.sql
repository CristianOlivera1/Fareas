-- FAREAS - 006_session_cancelada.sql (2026-10-11)
-- Motivo: R5 - las sesiones pueden cancelarse (feriado olvidado, paro).
-- ADD VALUE va aparte: el valor nuevo no se puede usar dentro de la misma
-- transacción que lo agrega (por eso 007 corre en otro archivo).
ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'cancelada';
