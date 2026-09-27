export interface RateLimitState {
  attempts: number;
  windowStart: number;
  lockedUntil: number;
}
