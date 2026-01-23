-- Migration: Database Optimization - Indexes
-- Description: Adds critical composite and partial indexes for query performance
-- Priority: HIGH
-- Risk: LOW (indexes can be dropped if issues occur)
-- Date: 2024
-- This migration is idempotent - safe to run multiple times

-- ============================================================================
-- COMPOSITE INDEXES FOR COMMON QUERY PATTERNS
-- ============================================================================

-- 1. user_subscriptions - Active subscription lookups (used in every credit operation)
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_user_status_active 
ON public.user_subscriptions(user_id, status) 
WHERE status = 'active';

-- 2. credit_transactions - User transaction history pagination
CREATE INDEX IF NOT EXISTS idx_credit_transactions_user_created 
ON public.credit_transactions(user_id, created_at DESC);

-- 3. credit_transactions - Action-based queries
CREATE INDEX IF NOT EXISTS idx_credit_transactions_user_action_created 
ON public.credit_transactions(user_id, action_id, created_at DESC);

-- 4. shorts - User content listing with status filter
CREATE INDEX IF NOT EXISTS idx_shorts_user_status_created 
ON public.shorts(user_id, status, created_at DESC);

-- 5. products - User product listing
CREATE INDEX IF NOT EXISTS idx_products_user_created 
ON public.products(user_id, created_at DESC);

-- 6. video_scenes - Scenario scene queries with status
CREATE INDEX IF NOT EXISTS idx_video_scenes_scenario_status 
ON public.video_scenes(scenario_id, status);

-- 7. publishing_info - Platform status queries
CREATE INDEX IF NOT EXISTS idx_publishing_info_platform_status 
ON public.publishing_info(platform, status);

-- 8. user_activities - Activity filtering by user, action, and date
CREATE INDEX IF NOT EXISTS idx_user_activities_user_action_created 
ON public.user_activities(user_id, action, created_at DESC);

-- 9. credit_usage_tracking - Usage limit checks (monthly limits)
CREATE INDEX IF NOT EXISTS idx_credit_usage_tracking_user_action_month 
ON public.credit_usage_tracking(user_id, action_id, usage_month);

-- 10. addon_credits - Expiration queries for FIFO credit deduction
CREATE INDEX IF NOT EXISTS idx_addon_credits_user_expires_remaining 
ON public.addon_credits(user_id, expires_at, credits_remaining) 
WHERE credits_remaining > 0;

-- ============================================================================
-- PARTIAL INDEXES FOR COMMON FILTERS
-- ============================================================================

-- 11. user_profiles - Active users only
CREATE INDEX IF NOT EXISTS idx_user_profiles_active_users 
ON public.user_profiles(user_id) 
WHERE is_active = true;

-- 12. shorts - Completed videos only
CREATE INDEX IF NOT EXISTS idx_shorts_completed 
ON public.shorts(user_id, created_at DESC) 
WHERE status = 'completed';

-- 13. user_subscriptions - Active subscriptions with period info
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_active_only 
ON public.user_subscriptions(user_id, plan_id, current_period_end) 
WHERE status = 'active';

-- ============================================================================
-- COVERING INDEXES FOR INDEX-ONLY SCANS
-- ============================================================================

-- 14. user_credits - Covering index for balance checks (PostgreSQL 11+)
-- Note: INCLUDE syntax requires PostgreSQL 11+
-- For older versions, this will create a regular index
DO $$
BEGIN
    IF current_setting('server_version_num')::int >= 110000 THEN
        CREATE INDEX IF NOT EXISTS idx_user_credits_covering 
        ON public.user_credits(user_id) 
        INCLUDE (credits_remaining, subscription_credits_remaining, addon_credits_remaining);
    ELSE
        -- Fallback for older PostgreSQL versions
        CREATE INDEX IF NOT EXISTS idx_user_credits_covering_legacy 
        ON public.user_credits(user_id, credits_remaining, subscription_credits_remaining, addon_credits_remaining);
    END IF;
END $$;

-- 15. user_subscriptions - Covering index for subscription checks
DO $$
BEGIN
    IF current_setting('server_version_num')::int >= 110000 THEN
        CREATE INDEX IF NOT EXISTS idx_user_subscriptions_covering 
        ON public.user_subscriptions(user_id, status) 
        INCLUDE (plan_id, current_period_start, current_period_end) 
        WHERE status = 'active';
    ELSE
        -- Fallback for older PostgreSQL versions
        CREATE INDEX IF NOT EXISTS idx_user_subscriptions_covering_legacy 
        ON public.user_subscriptions(user_id, status, plan_id, current_period_start, current_period_end) 
        WHERE status = 'active';
    END IF;
END $$;

-- ============================================================================
-- GIN INDEX OPTIMIZATION
-- ============================================================================

-- 16. user_profiles.preferences - GIN index for JSONB queries
CREATE INDEX IF NOT EXISTS idx_user_profiles_preferences_gin 
ON public.user_profiles USING GIN (preferences);

-- ============================================================================
-- COMMENTS FOR DOCUMENTATION
-- ============================================================================

COMMENT ON INDEX idx_user_subscriptions_user_status_active IS 
'Optimizes active subscription lookups used in credit operations';

COMMENT ON INDEX idx_credit_transactions_user_created IS 
'Optimizes transaction history pagination queries';

COMMENT ON INDEX idx_shorts_user_status_created IS 
'Optimizes user dashboard content listing queries';

COMMENT ON INDEX idx_user_credits_covering IS 
'Covering index for index-only scans on credit balance checks';

COMMENT ON INDEX idx_user_subscriptions_covering IS 
'Covering index for faster subscription checks without table access';

-- ============================================================================
-- ANALYZE TABLES AFTER INDEX CREATION
-- ============================================================================

-- Update statistics for query planner
ANALYZE public.user_subscriptions;
ANALYZE public.credit_transactions;
ANALYZE public.shorts;
ANALYZE public.products;
ANALYZE public.video_scenes;
ANALYZE public.publishing_info;
ANALYZE public.user_activities;
ANALYZE public.credit_usage_tracking;
ANALYZE public.addon_credits;
ANALYZE public.user_profiles;
ANALYZE public.user_credits;

