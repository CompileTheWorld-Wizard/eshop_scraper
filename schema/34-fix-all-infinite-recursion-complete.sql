-- ============================================================================
-- Migration: Fix ALL Infinite Recursion in RLS Policies
-- Description: Replace all circular admin checks with helper function
-- Date: 2026-01-19
-- ============================================================================

-- STEP 1: Create helper function to check admin status (bypasses RLS)
-- SECURITY DEFINER makes this function run with elevated privileges, bypassing RLS
-- This prevents infinite recursion when checking admin status
CREATE OR REPLACE FUNCTION public.is_admin(user_uuid UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
BEGIN
    -- Returns false if user_uuid is NULL (anonymous users)
    IF user_uuid IS NULL THEN
        RETURN false;
    END IF;
    
    -- Check if user has admin role (bypasses RLS due to SECURITY DEFINER)
    RETURN EXISTS (
        SELECT 1 
        FROM public.user_profiles 
        WHERE user_id = user_uuid 
        AND role = 'admin'
    );
EXCEPTION
    WHEN OTHERS THEN
        -- If any error occurs (e.g., table doesn't exist), return false
        RETURN false;
END;
$$;

GRANT EXECUTE ON FUNCTION public.is_admin(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_admin(UUID) TO anon;

-- STEP 1.5: Create a helper to manually set first admin (run this after fixing policies)
-- To create your first admin, uncomment and run this after applying the fixes:
-- UPDATE public.user_profiles SET role = 'admin' WHERE user_id = 'YOUR_USER_ID_HERE';
-- Or using email:
-- UPDATE public.user_profiles SET role = 'admin' 
-- WHERE user_id = (SELECT id FROM auth.users WHERE email = 'your@email.com');

-- STEP 2: Drop and recreate ALL policies that check for admin
-- This replaces: (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
-- With: public.is_admin(auth.uid())

-- ============================================================================
-- user_profiles (CRITICAL - causes infinite recursion)
-- ============================================================================
DROP POLICY IF EXISTS "user_profiles_select" ON public.user_profiles;
DROP POLICY IF EXISTS "user_profiles_insert" ON public.user_profiles;
DROP POLICY IF EXISTS "user_profiles_update" ON public.user_profiles;

CREATE POLICY "user_profiles_select" ON public.user_profiles FOR SELECT USING (
    (select auth.uid()) = user_id OR public.is_admin(auth.uid())
);
CREATE POLICY "user_profiles_insert" ON public.user_profiles FOR INSERT WITH CHECK ((select auth.uid()) = user_id);
CREATE POLICY "user_profiles_update" ON public.user_profiles FOR UPDATE USING ((select auth.uid()) = user_id) WITH CHECK ((select auth.uid()) = user_id);

-- ============================================================================
-- products
-- ============================================================================
DROP POLICY IF EXISTS "products_select" ON public.products;
CREATE POLICY "products_select" ON public.products FOR SELECT USING (
    (select auth.uid()) = user_id OR public.is_admin(auth.uid())
);

-- ============================================================================
-- shorts
-- ============================================================================
DROP POLICY IF EXISTS "shorts_select" ON public.shorts;
CREATE POLICY "shorts_select" ON public.shorts FOR SELECT USING (
    (select auth.uid()) = user_id OR public.is_admin(auth.uid())
);

-- ============================================================================
-- user_credits
-- ============================================================================
DROP POLICY IF EXISTS "user_credits_select" ON public.user_credits;
CREATE POLICY "user_credits_select" ON public.user_credits FOR SELECT USING (
    (select auth.uid()) = user_id OR public.is_admin(auth.uid())
);

-- ============================================================================
-- user_subscriptions
-- ============================================================================
DROP POLICY IF EXISTS "user_subscriptions_select" ON public.user_subscriptions;
CREATE POLICY "user_subscriptions_select" ON public.user_subscriptions FOR SELECT USING (
    (select auth.uid()) = user_id OR public.is_admin(auth.uid())
);

-- ============================================================================
-- credit_transactions
-- ============================================================================
DROP POLICY IF EXISTS "credit_transactions_select" ON public.credit_transactions;
CREATE POLICY "credit_transactions_select" ON public.credit_transactions FOR SELECT USING (
    (select auth.uid()) = user_id OR public.is_admin(auth.uid())
);

-- ============================================================================
-- credit_adjustments
-- ============================================================================
DROP POLICY IF EXISTS "credit_adjustments_select" ON public.credit_adjustments;
DROP POLICY IF EXISTS "credit_adjustments_insert" ON public.credit_adjustments;
DROP POLICY IF EXISTS "credit_adjustments_update" ON public.credit_adjustments;
DROP POLICY IF EXISTS "credit_adjustments_delete" ON public.credit_adjustments;

CREATE POLICY "credit_adjustments_select" ON public.credit_adjustments FOR SELECT USING (
    (select auth.uid()) = user_id OR public.is_admin(auth.uid())
);
CREATE POLICY "credit_adjustments_insert" ON public.credit_adjustments FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "credit_adjustments_update" ON public.credit_adjustments FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "credit_adjustments_delete" ON public.credit_adjustments FOR DELETE USING (public.is_admin(auth.uid()));

-- ============================================================================
-- user_activities
-- ============================================================================
DROP POLICY IF EXISTS "user_activities_select" ON public.user_activities;
CREATE POLICY "user_activities_select" ON public.user_activities FOR SELECT USING (
    (select auth.uid()) = user_id OR public.is_admin(auth.uid())
);

-- ============================================================================
-- credit_usage_tracking
-- ============================================================================
DROP POLICY IF EXISTS "credit_usage_tracking_select" ON public.credit_usage_tracking;
DROP POLICY IF EXISTS "credit_usage_tracking_insert" ON public.credit_usage_tracking;
DROP POLICY IF EXISTS "credit_usage_tracking_update" ON public.credit_usage_tracking;
DROP POLICY IF EXISTS "credit_usage_tracking_delete" ON public.credit_usage_tracking;

CREATE POLICY "credit_usage_tracking_select" ON public.credit_usage_tracking FOR SELECT USING (
    (select auth.uid()) = user_id OR public.is_admin(auth.uid())
);
CREATE POLICY "credit_usage_tracking_insert" ON public.credit_usage_tracking FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "credit_usage_tracking_update" ON public.credit_usage_tracking FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "credit_usage_tracking_delete" ON public.credit_usage_tracking FOR DELETE USING (public.is_admin(auth.uid()));

-- ============================================================================
-- addon_credits
-- ============================================================================
DROP POLICY IF EXISTS "addon_credits_select" ON public.addon_credits;
DROP POLICY IF EXISTS "addon_credits_insert" ON public.addon_credits;
DROP POLICY IF EXISTS "addon_credits_update" ON public.addon_credits;
DROP POLICY IF EXISTS "addon_credits_delete" ON public.addon_credits;

CREATE POLICY "addon_credits_select" ON public.addon_credits FOR SELECT USING (
    (select auth.uid()) = user_id OR public.is_admin(auth.uid())
);
CREATE POLICY "addon_credits_insert" ON public.addon_credits FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "addon_credits_update" ON public.addon_credits FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "addon_credits_delete" ON public.addon_credits FOR DELETE USING (public.is_admin(auth.uid()));

-- ============================================================================
-- user_referrals
-- ============================================================================
DROP POLICY IF EXISTS "user_referrals_select" ON public.user_referrals;
DROP POLICY IF EXISTS "user_referrals_insert" ON public.user_referrals;
DROP POLICY IF EXISTS "user_referrals_update" ON public.user_referrals;
DROP POLICY IF EXISTS "user_referrals_delete" ON public.user_referrals;

CREATE POLICY "user_referrals_select" ON public.user_referrals FOR SELECT USING (
    (select auth.uid()) = referrer_user 
    OR (select auth.uid()) = referred_user 
    OR public.is_admin(auth.uid())
);
CREATE POLICY "user_referrals_insert" ON public.user_referrals FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "user_referrals_update" ON public.user_referrals FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "user_referrals_delete" ON public.user_referrals FOR DELETE USING (public.is_admin(auth.uid()));

-- ============================================================================
-- referral_commissions
-- ============================================================================
DROP POLICY IF EXISTS "referral_commissions_select" ON public.referral_commissions;
DROP POLICY IF EXISTS "referral_commissions_insert" ON public.referral_commissions;
DROP POLICY IF EXISTS "referral_commissions_update" ON public.referral_commissions;
DROP POLICY IF EXISTS "referral_commissions_delete" ON public.referral_commissions;

CREATE POLICY "referral_commissions_select" ON public.referral_commissions FOR SELECT USING (
    (select auth.uid()) = referrer_user 
    OR (select auth.uid()) = referred_user 
    OR public.is_admin(auth.uid())
);
CREATE POLICY "referral_commissions_insert" ON public.referral_commissions FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "referral_commissions_update" ON public.referral_commissions FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "referral_commissions_delete" ON public.referral_commissions FOR DELETE USING (public.is_admin(auth.uid()));

-- ============================================================================
-- error_logs
-- ============================================================================
DROP POLICY IF EXISTS "error_logs_select" ON public.error_logs;
DROP POLICY IF EXISTS "error_logs_insert" ON public.error_logs;
DROP POLICY IF EXISTS "error_logs_update" ON public.error_logs;
DROP POLICY IF EXISTS "error_logs_delete" ON public.error_logs;

CREATE POLICY "error_logs_select" ON public.error_logs FOR SELECT USING (
    (select auth.uid()) = user_id OR public.is_admin(auth.uid())
);
CREATE POLICY "error_logs_insert" ON public.error_logs FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "error_logs_update" ON public.error_logs FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "error_logs_delete" ON public.error_logs FOR DELETE USING (public.is_admin(auth.uid()));

-- ============================================================================
-- brand_kit_activities
-- ============================================================================
DROP POLICY IF EXISTS "brand_kit_activities_select" ON public.brand_kit_activities;
DROP POLICY IF EXISTS "brand_kit_activities_update" ON public.brand_kit_activities;
DROP POLICY IF EXISTS "brand_kit_activities_delete" ON public.brand_kit_activities;

CREATE POLICY "brand_kit_activities_select" ON public.brand_kit_activities FOR SELECT USING (
    (select auth.uid()) = user_id OR public.is_admin(auth.uid())
);
CREATE POLICY "brand_kit_activities_update" ON public.brand_kit_activities FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "brand_kit_activities_delete" ON public.brand_kit_activities FOR DELETE USING (public.is_admin(auth.uid()));

-- ============================================================================
-- Admin-only tables
-- ============================================================================
DROP POLICY IF EXISTS "subscription_plans_insert" ON public.subscription_plans;
DROP POLICY IF EXISTS "subscription_plans_update" ON public.subscription_plans;
DROP POLICY IF EXISTS "subscription_plans_delete" ON public.subscription_plans;

CREATE POLICY "subscription_plans_insert" ON public.subscription_plans FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "subscription_plans_update" ON public.subscription_plans FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "subscription_plans_delete" ON public.subscription_plans FOR DELETE USING (public.is_admin(auth.uid()));

-- credit_actions
DROP POLICY IF EXISTS "credit_actions_insert" ON public.credit_actions;
DROP POLICY IF EXISTS "credit_actions_update" ON public.credit_actions;
DROP POLICY IF EXISTS "credit_actions_delete" ON public.credit_actions;

CREATE POLICY "credit_actions_insert" ON public.credit_actions FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "credit_actions_update" ON public.credit_actions FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "credit_actions_delete" ON public.credit_actions FOR DELETE USING (public.is_admin(auth.uid()));

-- credit_packages
DROP POLICY IF EXISTS "credit_packages_insert" ON public.credit_packages;
DROP POLICY IF EXISTS "credit_packages_update" ON public.credit_packages;
DROP POLICY IF EXISTS "credit_packages_delete" ON public.credit_packages;

CREATE POLICY "credit_packages_insert" ON public.credit_packages FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "credit_packages_update" ON public.credit_packages FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "credit_packages_delete" ON public.credit_packages FOR DELETE USING (public.is_admin(auth.uid()));

-- plan_credit_configs
DROP POLICY IF EXISTS "plan_credit_configs_insert" ON public.plan_credit_configs;
DROP POLICY IF EXISTS "plan_credit_configs_update" ON public.plan_credit_configs;
DROP POLICY IF EXISTS "plan_credit_configs_delete" ON public.plan_credit_configs;

CREATE POLICY "plan_credit_configs_insert" ON public.plan_credit_configs FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "plan_credit_configs_update" ON public.plan_credit_configs FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "plan_credit_configs_delete" ON public.plan_credit_configs FOR DELETE USING (public.is_admin(auth.uid()));

-- health_checks
DROP POLICY IF EXISTS "health_checks_insert" ON public.health_checks;
DROP POLICY IF EXISTS "health_checks_update" ON public.health_checks;
DROP POLICY IF EXISTS "health_checks_delete" ON public.health_checks;

CREATE POLICY "health_checks_insert" ON public.health_checks FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "health_checks_update" ON public.health_checks FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "health_checks_delete" ON public.health_checks FOR DELETE USING (public.is_admin(auth.uid()));

-- categories
DROP POLICY IF EXISTS "categories_insert" ON public.categories;
DROP POLICY IF EXISTS "categories_update" ON public.categories;
DROP POLICY IF EXISTS "categories_delete" ON public.categories;

CREATE POLICY "categories_insert" ON public.categories FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "categories_update" ON public.categories FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "categories_delete" ON public.categories FOR DELETE USING (public.is_admin(auth.uid()));

-- brand_kit_categories
DROP POLICY IF EXISTS "brand_kit_categories_select" ON public.brand_kit_categories;
DROP POLICY IF EXISTS "brand_kit_categories_insert" ON public.brand_kit_categories;
DROP POLICY IF EXISTS "brand_kit_categories_update" ON public.brand_kit_categories;
DROP POLICY IF EXISTS "brand_kit_categories_delete" ON public.brand_kit_categories;

CREATE POLICY "brand_kit_categories_select" ON public.brand_kit_categories FOR SELECT USING (is_active = true OR public.is_admin(auth.uid()));
CREATE POLICY "brand_kit_categories_insert" ON public.brand_kit_categories FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "brand_kit_categories_update" ON public.brand_kit_categories FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "brand_kit_categories_delete" ON public.brand_kit_categories FOR DELETE USING (public.is_admin(auth.uid()));

-- brand_assets
DROP POLICY IF EXISTS "brand_assets_select" ON public.brand_assets;
DROP POLICY IF EXISTS "brand_assets_insert" ON public.brand_assets;
DROP POLICY IF EXISTS "brand_assets_update" ON public.brand_assets;
DROP POLICY IF EXISTS "brand_assets_delete" ON public.brand_assets;

CREATE POLICY "brand_assets_select" ON public.brand_assets FOR SELECT USING (is_active = true OR public.is_admin(auth.uid()));
CREATE POLICY "brand_assets_insert" ON public.brand_assets FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "brand_assets_update" ON public.brand_assets FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "brand_assets_delete" ON public.brand_assets FOR DELETE USING (public.is_admin(auth.uid()));

-- premade_content
DROP POLICY IF EXISTS "premade_content_select" ON public.premade_content;
DROP POLICY IF EXISTS "premade_content_insert" ON public.premade_content;
DROP POLICY IF EXISTS "premade_content_update" ON public.premade_content;
DROP POLICY IF EXISTS "premade_content_delete" ON public.premade_content;

CREATE POLICY "premade_content_select" ON public.premade_content FOR SELECT USING (is_active = true OR public.is_admin(auth.uid()));
CREATE POLICY "premade_content_insert" ON public.premade_content FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "premade_content_update" ON public.premade_content FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "premade_content_delete" ON public.premade_content FOR DELETE USING (public.is_admin(auth.uid()));

-- premade_content_translations
DROP POLICY IF EXISTS "premade_content_translations_select" ON public.premade_content_translations;
DROP POLICY IF EXISTS "premade_content_translations_insert" ON public.premade_content_translations;
DROP POLICY IF EXISTS "premade_content_translations_update" ON public.premade_content_translations;
DROP POLICY IF EXISTS "premade_content_translations_delete" ON public.premade_content_translations;

CREATE POLICY "premade_content_translations_select" ON public.premade_content_translations FOR SELECT USING (
    content_id IN (SELECT id FROM public.premade_content WHERE is_active = true) OR public.is_admin(auth.uid())
);
CREATE POLICY "premade_content_translations_insert" ON public.premade_content_translations FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "premade_content_translations_update" ON public.premade_content_translations FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "premade_content_translations_delete" ON public.premade_content_translations FOR DELETE USING (public.is_admin(auth.uid()));

-- cms_pages
DROP POLICY IF EXISTS "cms_pages_select" ON public.cms_pages;
DROP POLICY IF EXISTS "cms_pages_insert" ON public.cms_pages;
DROP POLICY IF EXISTS "cms_pages_update" ON public.cms_pages;
DROP POLICY IF EXISTS "cms_pages_delete" ON public.cms_pages;

CREATE POLICY "cms_pages_select" ON public.cms_pages FOR SELECT USING (is_active = true OR public.is_admin(auth.uid()));
CREATE POLICY "cms_pages_insert" ON public.cms_pages FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "cms_pages_update" ON public.cms_pages FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "cms_pages_delete" ON public.cms_pages FOR DELETE USING (public.is_admin(auth.uid()));

-- cms_sections
DROP POLICY IF EXISTS "cms_sections_select" ON public.cms_sections;
DROP POLICY IF EXISTS "cms_sections_insert" ON public.cms_sections;
DROP POLICY IF EXISTS "cms_sections_update" ON public.cms_sections;
DROP POLICY IF EXISTS "cms_sections_delete" ON public.cms_sections;

CREATE POLICY "cms_sections_select" ON public.cms_sections FOR SELECT USING (
    (is_visible = true AND page_id IN (SELECT id FROM public.cms_pages WHERE is_active = true)) OR public.is_admin(auth.uid())
);
CREATE POLICY "cms_sections_insert" ON public.cms_sections FOR INSERT WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "cms_sections_update" ON public.cms_sections FOR UPDATE USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));
CREATE POLICY "cms_sections_delete" ON public.cms_sections FOR DELETE USING (public.is_admin(auth.uid()));

-- Add more tables as needed...

-- Verify the function exists
SELECT proname, prosecdef FROM pg_proc WHERE proname = 'is_admin';
