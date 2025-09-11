-- KEYS:
--   KEYS[1] = bucket hash key, e.g., "rl:{user}:{resource}"
--   KEYS[2] = optional idempotency key, e.g., "idem:{user}:{resource}:{idempotency}"
--
-- ARGV:
--   [1] capacity_tokens              (int)
--   [2] rate_subtokens_per_sec       (int)   -- refill_rate_per_sec * SCALE
--   [3] cost_tokens                  (int)
--   [4] scale                        (int)   -- e.g., 10000
--   [5] ttl_seconds                  (int)
--   [6] idempotency_ttl_seconds      (int)   -- if KEYS[2] present
--
-- Returns (array):
--   [1] allowed (1/0)
--   [2] retry_after_seconds (as string; fractional to ms precision)
--   [3] remaining_tokens (as string; fractional)
--   [4] used_idempotency (1/0)

local bucket_key = KEYS[1]
local idem_key   = KEYS[2]

local capacity_tokens        = tonumber(ARGV[1])
local rate_subtokens_per_sec = tonumber(ARGV[2])
local cost_tokens            = tonumber(ARGV[3])
local SCALE                  = tonumber(ARGV[4])
local ttl_seconds            = tonumber(ARGV[5])
local idem_ttl_seconds       = tonumber(ARGV[6])

-- If idempotency key exists, return cached result immediately
if idem_key and idem_key ~= '' then
    local cached = redis.call('GET', idem_key)
    if cached then
    -- cached is "allowed,retry_after_ms,remaining_subtokens"
    local parts = {}
    for s in string.gmatch(cached, '([^,]+)') do table.insert(parts, s) end
    local allowed = tonumber(parts[1])
    local retry_after_ms = tonumber(parts[2])
    local remaining_subtokens = tonumber(parts[3])
    local remaining_tokens = remaining_subtokens / SCALE
    return { allowed, tostring(retry_after_ms / 1000.0), tostring(remaining_tokens), 1}
    end
end

-- Read server time (shared across instances)
local now_time = redis.call('TIME')
local now_ms = (tonumber(now_time[1]) * 1000) + math.floor(tonumber(now_time[2]) / 1000)

-- Load current bucket state
local hvals = redis.call('HMGET', bucket_key, 'tokens', 'last_refill_ms')
local tokens = tonumber(hvals[1])
local last_ms = tonumber(hvals[2])

local capacity_subtokens = capacity_tokens * SCALE
local need_subtokens = cost_tokens * SCALE

-- Initialize if missing
if (tokens == nil) or (last_ms == nil) then
    tokens = capacity_subtokens
    last_ms = now_ms
end

-- Refill
local elapsed_ms = now_ms - last_ms
if elapsed_ms < 0 then
    elapsed_ms = 0
end

if elapsed_ms > 0 and tokens < capacity_subtokens then
    -- added_subtokens = rate_subtokens_per_sec * elapsed_ms / 1000
    local added = math.floor((rate_subtokens_per_sec * elapsed_ms) / 1000)
    if added > 0 then
        tokens = tokens + added
        if tokens > capacity_subtokens then
            tokens = capacity_subtokens
        end
    end
    last_ms = now_ms
end

local allowed = 0
local retry_after_ms = 0

-- needed tokens < tokens available -> allowed
if tokens >= need_subtokens then
    tokens = tokens - need_subtokens
    allowed = 1
    retry_after_ms = 0
-- calculate the retry after a refill 
else
    local deficit = need_subtokens - tokens
    if rate_subtokens_per_sec <= 0 then
        retry_after_ms = 2^31 - 1 -- effectively infinite
    else
        retry_after_ms = math.floor((deficit * 1000 + rate_subtokens_per_sec - 1) / rate_subtokens_per_sec) -- ceil
    end
end

-- Persist state + TTL
redis.call('HMSET', bucket_key, 'tokens', tostring(tokens), 'last_refill_ms', tostring(last_ms))
if ttl_seconds and ttl_seconds > 0 then
    redis.call('EXPIRE', bucket_key, ttl_seconds)
end

-- Cache idempotent result if requested
local used_idem = 0
if idem_key and idem_key ~= '' then
    local value = tostring(allowed) .. ',' .. tostring(retry_after_ms) .. ',' .. tostring(tokens)
    redis.call('SET', idem_key, value, 'EX', idem_ttl_seconds)
    used_idem = 0 -- we just wrote it; indicates this response is fresh
end

local remaining_tokens = tokens / SCALE
return { allowed, tostring(retry_after_ms / 1000.0), tostring(remaining_tokens), used_idem }