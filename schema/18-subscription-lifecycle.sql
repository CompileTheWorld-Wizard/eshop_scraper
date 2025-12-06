-- Migration: Subscription Lifecycle Features
-- Purpose: Implement subscription lifecycle management features
-- This migration includes:
--   1. Add per-billing-cycle credit tracking fields
--   2. Add downgrade scheduling fields
--   3. Add payment failure grace period fields
--   4. Add trial user tracking fields
-- Date: 2024
-- This migration is idempotent - safe to run multiple times

-- ============================================================================
-- PART 1: Add per-billing-cycle credit tracking fields
-- Purpose: Support Requirement 1 - credits reset every billing cycle (no rollover)
-- ============================================================================

ALTER TABLE public.user_credits
ADD COLUMN IF NOT EXISTS cycle_used_credits INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS cycle_start_at TIMESTAMPTZ;

COMMENT ON COLUMN public.user_credits.cycle_used_credits IS
'Total subscription-plan credits consumed in the current billing cycle. Used to enforce monthly_credits per cycle without rollover.';

COMMENT ON COLUMN public.user_credits.cycle_start_at IS
'Billing cycle start timestamp this cycle_used_credits value belongs to (mirrors user_subscriptions.current_period_start).';

-- ============================================================================
-- PART 2: Add downgrade scheduling fields
-- Purpose: Implement Requirement 4 - Downgrade applies on next billing cycle
-- ============================================================================

-- Add downgrade scheduling columns to user_subscriptions
ALTER TABLE public.user_subscriptions
ADD COLUMN IF NOT EXISTS downgrade_to_plan_id UUID REFERENCES public.subscription_plans(id) ON DELETE SET NULL,
ADD COLUMN IF NOT EXISTS downgrade_scheduled_at TIMESTAMP WITH TIME ZONE;

-- Add index for efficient queries on scheduled downgrades
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_downgrade_scheduled 
ON public.user_subscriptions(downgrade_to_plan_id) 
WHERE downgrade_to_plan_id IS NOT NULL;

-- Add comment to document the downgrade scheduling feature
COMMENT ON COLUMN public.user_subscriptions.downgrade_to_plan_id IS 'Plan ID for scheduled downgrade - will be applied at current_period_end';
COMMENT ON COLUMN public.user_subscriptions.downgrade_scheduled_at IS 'Timestamp when the downgrade was scheduled - typically equals current_period_end';

-- ============================================================================
-- PART 3: Add payment failure grace period fields
-- Purpose: Implement Requirement 7 - Payment failure: 3-day grace period, then block rendering
-- ============================================================================

ALTER TABLE public.user_subscriptions
ADD COLUMN IF NOT EXISTS payment_failed_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS grace_period_ends_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS rendering_blocked BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN public.user_subscriptions.payment_failed_at IS 'Timestamp when payment first failed. Used to track grace period start.';
COMMENT ON COLUMN public.user_subscriptions.grace_period_ends_at IS 'Timestamp when grace period ends (payment_failed_at + 3 days). After this, rendering is blocked.';
COMMENT ON COLUMN public.user_subscriptions.rendering_blocked IS 'If true, user cannot perform rendering actions. Set to true after grace period expires.';

-- Index for efficient grace period expiration checks
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_grace_period ON public.user_subscriptions(grace_period_ends_at) 
WHERE grace_period_ends_at IS NOT NULL AND status = 'past_due';

-- ============================================================================
-- PART 4: Add trial user tracking fields
-- Purpose: Implement Requirement 9 - Trial users: one free preview only
-- ============================================================================

ALTER TABLE public.user_profiles
ADD COLUMN IF NOT EXISTS is_trial_user BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN IF NOT EXISTS trial_preview_used BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN IF NOT EXISTS trial_preview_used_at TIMESTAMPTZ;

COMMENT ON COLUMN public.user_profiles.is_trial_user IS 'If true, user is a trial user who can only use one free preview render. No download, no publishing, no full-render credits.';
COMMENT ON COLUMN public.user_profiles.trial_preview_used IS 'If true, trial user has already used their one free preview.';
COMMENT ON COLUMN public.user_profiles.trial_preview_used_at IS 'Timestamp when trial user used their free preview render.';

-- Index for efficient trial user queries
CREATE INDEX IF NOT EXISTS idx_user_profiles_is_trial_user ON public.user_profiles(is_trial_user) 
WHERE is_trial_user = true;

-- Add preview_render action if it doesn't exist (0 credits for trial users)
INSERT INTO public.credit_actions (action_name, display_name, description, base_credit_cost, is_active)
VALUES ('preview_render', 'Preview Render', 'Free preview render for trial users (one-time use)', 0, true)
ON CONFLICT (action_name) DO NOTHING;

