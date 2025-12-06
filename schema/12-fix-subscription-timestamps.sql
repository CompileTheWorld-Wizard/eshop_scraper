-- Migration: Fix Monthly Subscription Timestamps
-- Description: Fixes incorrect current_period_end values for monthly subscriptions
-- This migration corrects subscriptions where billing_cycle is 'monthly' but 
-- current_period_end is set to 1 year instead of 1 month
-- Date: 2024

-- Fix monthly subscriptions where current_period_end is more than 32 days from current_period_start
-- (32 days allows for some margin, as months can be 28-31 days)
-- This migration is idempotent - safe to run multiple times

WITH fixed_subscriptions AS (
  UPDATE public.user_subscriptions
  SET 
    current_period_end = (
      -- Calculate exactly 1 month from current_period_start
      (current_period_start AT TIME ZONE 'UTC') + INTERVAL '1 month'
    ) AT TIME ZONE 'UTC',
    updated_at = NOW()
  WHERE 
    billing_cycle = 'monthly'
    AND current_period_start IS NOT NULL
    AND current_period_end IS NOT NULL
    -- Only fix if the period is longer than 32 days (indicating it was set to 1 year)
    AND EXTRACT(EPOCH FROM (current_period_end - current_period_start)) / 86400 > 32
    -- Only fix if current_period_end is in the future (don't modify past periods)
    AND current_period_end > NOW()
  RETURNING id
)
SELECT COUNT(*) as fixed_count FROM fixed_subscriptions;

