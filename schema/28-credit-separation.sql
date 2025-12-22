-- Migration: Separate Subscription and Add-on Credits
-- Purpose: Implement Requirements 1 & 2 - Credits reset every billing cycle, unused credits do NOT roll over
-- Date: 2024
-- This migration is idempotent - safe to run multiple times

-- ============================================================================
-- PART 1: Add columns to separate subscription vs add-on credits
-- ============================================================================

ALTER TABLE public.user_credits
ADD COLUMN IF NOT EXISTS subscription_credits_remaining INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS addon_credits_remaining INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_billing_cycle_reset TIMESTAMPTZ;

COMMENT ON COLUMN public.user_credits.subscription_credits_remaining IS 
'Credits from subscription plan that reset every billing cycle. These do NOT roll over.';

COMMENT ON COLUMN public.user_credits.addon_credits_remaining IS 
'Credits from add-on purchases that expire at the end of current billing cycle. These do NOT roll over.';

COMMENT ON COLUMN public.user_credits.last_billing_cycle_reset IS 
'Timestamp when credits were last reset on billing cycle renewal. Used for idempotency checks.';

-- ============================================================================
-- PART 2: Migrate existing data
-- ============================================================================

-- Migrate existing credits_remaining to subscription_credits_remaining
-- Assume all current credits are subscription credits (add-ons will be tracked separately)
UPDATE public.user_credits
SET 
    subscription_credits_remaining = credits_remaining,
    addon_credits_remaining = 0
WHERE subscription_credits_remaining = 0 AND addon_credits_remaining = 0
  AND credits_remaining > 0;

-- For users with no credits, ensure defaults are set
UPDATE public.user_credits
SET 
    subscription_credits_remaining = COALESCE(subscription_credits_remaining, 0),
    addon_credits_remaining = COALESCE(addon_credits_remaining, 0)
WHERE subscription_credits_remaining IS NULL OR addon_credits_remaining IS NULL;

-- ============================================================================
-- PART 3: Create index for efficient queries
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_user_credits_last_billing_cycle_reset 
ON public.user_credits(last_billing_cycle_reset) 
WHERE last_billing_cycle_reset IS NOT NULL;

