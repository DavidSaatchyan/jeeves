const buckets = new Map();

export function createRateLimiter({ tokensPerSec = 100, maxBurst = 200 } = {}) {
  const refillRate = tokensPerSec;
  const capacity = maxBurst;

  return {
    check(key = "default") {
      const now = Date.now();
      let bucket = buckets.get(key);

      if (!bucket) {
        bucket = { tokens: capacity, lastRefill: now };
        buckets.set(key, bucket);
      }

      const elapsed = (now - bucket.lastRefill) / 1000;
      bucket.tokens = Math.min(capacity, bucket.tokens + elapsed * refillRate);
      bucket.lastRefill = now;

      if (bucket.tokens < 1) {
        const retryAfter = Math.ceil((1 - bucket.tokens) / refillRate * 1000);
        return { allowed: false, retryAfter };
      }

      bucket.tokens -= 1;
      return { allowed: true };
    },

    reset(key) {
      buckets.delete(key);
    },

    resetAll() {
      buckets.clear();
    },
  };
}
