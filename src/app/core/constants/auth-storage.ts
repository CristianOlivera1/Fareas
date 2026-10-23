// Bearer tokens are persisted in localStorage until the backend supports
// HttpOnly cookies. Keep every key here so that migration stays centralized.
export const ACCESS_TOKEN_KEY = 'fareas_token';
export const REFRESH_TOKEN_KEY = 'fareas_refresh_token';
export const ACCESS_TOKEN_EXPIRES_AT_KEY = 'fareas_token_expires_at';
export const REFRESH_TOKEN_EXPIRES_AT_KEY = 'fareas_refresh_expires_at';
export const SESSION_KEY = 'fareas_session';
