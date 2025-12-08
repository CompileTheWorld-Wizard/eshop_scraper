-- Migration: Fix sync_user_credits_to_profile function
-- Description: Updates sync_user_credits_to_profile to use credits_remaining instead of used_credits
--              This fixes the error: column "used_credits" does not exist
-- Date: 2025-12-07
-- This migration is idempotent - safe to run multiple times

-- ========================================
-- PART 1: Update sync_user_credits_to_profile function
-- ========================================

CREATE OR REPLACE FUNCTION sync_user_credits_to_profile(user_uuid UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE public.user_profiles
    SET 
        credits_total = COALESCE(uc.total_credits, 0),
        credits_remaining = COALESCE(uc.credits_remaining, 0),
        updated_at = NOW()
    FROM public.user_credits uc
    WHERE public.user_profiles.user_id = user_uuid
    AND uc.user_id = user_uuid;
    
    -- If no user_credits record exists, set to 0
    IF NOT FOUND THEN
        UPDATE public.user_profiles
        SET 
            credits_total = 0,
            credits_remaining = 0,
            updated_at = NOW()
        WHERE user_id = user_uuid;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- Summary
-- ========================================
-- This migration fixes the sync_user_credits_to_profile function to:
-- 1. Use credits_remaining directly (stored value) instead of calculating from used_credits
-- 2. Remove the reference to the non-existent used_credits column
-- 3. Match the current schema where credits_remaining is stored directly
--
-- The old version was:
--   - SELECT used_credits FROM user_credits (column doesn't exist anymore)
--   - Calculate: remaining = total - used
--
-- The new version:
--   - SELECT credits_remaining FROM user_credits (directly stored value)
--   - Use credits_remaining directly (no calculation needed)
--
-- This fixes the error: "column 'used_credits' does not exist"
-- that occurs when deduct_user_credits updates user_credits table,
-- which triggers sync_user_credits_trigger, which calls this function.

