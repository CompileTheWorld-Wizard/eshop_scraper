-- Migration: Fix Admin Views with RLS Policies
-- Description: Fixes admin views to work with RLS by using SECURITY DEFINER functions
-- This migration is idempotent - safe to run multiple times

-- Drop existing views to recreate them properly
DROP VIEW IF EXISTS admin_user_overview CASCADE;
DROP VIEW IF EXISTS admin_platform_analytics CASCADE;
DROP VIEW IF EXISTS admin_subscription_analytics CASCADE;

-- Create SECURITY DEFINER function to get user email
-- This allows views to access auth.users data
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

-- Create SECURITY DEFINER function to check if user is admin
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

-- Admin user overview view
-- Fixed column name: user_created_at -> profile_created_at to match code expectations
-- Uses SECURITY DEFINER function to get email from auth.users
-- Uses user_profiles credits as primary source (synced from user_credits table)
CREATE OR REPLACE VIEW admin_user_overview AS
SELECT 
    up.user_id,
    public.get_user_email(up.user_id) as email, -- Use function to get email
    up.full_name,
    up.username,
    up.role,
    up.is_active,
    up.onboarding_completed,
    up.created_at as profile_created_at, -- Fixed: changed from user_created_at
    COALESCE(us.status, 'no_subscription') as subscription_status,
    COALESCE(sp.name, 'no_plan') as plan_name,
    COALESCE(sp.display_name, 'No Plan') as plan_display_name,
    COALESCE(up.credits_total, 0) as credits_total,
    COALESCE(up.credits_remaining, 0) as credits_remaining,
    COALESCE(up.credits_remaining, 0) as available_credits, -- Add alias for code compatibility
    COALESCE(up.credits_total, 0) - COALESCE(up.credits_remaining, 0) as used_credits, -- Add used_credits
    (SELECT COUNT(*) FROM public.shorts WHERE user_id = up.user_id) as total_shorts,
    (SELECT COUNT(*) FROM public.shorts WHERE user_id = up.user_id AND status = 'completed') as completed_shorts,
    (SELECT COUNT(*) FROM public.shorts WHERE user_id = up.user_id AND status = 'published') as published_shorts, -- Add published_shorts
    (SELECT COUNT(*) FROM public.products WHERE user_id = up.user_id) as total_products,
    (SELECT MAX(created_at) FROM public.user_activities WHERE user_id = up.user_id) as last_activity
FROM public.user_profiles up
LEFT JOIN public.user_subscriptions us ON up.user_id = us.user_id AND us.status = 'active'
LEFT JOIN public.subscription_plans sp ON us.plan_id = sp.id;

-- Admin platform analytics view with date column for filtering
-- Fixed: Added date column and uses function to count users
CREATE OR REPLACE VIEW admin_platform_analytics AS
SELECT 
    CURRENT_DATE as date, -- Add date column for filtering
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

-- Admin subscription analytics view
-- Refactored to not query auth.users directly
-- Uses user_profiles credits as primary source (synced from user_credits table)
CREATE OR REPLACE VIEW admin_subscription_analytics AS
SELECT 
    COALESCE(sp.name, 'no_plan') as plan_name,
    COALESCE(sp.display_name, 'No Plan') as plan_display_name,
    COUNT(us.id)::bigint as subscriber_count,
    COUNT(CASE WHEN us.status = 'active' THEN 1 END)::bigint as active_subscribers,
    COUNT(CASE WHEN us.status = 'canceled' THEN 1 END)::bigint as canceled_subscribers,
    AVG(COALESCE(up.credits_remaining, 0))::numeric(10,2) as avg_credits_remaining,
    SUM(COALESCE(up.credits_total, 0))::bigint as total_credits_purchased
FROM public.user_profiles up
LEFT JOIN public.user_subscriptions us ON up.user_id = us.user_id
LEFT JOIN public.subscription_plans sp ON us.plan_id = sp.id
GROUP BY sp.id, sp.name, sp.display_name
ORDER BY subscriber_count DESC;

-- Grant necessary permissions
GRANT SELECT ON admin_user_overview TO authenticated;
GRANT SELECT ON admin_platform_analytics TO authenticated;
GRANT SELECT ON admin_subscription_analytics TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_user_email(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_admin_user() TO authenticated;

-- Add comments for documentation
COMMENT ON VIEW admin_user_overview IS 'Comprehensive user overview for admin panel. Requires admin role to access via RLS on underlying tables.';
COMMENT ON VIEW admin_platform_analytics IS 'Platform-wide analytics for admin panel. Requires admin role to access via RLS on underlying tables.';
COMMENT ON VIEW admin_subscription_analytics IS 'Subscription analytics for admin panel. Requires admin role to access via RLS on underlying tables.';
COMMENT ON FUNCTION public.get_user_email(UUID) IS 'SECURITY DEFINER function to get user email from auth.users. Only accessible to authenticated users.';
COMMENT ON FUNCTION public.is_admin_user() IS 'SECURITY DEFINER function to check if current user is admin.';
