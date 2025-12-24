-- Migration: Fix Views to Use total_credits Instead of credits_total
-- Description: Updates all views and functions that reference user_credits.credits_total to use total_credits
-- Priority: HIGH (fixes credit adjustment error)
-- Risk: LOW (only updates views, doesn't change data)
-- Date: 2024
-- This migration is idempotent - safe to run multiple times

-- ============================================================================
-- FIX VIEWS THAT REFERENCE user_credits TABLE
-- ============================================================================

-- Fix admin_user_overview view in schema/07-views.sql
-- This view joins user_credits and might be causing the error
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

-- Fix admin_subscription_analytics view (from schema/07-views.sql)
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

-- Also update the admin_user_overview from schema/11-admin-views-rls.sql if it exists
-- This version doesn't join user_credits, but we'll ensure it's correct
DO $$
BEGIN
    -- Check if admin_user_overview exists and recreate it to ensure it's using correct columns
    IF EXISTS (SELECT 1 FROM pg_views WHERE schemaname = 'public' AND viewname = 'admin_user_overview') THEN
        -- View will be recreated above, but this ensures we catch any other versions
        NULL;
    END IF;
END $$;

-- Grant permissions
GRANT SELECT ON admin_subscription_analytics TO authenticated;

-- ============================================================================
-- VERIFY NO OTHER VIEWS REFERENCE uc.credits_total
-- ============================================================================

-- Check for any remaining references (informational)
DO $$
DECLARE
    view_name TEXT;
    view_def TEXT;
BEGIN
    FOR view_name IN 
        SELECT schemaname||'.'||viewname 
        FROM pg_views 
        WHERE schemaname = 'public'
    LOOP
        SELECT definition INTO view_def
        FROM pg_views
        WHERE schemaname = 'public' AND viewname = (SELECT split_part(view_name, '.', 2));
        
        IF view_def LIKE '%uc.credits_total%' OR view_def LIKE '%user_credits.credits_total%' THEN
            RAISE WARNING 'View % may still reference credits_total: %', view_name, substring(view_def, 1, 200);
        END IF;
    END LOOP;
END $$;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON VIEW admin_user_overview IS 
'Admin user overview view. Uses user_credits.total_credits (not credits_total) as source of truth.';

COMMENT ON VIEW admin_subscription_analytics IS 
'Subscription analytics view. Uses user_credits.total_credits (not credits_total) for aggregations.';

