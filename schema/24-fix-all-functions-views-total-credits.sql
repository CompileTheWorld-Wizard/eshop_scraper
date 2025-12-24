-- Migration: Fix ALL Functions and Views to Use total_credits
-- Description: Comprehensive fix for all database objects that reference user_credits.credits_total
-- Priority: CRITICAL (fixes credit adjustment error)
-- Risk: LOW (only updates functions/views, doesn't change data)
-- Date: 2024
-- This migration is idempotent - safe to run multiple times

-- ============================================================================
-- STEP 1: RECREATE ALL FUNCTIONS THAT REFERENCE user_credits
-- ============================================================================

-- Function: get_user_credits - Already correct, but ensure it's up to date
CREATE OR REPLACE FUNCTION get_user_credits(user_uuid UUID)
RETURNS TABLE(
    credits_total INTEGER,
    credits_remaining INTEGER,
    subscription_status TEXT,
    plan_name TEXT,
    plan_display_name TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COALESCE(uc.total_credits, 0) as credits_total,
        COALESCE(uc.credits_remaining, 0) as credits_remaining,
        COALESCE(us.status, 'no_subscription') as subscription_status,
        COALESCE(sp.name, 'no_plan') as plan_name,
        COALESCE(sp.display_name, 'No Plan') as plan_display_name
    FROM auth.users u
    LEFT JOIN public.user_credits uc ON u.id = uc.user_id
    LEFT JOIN public.user_subscriptions us ON u.id = us.user_id AND us.status = 'active'
    LEFT JOIN public.subscription_plans sp ON us.plan_id = sp.id
    WHERE u.id = user_uuid;
END;
$$ LANGUAGE plpgsql;

-- Function: get_user_status - Already correct, but ensure it's up to date
CREATE OR REPLACE FUNCTION get_user_status(user_uuid UUID)
RETURNS TABLE(
    user_id UUID,
    full_name TEXT,
    email TEXT,
    role TEXT,
    is_active BOOLEAN,
    onboarding_completed BOOLEAN,
    subscription_status TEXT,
    plan_name TEXT,
    plan_display_name TEXT,
    credits_total INTEGER,
    credits_remaining INTEGER,
    created_at TIMESTAMP WITH TIME ZONE,
    last_activity TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        u.id as user_id,
        up.full_name,
        u.email,
        up.role,
        up.is_active,
        up.onboarding_completed,
        COALESCE(us.status, 'no_subscription') as subscription_status,
        COALESCE(sp.name, 'no_plan') as plan_name,
        COALESCE(sp.display_name, 'No Plan') as plan_display_name,
        COALESCE(uc.total_credits, 0) as credits_total,
        COALESCE(uc.credits_remaining, 0) as credits_remaining,
        up.created_at,
        (SELECT MAX(created_at) FROM public.user_activities WHERE user_id = u.id) as last_activity
    FROM auth.users u
    LEFT JOIN public.user_profiles up ON u.id = up.user_id
    LEFT JOIN public.user_credits uc ON u.id = uc.user_id
    LEFT JOIN public.user_subscriptions us ON u.id = us.user_id AND us.status = 'active'
    LEFT JOIN public.subscription_plans sp ON us.plan_id = sp.id
    WHERE u.id = user_uuid;
END;
$$ LANGUAGE plpgsql;

-- Function: sync_user_credits_to_profile - Already correct, but ensure it's up to date
CREATE OR REPLACE FUNCTION sync_user_credits_to_profile(user_uuid UUID)
RETURNS VOID AS $$
BEGIN
    -- Use explicit table aliases to avoid ambiguity
    -- Note: user_credits table uses 'total_credits' column name
    UPDATE public.user_profiles up
    SET 
        credits_total = COALESCE(uc.total_credits, 0),
        credits_remaining = COALESCE(uc.credits_remaining, 0),
        updated_at = NOW()
    FROM public.user_credits uc
    WHERE up.user_id = user_uuid
    AND uc.user_id = user_uuid;
    
    -- If no user_credits record exists, set to 0
    IF NOT FOUND THEN
        UPDATE public.user_profiles
        SET 
            credits_total = 0,
            credits_remaining = 0,
            updated_at = NOW()
        WHERE user_id = user_uuid;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- STEP 2: RECREATE ALL VIEWS THAT REFERENCE user_credits
-- ============================================================================

-- Drop and recreate admin_user_overview view (from schema/07-views.sql)
DROP VIEW IF EXISTS admin_user_overview CASCADE;

CREATE OR REPLACE VIEW admin_user_overview AS
SELECT 
    u.id as user_id,
    u.email,
    up.full_name,
    up.username,
    up.role,
    up.is_active,
    up.onboarding_completed,
    up.created_at as profile_created_at,
    COALESCE(us.status, 'no_subscription') as subscription_status,
    COALESCE(sp.name, 'no_plan') as plan_name,
    COALESCE(sp.display_name, 'No Plan') as plan_display_name,
    COALESCE(uc.total_credits, up.credits_total, 0) as credits_total,
    COALESCE(uc.credits_remaining, up.credits_remaining, 0) as credits_remaining,
    COALESCE(uc.credits_remaining, up.credits_remaining, 0) as available_credits,
    COALESCE(uc.total_credits, up.credits_total, 0) - COALESCE(uc.credits_remaining, up.credits_remaining, 0) as used_credits,
    (SELECT COUNT(*) FROM public.shorts WHERE user_id = u.id) as total_shorts,
    (SELECT COUNT(*) FROM public.shorts WHERE user_id = u.id AND status = 'completed') as completed_shorts,
    (SELECT COUNT(*) FROM public.shorts WHERE user_id = u.id AND status = 'published') as published_shorts,
    (SELECT COUNT(*) FROM public.products WHERE user_id = u.id) as total_products,
    (SELECT MAX(created_at) FROM public.user_activities WHERE user_id = u.id) as last_activity
FROM auth.users u
LEFT JOIN public.user_profiles up ON u.id = up.user_id
LEFT JOIN public.user_credits uc ON u.id = uc.user_id
LEFT JOIN public.user_subscriptions us ON u.id = us.user_id AND us.status = 'active'
LEFT JOIN public.subscription_plans sp ON us.plan_id = sp.id;

-- Grant permissions
GRANT SELECT ON admin_user_overview TO authenticated;

-- Drop and recreate admin_subscription_analytics view (from schema/07-views.sql)
DROP VIEW IF EXISTS admin_subscription_analytics CASCADE;

CREATE OR REPLACE VIEW admin_subscription_analytics AS
SELECT 
    COALESCE(sp.name, 'no_plan') as plan_name,
    COALESCE(sp.display_name, 'No Plan') as plan_display_name,
    COUNT(us.id)::bigint as subscriber_count,
    COUNT(CASE WHEN us.status = 'active' THEN 1 END)::bigint as active_subscribers,
    COUNT(CASE WHEN us.status = 'canceled' THEN 1 END)::bigint as canceled_subscribers,
    AVG(COALESCE(uc.credits_remaining, up.credits_remaining, 0))::numeric(10,2) as avg_credits_remaining,
    SUM(COALESCE(uc.total_credits, up.credits_total, 0))::bigint as total_credits_purchased
FROM auth.users u
LEFT JOIN public.user_profiles up ON u.id = up.user_id
LEFT JOIN public.user_subscriptions us ON u.id = us.user_id
LEFT JOIN public.subscription_plans sp ON us.plan_id = sp.id
LEFT JOIN public.user_credits uc ON u.id = uc.user_id
GROUP BY sp.id, sp.name, sp.display_name
ORDER BY subscriber_count DESC;

-- Grant permissions
GRANT SELECT ON admin_subscription_analytics TO authenticated;

-- ============================================================================
-- STEP 3: VERIFY NO OTHER OBJECTS REFERENCE uc.credits_total
-- ============================================================================

-- Check for any views that might reference credits_total incorrectly
DO $$
DECLARE
    view_record RECORD;
BEGIN
    FOR view_record IN 
        SELECT viewname, definition
        FROM pg_views
        WHERE schemaname = 'public'
    LOOP
        -- Check for uc.credits_total (incorrect) in view definition
        IF view_record.definition LIKE '%uc.credits_total%' OR view_record.definition LIKE '%user_credits.credits_total%' THEN
            RAISE WARNING 'View % may reference credits_total incorrectly', view_record.viewname;
        END IF;
    END LOOP;
END $$;

-- ============================================================================
-- STEP 4: COMMENTS
-- ============================================================================

COMMENT ON FUNCTION get_user_credits(UUID) IS 
'Gets user credits. Uses user_credits.total_credits (not credits_total).';

COMMENT ON FUNCTION get_user_status(UUID) IS 
'Gets user status. Uses user_credits.total_credits (not credits_total).';

COMMENT ON FUNCTION sync_user_credits_to_profile(UUID) IS 
'Syncs credits from user_credits.total_credits to user_profiles.credits_total.';

COMMENT ON VIEW admin_user_overview IS 
'Admin user overview view. Uses user_credits.total_credits (not credits_total) as source of truth.';

COMMENT ON VIEW admin_subscription_analytics IS 
'Subscription analytics view. Uses user_credits.total_credits (not credits_total) for aggregations.';

-- ============================================================================
-- STEP 5: VERIFY COLUMN EXISTS
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'user_credits' 
        AND column_name = 'total_credits'
    ) THEN
        RAISE EXCEPTION 'Column user_credits.total_credits does not exist. Run migration 22-fix-total-credits-column-name.sql first.';
    ELSE
        RAISE NOTICE '✓ Verified: user_credits.total_credits column exists';
    END IF;
END $$;

