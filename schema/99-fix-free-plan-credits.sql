-- Migration: Fix Free Plan Credits and Limits
-- Date: 2026-01-25
-- Description: 
--   1. Fix free plan to give 5 credits (not 10 or 50)
--   2. Fix scraping limits to allow 5 scrapings per month (not just 1)
--   3. Update plan_credit_configs for free plan to have proper limits

-- ============================================================================
-- Step 1: Update plan_credit_configs for free plan
-- ============================================================================

-- Update free plan configurations to allow more than 1 action per month/day
UPDATE public.plan_credit_configs pcc
SET 
    monthly_limit = CASE 
        WHEN ca.action_name = 'scraping' THEN 5  -- 5 scrapings per month
        WHEN ca.action_name = 'generate_scenario' THEN 2  -- 2 scenarios per month
        WHEN ca.action_name = 'generate_scene' THEN 0  -- Not available
        WHEN ca.action_name = 'generate_image' THEN 0  -- Not available
        WHEN ca.action_name = 'generate_audio' THEN 0  -- Not available
        WHEN ca.action_name = 'merge_video' THEN 5  -- 5 merges (0 credits each)
        WHEN ca.action_name = 'upscale_video' THEN 0  -- Not available
        ELSE 0
    END,
    daily_limit = CASE 
        WHEN ca.action_name = 'scraping' THEN 5  -- Up to 5 per day
        WHEN ca.action_name = 'generate_scenario' THEN 2  -- Up to 2 per day
        ELSE NULL
    END,
    updated_at = NOW()
FROM public.subscription_plans sp, public.credit_actions ca
WHERE pcc.plan_id = sp.id
    AND pcc.action_id = ca.id
    AND sp.name = 'free';

-- ============================================================================
-- Step 2: Update existing users' credits to match free plan (5 credits)
-- ============================================================================

-- Update user_credits for users on free plan who have incorrect credit amounts
-- We need to update subscription credits while preserving addon credits
UPDATE public.user_credits uc
SET 
    total_credits = 5,
    subscription_credits_remaining = LEAST(COALESCE(subscription_credits_remaining, 0), 5),  -- Cap subscription credits at 5
    credits_remaining = LEAST(COALESCE(subscription_credits_remaining, 0), 5) + COALESCE(addon_credits_remaining, 0),  -- Update total = subscription + addon
    updated_at = NOW()
FROM public.user_subscriptions us, public.subscription_plans sp
WHERE uc.user_id = us.user_id
    AND us.plan_id = sp.id
    AND sp.name = 'free'
    AND us.status = 'active'
    AND uc.total_credits != 5;

-- Update user_profiles for users on free plan who have incorrect credit amounts
UPDATE public.user_profiles up
SET 
    credits_total = 5,
    credits_remaining = LEAST(credits_remaining, 5),  -- Cap at 5, don't remove if they have less
    updated_at = NOW()
FROM public.user_subscriptions us, public.subscription_plans sp
WHERE up.user_id = us.user_id
    AND us.plan_id = sp.id
    AND sp.name = 'free'
    AND us.status = 'active'
    AND up.credits_total != 5;

-- ============================================================================
-- Step 3: Log the migration
-- ============================================================================

-- Add comment to track migration
COMMENT ON TABLE public.plan_credit_configs IS 'Plan-specific credit configurations. Updated 2026-01-25: Fixed free plan limits to allow 5 scrapings/month instead of 1.';
