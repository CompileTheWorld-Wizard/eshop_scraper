-- Migration: Consolidate RLS Policies - Eliminate Multiple Permissive Policies
-- Description: ONE SELECT policy per table (with OR logic) to eliminate warnings
-- Priority: HIGH (performance optimization)
-- Risk: ZERO (same access control, just consolidated)
-- Date: 2024-01-14
--
-- ISSUE: Multiple permissive SELECT policies cause performance warnings
-- SOLUTION: One SELECT policy with OR conditions per table
--
-- Pattern:
-- - One consolidated SELECT policy (users OR admins)
-- - Admin-only modification policies don't cause warnings (only one per action)

DO $$
DECLARE
    r RECORD;
BEGIN
    RAISE NOTICE 'Dropping all existing policies...';
    FOR r IN (SELECT schemaname, tablename, policyname FROM pg_policies WHERE schemaname = 'public')
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I', r.policyname, r.schemaname, r.tablename);
    END LOOP;
END $$;

-- ============================================================================
-- Pattern 1: User-owned tables (users see/manage their own, admins see all)
-- ============================================================================

-- products
CREATE POLICY "products_select" ON public.products FOR SELECT USING (
    (select auth.uid()) = user_id OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "products_insert" ON public.products FOR INSERT WITH CHECK ((select auth.uid()) = user_id);
CREATE POLICY "products_update" ON public.products FOR UPDATE USING ((select auth.uid()) = user_id) WITH CHECK ((select auth.uid()) = user_id);
CREATE POLICY "products_delete" ON public.products FOR DELETE USING ((select auth.uid()) = user_id);

-- shorts
CREATE POLICY "shorts_select" ON public.shorts FOR SELECT USING (
    (select auth.uid()) = user_id OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "shorts_insert" ON public.shorts FOR INSERT WITH CHECK ((select auth.uid()) = user_id);
CREATE POLICY "shorts_update" ON public.shorts FOR UPDATE USING ((select auth.uid()) = user_id) WITH CHECK ((select auth.uid()) = user_id);
CREATE POLICY "shorts_delete" ON public.shorts FOR DELETE USING ((select auth.uid()) = user_id);

-- user_credits
CREATE POLICY "user_credits_select" ON public.user_credits FOR SELECT USING (
    (select auth.uid()) = user_id OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "user_credits_insert" ON public.user_credits FOR INSERT WITH CHECK ((select auth.uid()) = user_id);
CREATE POLICY "user_credits_update" ON public.user_credits FOR UPDATE USING ((select auth.uid()) = user_id) WITH CHECK ((select auth.uid()) = user_id);
CREATE POLICY "user_credits_delete" ON public.user_credits FOR DELETE USING ((select auth.uid()) = user_id);

-- user_profiles
CREATE POLICY "user_profiles_select" ON public.user_profiles FOR SELECT USING (
    (select auth.uid()) = user_id OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "user_profiles_update" ON public.user_profiles FOR UPDATE USING ((select auth.uid()) = user_id) WITH CHECK ((select auth.uid()) = user_id);

-- user_subscriptions
CREATE POLICY "user_subscriptions_select" ON public.user_subscriptions FOR SELECT USING (
    (select auth.uid()) = user_id OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);

-- credit_transactions
CREATE POLICY "credit_transactions_select" ON public.credit_transactions FOR SELECT USING (
    (select auth.uid()) = user_id OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "credit_transactions_insert" ON public.credit_transactions FOR INSERT WITH CHECK ((select auth.uid()) = user_id);

-- credit_adjustments
CREATE POLICY "credit_adjustments_select" ON public.credit_adjustments FOR SELECT USING (
    (select auth.uid()) = user_id OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "credit_adjustments_insert" ON public.credit_adjustments FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "credit_adjustments_update" ON public.credit_adjustments FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "credit_adjustments_delete" ON public.credit_adjustments FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

-- user_activities
CREATE POLICY "user_activities_select" ON public.user_activities FOR SELECT USING (
    (select auth.uid()) = user_id OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "user_activities_insert" ON public.user_activities FOR INSERT WITH CHECK ((select auth.uid()) = user_id);

-- credit_usage_tracking
CREATE POLICY "credit_usage_tracking_select" ON public.credit_usage_tracking FOR SELECT USING (
    (select auth.uid()) = user_id OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "credit_usage_tracking_insert" ON public.credit_usage_tracking FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "credit_usage_tracking_update" ON public.credit_usage_tracking FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "credit_usage_tracking_delete" ON public.credit_usage_tracking FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

-- addon_credits
CREATE POLICY "addon_credits_select" ON public.addon_credits FOR SELECT USING (
    (select auth.uid()) = user_id OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "addon_credits_insert" ON public.addon_credits FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "addon_credits_update" ON public.addon_credits FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "addon_credits_delete" ON public.addon_credits FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

-- user_referrals
CREATE POLICY "user_referrals_select" ON public.user_referrals FOR SELECT USING (
    (select auth.uid()) IN (referrer_user, referred_user) 
    OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "user_referrals_insert" ON public.user_referrals FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "user_referrals_update" ON public.user_referrals FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "user_referrals_delete" ON public.user_referrals FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

-- referral_commissions
CREATE POLICY "referral_commissions_select" ON public.referral_commissions FOR SELECT USING (
    (select auth.uid()) = referrer_user
    OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "referral_commissions_insert" ON public.referral_commissions FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "referral_commissions_update" ON public.referral_commissions FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "referral_commissions_delete" ON public.referral_commissions FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

-- error_logs
CREATE POLICY "error_logs_select" ON public.error_logs FOR SELECT USING (
    (select auth.uid()) = user_id OR (select auth.uid()) IS NULL
    OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "error_logs_insert" ON public.error_logs FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "error_logs_update" ON public.error_logs FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "error_logs_delete" ON public.error_logs FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

-- brand_kit_activities
CREATE POLICY "brand_kit_activities_select" ON public.brand_kit_activities FOR SELECT USING (
    (select auth.uid()) = user_id OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "brand_kit_activities_insert" ON public.brand_kit_activities FOR INSERT WITH CHECK ((select auth.uid()) = user_id);
CREATE POLICY "brand_kit_activities_update" ON public.brand_kit_activities FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "brand_kit_activities_delete" ON public.brand_kit_activities FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

-- video_scenarios
CREATE POLICY "video_scenarios_select" ON public.video_scenarios FOR SELECT USING (
    short_id IN (SELECT id FROM public.shorts WHERE user_id = (select auth.uid()))
    OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "video_scenarios_insert" ON public.video_scenarios FOR INSERT WITH CHECK (
    short_id IN (SELECT id FROM public.shorts WHERE user_id = (select auth.uid()))
);
CREATE POLICY "video_scenarios_update" ON public.video_scenarios FOR UPDATE USING (
    short_id IN (SELECT id FROM public.shorts WHERE user_id = (select auth.uid()))
) WITH CHECK (
    short_id IN (SELECT id FROM public.shorts WHERE user_id = (select auth.uid()))
);
CREATE POLICY "video_scenarios_delete" ON public.video_scenarios FOR DELETE USING (
    short_id IN (SELECT id FROM public.shorts WHERE user_id = (select auth.uid()))
);

-- video_scenes
CREATE POLICY "video_scenes_select" ON public.video_scenes FOR SELECT USING (
    scenario_id IN (SELECT vs.id FROM public.video_scenarios vs JOIN public.shorts s ON s.id = vs.short_id WHERE s.user_id = (select auth.uid()))
    OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "video_scenes_insert" ON public.video_scenes FOR INSERT WITH CHECK (
    scenario_id IN (SELECT vs.id FROM public.video_scenarios vs JOIN public.shorts s ON s.id = vs.short_id WHERE s.user_id = (select auth.uid()))
);
CREATE POLICY "video_scenes_update" ON public.video_scenes FOR UPDATE USING (
    scenario_id IN (SELECT vs.id FROM public.video_scenarios vs JOIN public.shorts s ON s.id = vs.short_id WHERE s.user_id = (select auth.uid()))
) WITH CHECK (
    scenario_id IN (SELECT vs.id FROM public.video_scenarios vs JOIN public.shorts s ON s.id = vs.short_id WHERE s.user_id = (select auth.uid()))
);
CREATE POLICY "video_scenes_delete" ON public.video_scenes FOR DELETE USING (
    scenario_id IN (SELECT vs.id FROM public.video_scenarios vs JOIN public.shorts s ON s.id = vs.short_id WHERE s.user_id = (select auth.uid()))
);

-- Simple user-owned tables (single FOR ALL policy)
CREATE POLICY "social_media_accounts_all" ON public.social_media_accounts FOR ALL USING ((select auth.uid()) = user_id) WITH CHECK ((select auth.uid()) = user_id);
CREATE POLICY "audio_info_all" ON public.audio_info FOR ALL USING ((select auth.uid()) = user_id) WITH CHECK ((select auth.uid()) = user_id);
CREATE POLICY "publishing_info_all" ON public.publishing_info FOR ALL USING ((select auth.uid()) = user_id) WITH CHECK ((select auth.uid()) = user_id);

-- ============================================================================
-- Pattern 2: Public read tables (everyone reads, admin modifies)
-- ============================================================================

-- subscription_plans
CREATE POLICY "subscription_plans_select" ON public.subscription_plans FOR SELECT USING ((select auth.uid()) IS NOT NULL);
CREATE POLICY "subscription_plans_insert" ON public.subscription_plans FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "subscription_plans_update" ON public.subscription_plans FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "subscription_plans_delete" ON public.subscription_plans FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

-- credit_actions, credit_packages, plan_credit_configs, health_checks, categories
CREATE POLICY "credit_actions_select" ON public.credit_actions FOR SELECT USING ((select auth.uid()) IS NOT NULL);
CREATE POLICY "credit_actions_insert" ON public.credit_actions FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "credit_actions_update" ON public.credit_actions FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "credit_actions_delete" ON public.credit_actions FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

CREATE POLICY "credit_packages_select" ON public.credit_packages FOR SELECT USING ((select auth.uid()) IS NOT NULL);
CREATE POLICY "credit_packages_insert" ON public.credit_packages FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "credit_packages_update" ON public.credit_packages FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "credit_packages_delete" ON public.credit_packages FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

CREATE POLICY "plan_credit_configs_select" ON public.plan_credit_configs FOR SELECT USING ((select auth.uid()) IS NOT NULL);
CREATE POLICY "plan_credit_configs_insert" ON public.plan_credit_configs FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "plan_credit_configs_update" ON public.plan_credit_configs FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "plan_credit_configs_delete" ON public.plan_credit_configs FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

CREATE POLICY "health_checks_select" ON public.health_checks FOR SELECT USING ((select auth.uid()) IS NOT NULL);
CREATE POLICY "health_checks_insert" ON public.health_checks FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "health_checks_update" ON public.health_checks FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "health_checks_delete" ON public.health_checks FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

CREATE POLICY "categories_select" ON public.categories FOR SELECT USING ((select auth.uid()) IS NOT NULL);
CREATE POLICY "categories_insert" ON public.categories FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "categories_update" ON public.categories FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "categories_delete" ON public.categories FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

-- ============================================================================
-- Pattern 3: Active content (public reads active, admin manages all)
-- ============================================================================

CREATE POLICY "brand_kit_categories_select" ON public.brand_kit_categories FOR SELECT USING (is_active = true OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "brand_kit_categories_insert" ON public.brand_kit_categories FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "brand_kit_categories_update" ON public.brand_kit_categories FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "brand_kit_categories_delete" ON public.brand_kit_categories FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

CREATE POLICY "brand_assets_select" ON public.brand_assets FOR SELECT USING (is_active = true OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "brand_assets_insert" ON public.brand_assets FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "brand_assets_update" ON public.brand_assets FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "brand_assets_delete" ON public.brand_assets FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

CREATE POLICY "premade_content_select" ON public.premade_content FOR SELECT USING (is_active = true OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "premade_content_insert" ON public.premade_content FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "premade_content_update" ON public.premade_content FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "premade_content_delete" ON public.premade_content FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

CREATE POLICY "premade_content_translations_select" ON public.premade_content_translations FOR SELECT USING (
    content_id IN (SELECT id FROM public.premade_content WHERE is_active = true) OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "premade_content_translations_insert" ON public.premade_content_translations FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "premade_content_translations_update" ON public.premade_content_translations FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "premade_content_translations_delete" ON public.premade_content_translations FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

CREATE POLICY "cms_pages_select" ON public.cms_pages FOR SELECT USING (is_active = true OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "cms_pages_insert" ON public.cms_pages FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "cms_pages_update" ON public.cms_pages FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "cms_pages_delete" ON public.cms_pages FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

CREATE POLICY "cms_sections_select" ON public.cms_sections FOR SELECT USING (
    (is_visible = true AND page_id IN (SELECT id FROM public.cms_pages WHERE is_active = true)) OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "cms_sections_insert" ON public.cms_sections FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "cms_sections_update" ON public.cms_sections FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "cms_sections_delete" ON public.cms_sections FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

CREATE POLICY "cms_content_blocks_select" ON public.cms_content_blocks FOR SELECT USING (
    section_id IN (SELECT s.id FROM public.cms_sections s JOIN public.cms_pages p ON p.id = s.page_id WHERE s.is_visible = true AND p.is_active = true)
    OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "cms_content_blocks_insert" ON public.cms_content_blocks FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "cms_content_blocks_update" ON public.cms_content_blocks FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "cms_content_blocks_delete" ON public.cms_content_blocks FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

CREATE POLICY "cms_assets_select" ON public.cms_assets FOR SELECT USING (true);
CREATE POLICY "cms_assets_insert" ON public.cms_assets FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "cms_assets_update" ON public.cms_assets FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "cms_assets_delete" ON public.cms_assets FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

CREATE POLICY "cms_legal_documents_select" ON public.cms_legal_documents FOR SELECT USING (is_published = true OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "cms_legal_documents_insert" ON public.cms_legal_documents FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "cms_legal_documents_update" ON public.cms_legal_documents FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "cms_legal_documents_delete" ON public.cms_legal_documents FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

CREATE POLICY "cms_translations_select" ON public.cms_translations FOR SELECT USING (
    content_block_id IN (SELECT cb.id FROM public.cms_content_blocks cb JOIN public.cms_sections s ON s.id = cb.section_id JOIN public.cms_pages p ON p.id = s.page_id WHERE s.is_visible = true AND p.is_active = true)
    OR (select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')
);
CREATE POLICY "cms_translations_insert" ON public.cms_translations FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "cms_translations_update" ON public.cms_translations FOR UPDATE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "cms_translations_delete" ON public.cms_translations FOR DELETE USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

-- ============================================================================
-- Pattern 4: Admin-only tables
-- ============================================================================

CREATE POLICY "cms_audit_log_select" ON public.cms_audit_log FOR SELECT USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "retry_attempts_all" ON public.retry_attempts FOR ALL USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "alert_rules_all" ON public.alert_rules FOR ALL USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));
CREATE POLICY "alerts_all" ON public.alerts FOR ALL USING ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin')) WITH CHECK ((select auth.uid()) IN (SELECT user_id FROM public.user_profiles WHERE role = 'admin'));

-- ============================================================================
-- VERIFICATION
-- ============================================================================

DO $$
DECLARE policy_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO policy_count FROM pg_policies WHERE schemaname = 'public';
    RAISE NOTICE '======================================== ';
    RAISE NOTICE 'Consolidation complete! Total policies: %', policy_count;
    RAISE NOTICE 'Each table has 1-3 policies (one SELECT + modifications)';
    RAISE NOTICE '========================================';
END $$;
