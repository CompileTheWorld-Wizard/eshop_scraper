-- Auto-Promo AI Database Views
-- Admin views for analytics and user management
-- NOTE: These views require RLS policies for admin access
-- Run migration 13-fix-admin-views-rls.sql to set up proper RLS policies

-- Admin user overview view
-- Fixed: Uses profile_created_at to match code expectations
CREATE OR REPLACE VIEW admin_user_overview AS
SELECT 
    u.id as user_id,
    u.email,
    up.full_name,
    up.username,
    up.role,
    up.is_active,
    up.onboarding_completed,
    up.created_at as profile_created_at, -- Fixed: changed from user_created_at
    COALESCE(us.status, 'no_subscription') as subscription_status,
    COALESCE(sp.name, 'no_plan') as plan_name,
    COALESCE(sp.display_name, 'No Plan') as plan_display_name,
    COALESCE(uc.credits_total, up.credits_total, 0) as credits_total,
    COALESCE(uc.credits_remaining, up.credits_remaining, 0) as credits_remaining,
    COALESCE(uc.credits_remaining, up.credits_remaining, 0) as available_credits, -- Add alias for code compatibility
    COALESCE(uc.credits_total, up.credits_total, 0) - COALESCE(uc.credits_remaining, up.credits_remaining, 0) as used_credits, -- Add used_credits
    (SELECT COUNT(*) FROM public.shorts WHERE user_id = u.id) as total_shorts,
    (SELECT COUNT(*) FROM public.shorts WHERE user_id = u.id AND status = 'completed') as completed_shorts,
    (SELECT COUNT(*) FROM public.shorts WHERE user_id = u.id AND status = 'published') as published_shorts, -- Add published_shorts
    (SELECT COUNT(*) FROM public.products WHERE user_id = u.id) as total_products,
    (SELECT MAX(created_at) FROM public.user_activities WHERE user_id = u.id) as last_activity
FROM auth.users u
LEFT JOIN public.user_profiles up ON u.id = up.user_id
LEFT JOIN public.user_credits uc ON u.id = uc.user_id
LEFT JOIN public.user_subscriptions us ON u.id = us.user_id AND us.status = 'active'
LEFT JOIN public.subscription_plans sp ON us.plan_id = sp.id;

-- Admin platform analytics view
-- Fixed: Added date column for proper filtering
CREATE OR REPLACE VIEW admin_platform_analytics AS
SELECT 
    CURRENT_DATE as date, -- Add date column for filtering
    'total_users' as metric,
    COUNT(*)::bigint as value
FROM auth.users
UNION ALL
SELECT 
    CURRENT_DATE as date,
    'active_users' as metric,
    COUNT(*)::bigint as value
FROM auth.users u
JOIN public.user_profiles up ON u.id = up.user_id
WHERE up.is_active = true
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
CREATE OR REPLACE VIEW admin_subscription_analytics AS
SELECT 
    COALESCE(sp.name, 'no_plan') as plan_name,
    COALESCE(sp.display_name, 'No Plan') as plan_display_name,
    COUNT(us.id)::bigint as subscriber_count,
    COUNT(CASE WHEN us.status = 'active' THEN 1 END)::bigint as active_subscribers,
    COUNT(CASE WHEN us.status = 'canceled' THEN 1 END)::bigint as canceled_subscribers,
    AVG(COALESCE(uc.credits_remaining, up.credits_remaining, 0))::numeric(10,2) as avg_credits_remaining,
    SUM(COALESCE(uc.credits_total, up.credits_total, 0))::bigint as total_credits_purchased
FROM auth.users u
LEFT JOIN public.user_profiles up ON u.id = up.user_id
LEFT JOIN public.user_subscriptions us ON u.id = us.user_id
LEFT JOIN public.subscription_plans sp ON us.plan_id = sp.id
LEFT JOIN public.user_credits uc ON u.id = uc.user_id
GROUP BY sp.id, sp.name, sp.display_name
ORDER BY subscriber_count DESC; 