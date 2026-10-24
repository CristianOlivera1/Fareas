CREATE TABLE IF NOT EXISTS notification (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT       NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    kind            VARCHAR(40)  NOT NULL,
    title           VARCHAR(160) NOT NULL,
    message         VARCHAR(500) NOT NULL,
    link            VARCHAR(200),
    severity        VARCHAR(10)  NOT NULL DEFAULT 'info',
    dedupe_key      VARCHAR(120),
    read_at         TIMESTAMPTZ,
    email_status    VARCHAR(10)  NOT NULL DEFAULT 'skipped',
    email_attempts  SMALLINT     NOT NULL DEFAULT 0,
    email_error     VARCHAR(300),
    email_sent_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_notification_severity CHECK (severity IN ('info', 'success', 'warning', 'danger')),
    CONSTRAINT chk_notification_email CHECK (email_status IN ('pending', 'sent', 'failed', 'skipped'))
);

CREATE INDEX IF NOT EXISTS idx_notification_user_created ON notification (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notification_unread ON notification (user_id, created_at DESC) WHERE read_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_dedupe ON notification (user_id, dedupe_key) WHERE dedupe_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_notification_email_pending ON notification (created_at) WHERE email_status = 'pending';
