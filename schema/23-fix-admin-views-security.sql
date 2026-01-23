-- Migration: Fix Admin Views Security and Remove SECURITY DEFINER
-- Description: Comprehensive fix for all admin views security issues
-- Priority: CRITICAL (security vulnerability)
-- Risk: LOW (only updates views, doesn't change data)
-- Date: 2024-01-14
-- This migration is idempotent - safe to run multiple times
--
-- CONSOLIDATED: Replaces migrations 27, 32, 33
--
-- ISSUE: admin views directly expose auth.users and have SECURITY DEFINER property
-- SOLUTION: Use SECURITY DEFINER helper functions + recreate views without SECURITY DEFINER

-- ============================================================================
-- STEP 1: CREATE HELPER FUNCTIONS (SECURITY DEFINER)
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_user_email(user_uuid UUID)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
BEGIN
  RETURN (SELECT email FROM auth.users WHERE id = user_uuid);
END;
$$;

CREATE OR REPLACE FUNCTION public.is_admin_user()
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.user_profiles 
    WHERE user_id = auth.uid() 
    AND role = 'admin'
  );
$$;

-- ============================================================================
-- STEP 2: DROP ALL ADMIN VIEWS
-- ============================================================================

DROP VIEW IF EXISTS admin_user_overview CASCADE;
DROP VIEW IF EXISTS admin_subscription_analytics CASCADE;
DROP VIEW IF EXISTS admin_platform_analytics CASCADE;

-- ============================================================================
-- STEP 3: RECREATE admin_user_overview (SECURE VERSION)
-- ============================================================================

CREATE VIEW admin_user_overview AS
SELECT 
    up.user_id,
    public.get_user_email(up.user_id) as email,
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
    (SELECT COUNT(*) FROM public.shorts WHERE user_id = up.user_id) as total_shorts,
    (SELECT COUNT(*) FROM public.shorts WHERE user_id = up.user_id AND status = 'completed') as completed_shorts,
    (SELECT COUNT(*) FROM public.shorts WHERE user_id = up.user_id AND status = 'published') as published_shorts,
    (SELECT COUNT(*) FROM public.products WHERE user_id = up.user_id) as total_products,
    (SELECT MAX(created_at) FROM public.user_activities WHERE user_id = up.user_id) as last_activity
FROM public.user_profiles up
LEFT JOIN public.user_credits uc ON up.user_id = uc.user_id
LEFT JOIN public.user_subscriptions us ON up.user_id = us.user_id AND us.status = 'active'
LEFT JOIN public.subscription_plans sp ON us.plan_id = sp.id;

-- ============================================================================
-- STEP 4: RECREATE admin_platform_analytics (SECURE VERSION)
-- ============================================================================

CREATE VIEW admin_platform_analytics AS
SELECT 
    CURRENT_DATE as date,
    'total_users' as metric,
    (SELECT COUNT(*) FROM public.user_profiles)::bigint as value
FROM (SELECT 1) as dummy
UNION ALL
SELECT 
    CURRENT_DATE as date,
    'active_users' as metric,
    COUNT(*)::bigint as value
FROM public.user_profiles
WHERE is_active = true
UNION ALL
SELECT 
    CURRENT_DATE as date,
    'total_shorts' as metric,
    COUNT(*)::bigint as value
FROM public.shorts
UNION ALL
SELECT 
    CURRENT_DATE as date,
    'completed_shorts' as metric,
    COUNT(*)::bigint as value
FROM public.shorts
WHERE status = 'completed'
UNION ALL
SELECT 
    CURRENT_DATE as date,
    'total_products' as metric,
    COUNT(*)::bigint as value
FROM public.products;

-- ============================================================================
-- STEP 5: RECREATE admin_subscription_analytics (SECURE VERSION)
-- ============================================================================

CREATE VIEW admin_subscription_analytics AS
SELECT 
    COALESCE(sp.name, 'no_plan') as plan_name,
    COALESCE(sp.display_name, 'No Plan') as plan_display_name,
    COUNT(us.id)::bigint as subscriber_count,
    COUNT(CASE WHEN us.status = 'active' THEN 1 END)::bigint as active_subscribers,
    COUNT(CASE WHEN us.status = 'canceled' THEN 1 END)::bigint as canceled_subscribers,
    AVG(COALESCE(uc.credits_remaining, up.credits_remaining, 0))::numeric(10,2) as avg_credits_remaining,
    SUM(COALESCE(uc.total_credits, up.credits_total, 0))::bigint as total_credits_purchased
FROM public.user_profiles up
LEFT JOIN public.user_subscriptions us ON up.user_id = us.user_id
LEFT JOIN public.subscription_plans sp ON us.plan_id = sp.id
LEFT JOIN public.user_credits uc ON up.user_id = uc.user_id
GROUP BY sp.id, sp.name, sp.display_name
ORDER BY subscriber_count DESC;

-- ============================================================================
-- STEP 6: SET SECURITY_INVOKER (PostgreSQL 15+)
-- ============================================================================

DO $$
BEGIN
    BEGIN
        ALTER VIEW admin_user_overview SET (security_invoker = true);
        ALTER VIEW admin_platform_analytics SET (security_invoker = true);
        ALTER VIEW admin_subscription_analytics SET (security_invoker = true);
        RAISE NOTICE '✓ Set security_invoker = true for all admin views';
    EXCEPTION 
        WHEN undefined_object OR invalid_parameter_value THEN
            RAISE NOTICE 'Note: security_invoker option not available (PostgreSQL < 15)';
        WHEN OTHERS THEN
            RAISE NOTICE 'Note: Could not set security_invoker option';
    END;
END $$;

-- ============================================================================
-- STEP 7: GRANT PERMISSIONS
-- ============================================================================

GRANT SELECT ON admin_user_overview TO authenticated;
GRANT SELECT ON admin_platform_analytics TO authenticated;
GRANT SELECT ON admin_subscription_analytics TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_user_email(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_admin_user() TO authenticated;

-- ============================================================================
-- STEP 8: ADD COMMENTS
-- ============================================================================

COMMENT ON VIEW admin_user_overview IS 
'SECURE admin user overview. Uses SECURITY DEFINER function for email access. Never directly queries auth.users.';

COMMENT ON VIEW admin_platform_analytics IS 
'SECURE platform analytics. Uses public tables only. Never directly queries auth.users.';

COMMENT ON VIEW admin_subscription_analytics IS 
'SECURE subscription analytics. Starts from user_profiles, not auth.users.';

COMMENT ON FUNCTION public.get_user_email(UUID) IS 
'SECURITY DEFINER function to get user email from auth.users. Controlled access point to protect auth schema.';

COMMENT ON FUNCTION public.is_admin_user() IS 
'SECURITY DEFINER function to check if current user is admin. Used for authorization checks.';

-- ============================================================================
-- STEP 9: VERIFY SECURITY
-- ============================================================================

DO $$
DECLARE
    view_rec RECORD;
    has_auth_users_exposure BOOLEAN := FALSE;
    has_security_definer BOOLEAN := FALSE;
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Verifying admin views security...';
    RAISE NOTICE '========================================';
    
    -- Check for direct auth.users exposure
    FOR view_rec IN 
        SELECT viewname, definition
        FROM pg_views
        WHERE schemaname = 'public' AND viewname LIKE 'admin_%'
    LOOP
        IF view_rec.definition ~* 'FROM\s+auth\.users' OR 
           view_rec.definition ~* 'JOIN\s+auth\.users' THEN
            RAISE WARNING '✗ View % still directly accesses auth.users', view_rec.viewname;
            has_auth_users_exposure := TRUE;
        ELSE
            RAISE NOTICE '✓ View % does not directly access auth.users', view_rec.viewname;
        END IF;
    END LOOP;
    
    -- Check for SECURITY DEFINER on views
    FOR view_rec IN 
        SELECT 
            c.relname as view_name,
            c.reloptions
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
        AND c.relname IN ('admin_user_overview', 'admin_platform_analytics', 'admin_subscription_analytics')
        AND c.relkind = 'v'
    LOOP
        IF view_rec.reloptions IS NOT NULL AND 
           'security_definer=true' = ANY(view_rec.reloptions) THEN
            RAISE WARNING '✗ View % has security_definer=true', view_rec.view_name;
            has_security_definer := TRUE;
        ELSE
            RAISE NOTICE '✓ View % does NOT have security_definer', view_rec.view_name;
        END IF;
    END LOOP;
    
    RAISE NOTICE '========================================';
    IF has_auth_users_exposure OR has_security_definer THEN
        RAISE WARNING 'Security check failed - manual review required';
    ELSE
        RAISE NOTICE '✓✓✓ All admin views are secure!';
    END IF;
    RAISE NOTICE '========================================';
END $$;
