-- =============================================
-- MIDDLEWARE PERFORMANCE OPTIMIZATION
-- =============================================
-- This migration adds indexes and optimizations to speed up middleware queries
-- Created: 2026-01-20

-- Note: CREATE INDEX IF NOT EXISTS is safer and doesn't require CONCURRENTLY
-- which would fail in a transaction block

-- 1. Add index on user_profiles(user_id) if it doesn't exist
-- This dramatically speeds up the middleware profile lookup
-- Using INCLUDE clause for covering index (PostgreSQL 11+)
CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id_fast 
ON user_profiles(user_id) 
INCLUDE (onboarding_completed, is_active, role);

-- 2. Add index on user_profiles for active users lookup
-- Partial index for better performance on filtered queries
CREATE INDEX IF NOT EXISTS idx_user_profiles_active_users 
ON user_profiles(is_active, user_id) 
WHERE is_active = true;

-- 3. Analyze the table to update query planner statistics
-- This helps PostgreSQL choose the best query plans
ANALYZE user_profiles;

-- 4. Verification - Show all indexes on user_profiles
SELECT 
    'user_profiles indexes created successfully' as status,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'user_profiles'
    AND schemaname = 'public'
ORDER BY indexname;
