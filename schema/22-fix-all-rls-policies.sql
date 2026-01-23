-- Migration: Enable RLS and Create Policies for All Tables
-- Description: Comprehensive RLS setup for all public tables
-- Priority: HIGH (security)
-- Risk: LOW (only adds access control, no structure changes)
-- Date: 2024-01-14
-- This migration is idempotent - safe to run multiple times
--
-- CONSOLIDATED: Replaces migrations 28-44 (individual RLS fixes)

-- ============================================================================
-- CREDIT SYSTEM TABLES
-- ============================================================================

-- credit_actions
ALTER TABLE public.credit_actions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view credit actions" ON public.credit_actions;
DROP POLICY IF EXISTS "Authenticated users can view credit actions" ON public.credit_actions;
DROP POLICY IF EXISTS "Admins can manage credit actions" ON public.credit_actions;

CREATE POLICY "Authenticated users can view credit actions" ON public.credit_actions
FOR SELECT USING (auth.uid() IS NOT NULL);

CREATE POLICY "Admins can manage credit actions" ON public.credit_actions
FOR ALL USING (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
) WITH CHECK (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
);

GRANT SELECT ON public.credit_actions TO authenticated;
GRANT ALL ON public.credit_actions TO service_role;

-- credit_packages
ALTER TABLE public.credit_packages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view credit packages" ON public.credit_packages;
DROP POLICY IF EXISTS "Authenticated users can view credit packages" ON public.credit_packages;
DROP POLICY IF EXISTS "Admins can manage credit packages" ON public.credit_packages;

CREATE POLICY "Authenticated users can view credit packages" ON public.credit_packages
FOR SELECT USING (auth.uid() IS NOT NULL);

CREATE POLICY "Admins can manage credit packages" ON public.credit_packages
FOR ALL USING (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
) WITH CHECK (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
);

GRANT SELECT ON public.credit_packages TO authenticated;
GRANT ALL ON public.credit_packages TO service_role;

-- plan_credit_configs
ALTER TABLE public.plan_credit_configs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view plan credit configs" ON public.plan_credit_configs;
DROP POLICY IF EXISTS "Authenticated users can view plan credit configs" ON public.plan_credit_configs;
DROP POLICY IF EXISTS "Admins can manage plan credit configs" ON public.plan_credit_configs;

CREATE POLICY "Authenticated users can view plan credit configs" ON public.plan_credit_configs
FOR SELECT USING (auth.uid() IS NOT NULL);

CREATE POLICY "Admins can manage plan credit configs" ON public.plan_credit_configs
FOR ALL USING (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
) WITH CHECK (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
);

GRANT SELECT ON public.plan_credit_configs TO authenticated;
GRANT ALL ON public.plan_credit_configs TO service_role;

-- addon_credits
ALTER TABLE public.addon_credits ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can view their own addon credits" ON public.addon_credits;
DROP POLICY IF EXISTS "Admins can manage all addon credits" ON public.addon_credits;

CREATE POLICY "Users can view their own addon credits" ON public.addon_credits
FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Admins can manage all addon credits" ON public.addon_credits
FOR ALL USING (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
) WITH CHECK (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
);

GRANT SELECT ON public.addon_credits TO authenticated;
GRANT ALL ON public.addon_credits TO service_role;

-- credit_usage_tracking
ALTER TABLE public.credit_usage_tracking ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can view their own credit usage" ON public.credit_usage_tracking;
DROP POLICY IF EXISTS "Admins can manage all credit usage" ON public.credit_usage_tracking;

CREATE POLICY "Users can view their own credit usage" ON public.credit_usage_tracking
FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Admins can manage all credit usage" ON public.credit_usage_tracking
FOR ALL USING (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
) WITH CHECK (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
);

GRANT SELECT ON public.credit_usage_tracking TO authenticated;
GRANT ALL ON public.credit_usage_tracking TO service_role;

-- ============================================================================
-- SUBSCRIPTION SYSTEM TABLES
-- ============================================================================

-- subscription_plans
ALTER TABLE public.subscription_plans ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view subscription plans" ON public.subscription_plans;
DROP POLICY IF EXISTS "Authenticated users can view subscription plans" ON public.subscription_plans;
DROP POLICY IF EXISTS "Admins can manage subscription plans" ON public.subscription_plans;

CREATE POLICY "Authenticated users can view subscription plans" ON public.subscription_plans
FOR SELECT USING (auth.uid() IS NOT NULL);

CREATE POLICY "Admins can manage subscription plans" ON public.subscription_plans
FOR ALL USING (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
) WITH CHECK (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
);

GRANT SELECT ON public.subscription_plans TO authenticated;
GRANT ALL ON public.subscription_plans TO service_role;

-- ============================================================================
-- REFERRAL SYSTEM TABLES
-- ============================================================================

-- user_referrals
ALTER TABLE public.user_referrals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can view their own referrals" ON public.user_referrals;
DROP POLICY IF EXISTS "Users can view referrals they were referred by" ON public.user_referrals;
DROP POLICY IF EXISTS "Admins can manage all referrals" ON public.user_referrals;

CREATE POLICY "Users can view their own referrals" ON public.user_referrals
FOR SELECT USING (auth.uid() = referrer_user OR auth.uid() = referred_user);

CREATE POLICY "Admins can manage all referrals" ON public.user_referrals
FOR ALL USING (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
) WITH CHECK (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
);

GRANT SELECT ON public.user_referrals TO authenticated;
GRANT ALL ON public.user_referrals TO service_role;

-- referral_commissions
ALTER TABLE public.referral_commissions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can view their own commissions" ON public.referral_commissions;
DROP POLICY IF EXISTS "Admins can manage all commissions" ON public.referral_commissions;

CREATE POLICY "Users can view their own commissions" ON public.referral_commissions
FOR SELECT USING (auth.uid() = referrer_user);

CREATE POLICY "Admins can manage all commissions" ON public.referral_commissions
FOR ALL USING (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
) WITH CHECK (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
);

GRANT SELECT ON public.referral_commissions TO authenticated;
GRANT ALL ON public.referral_commissions TO service_role;

-- ============================================================================
-- STABILITY/MONITORING SYSTEM TABLES
-- ============================================================================

-- health_checks
ALTER TABLE public.health_checks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Authenticated users can view health checks" ON public.health_checks;
DROP POLICY IF EXISTS "Admins can manage health checks" ON public.health_checks;

CREATE POLICY "Authenticated users can view health checks" ON public.health_checks
FOR SELECT USING (auth.uid() IS NOT NULL);

CREATE POLICY "Admins can manage health checks" ON public.health_checks
FOR ALL USING (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
) WITH CHECK (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
);

GRANT SELECT ON public.health_checks TO authenticated;
GRANT ALL ON public.health_checks TO service_role;

-- error_logs
ALTER TABLE public.error_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can view their own error logs" ON public.error_logs;
DROP POLICY IF EXISTS "Admins can manage all error logs" ON public.error_logs;

CREATE POLICY "Users can view their own error logs" ON public.error_logs
FOR SELECT USING (auth.uid() = user_id OR auth.uid() IS NULL);

CREATE POLICY "Admins can manage all error logs" ON public.error_logs
FOR ALL USING (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
) WITH CHECK (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
);

GRANT SELECT ON public.error_logs TO authenticated;
GRANT ALL ON public.error_logs TO service_role;

-- retry_attempts
ALTER TABLE public.retry_attempts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Admins can view all retry attempts" ON public.retry_attempts;
DROP POLICY IF EXISTS "Admins can manage retry attempts" ON public.retry_attempts;

CREATE POLICY "Admins can view all retry attempts" ON public.retry_attempts
FOR SELECT USING (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
);

CREATE POLICY "Admins can manage retry attempts" ON public.retry_attempts
FOR ALL USING (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
) WITH CHECK (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
);

GRANT SELECT ON public.retry_attempts TO authenticated;
GRANT ALL ON public.retry_attempts TO service_role;

-- alert_rules
ALTER TABLE public.alert_rules ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Admins can manage alert rules" ON public.alert_rules;

CREATE POLICY "Admins can manage alert rules" ON public.alert_rules
FOR ALL USING (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
) WITH CHECK (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
);

GRANT SELECT ON public.alert_rules TO authenticated;
GRANT ALL ON public.alert_rules TO service_role;

-- alerts
ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Admins can view all alerts" ON public.alerts;
DROP POLICY IF EXISTS "Admins can manage alerts" ON public.alerts;

CREATE POLICY "Admins can view all alerts" ON public.alerts
FOR SELECT USING (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
);

CREATE POLICY "Admins can manage alerts" ON public.alerts
FOR ALL USING (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
) WITH CHECK (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
);

GRANT SELECT ON public.alerts TO authenticated;
GRANT ALL ON public.alerts TO service_role;

-- ============================================================================
-- CONTENT SYSTEM TABLES
-- ============================================================================

-- categories
ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Authenticated users can view categories" ON public.categories;
DROP POLICY IF EXISTS "Admins can manage categories" ON public.categories;

CREATE POLICY "Authenticated users can view categories" ON public.categories
FOR SELECT USING (auth.uid() IS NOT NULL);

CREATE POLICY "Admins can manage categories" ON public.categories
FOR ALL USING (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
) WITH CHECK (
    EXISTS (SELECT 1 FROM public.user_profiles WHERE user_profiles.user_id = auth.uid() AND user_profiles.role = 'admin')
);

GRANT SELECT ON public.categories TO authenticated;
GRANT ALL ON public.categories TO service_role;

-- ============================================================================
-- VERIFICATION
-- ============================================================================

DO $$
DECLARE
    table_name TEXT;
    rls_enabled BOOLEAN;
    policy_count INTEGER;
    tables_checked INTEGER := 0;
    tables_secure INTEGER := 0;
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Verifying RLS on all tables...';
    RAISE NOTICE '========================================';
    
    FOR table_name IN 
        SELECT unnest(ARRAY[
            'credit_actions', 'credit_packages', 'plan_credit_configs', 'addon_credits', 'credit_usage_tracking',
            'subscription_plans',
            'user_referrals', 'referral_commissions',
            'health_checks', 'error_logs', 'retry_attempts', 'alert_rules', 'alerts',
            'categories'
        ])
    LOOP
        tables_checked := tables_checked + 1;
        
        SELECT relrowsecurity INTO rls_enabled
        FROM pg_class
        WHERE relname = table_name AND relnamespace = 'public'::regnamespace;
        
        SELECT COUNT(*) INTO policy_count
        FROM pg_policies
        WHERE schemaname = 'public' AND tablename = table_name;
        
        IF rls_enabled AND policy_count > 0 THEN
            tables_secure := tables_secure + 1;
            RAISE NOTICE '✓ % - RLS enabled, % policies', table_name, policy_count;
        ELSE
            RAISE WARNING '✗ % - RLS: %, Policies: %', table_name, rls_enabled, policy_count;
        END IF;
    END LOOP;
    
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Result: %/% tables are secure', tables_secure, tables_checked;
    RAISE NOTICE '========================================';
END $$;
