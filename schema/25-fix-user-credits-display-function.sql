-- Migration: Fix user_credits display function
-- Description: Creates/updates a function to return user_credits data with proper field structure
--              without the non-existent fields (start_date, last_reset_date, reset_frequency)
-- Date: 2025-12-07
-- This migration is idempotent - safe to run multiple times

-- ========================================
-- PART 1: Create/Update get_user_credits_detailed function
-- ========================================

CREATE OR REPLACE FUNCTION get_user_credits_detailed(user_uuid UUID)
RETURNS TABLE(
    id UUID,
    user_id UUID,
    total_credits INTEGER,
    credits_remaining INTEGER,
    cycle_used_credits INTEGER,
    cycle_start_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    -- Optional subscription cycle info (from user_subscriptions)
    subscription_current_period_start TIMESTAMPTZ,
    subscription_current_period_end TIMESTAMPTZ,
    subscription_billing_cycle TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        uc.id,
        uc.user_id,
        COALESCE(uc.total_credits, 0) as total_credits,
        COALESCE(uc.credits_remaining, 0) as credits_remaining,
        COALESCE(uc.cycle_used_credits, 0) as cycle_used_credits,
        uc.cycle_start_at,
        uc.created_at,
        uc.updated_at,
        -- Subscription cycle information (if subscription exists)
        us.current_period_start as subscription_current_period_start,
        us.current_period_end as subscription_current_period_end,
        us.billing_cycle as subscription_billing_cycle
    FROM public.user_credits uc
    LEFT JOIN public.user_subscriptions us ON uc.user_id = us.user_id AND us.status = 'active'
    WHERE uc.user_id = user_uuid;
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- PART 2: Create/Update get_user_credits_simple function (returns only credit fields)
-- ========================================

CREATE OR REPLACE FUNCTION get_user_credits_simple(user_uuid UUID)
RETURNS TABLE(
    id UUID,
    user_id UUID,
    total_credits INTEGER,
    credits_remaining INTEGER,
    cycle_used_credits INTEGER,
    cycle_start_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        uc.id,
        uc.user_id,
        COALESCE(uc.total_credits, 0) as total_credits,
        COALESCE(uc.credits_remaining, 0) as credits_remaining,
        COALESCE(uc.cycle_used_credits, 0) as cycle_used_credits,
        uc.cycle_start_at,
        uc.created_at,
        uc.updated_at
    FROM public.user_credits uc
    WHERE uc.user_id = user_uuid;
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- PART 3: Grant execute permissions
-- ========================================

GRANT EXECUTE ON FUNCTION get_user_credits_detailed(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION get_user_credits_simple(UUID) TO authenticated;

-- ========================================
-- Summary
-- ========================================
-- This migration creates functions to properly query user_credits data:
--
-- 1. get_user_credits_detailed() - Returns all user_credits fields + subscription cycle info
--    - Includes subscription period dates if subscription exists
--    - Proper field names matching the actual table structure
--
-- 2. get_user_credits_simple() - Returns only user_credits table fields
--    - Clean structure with only actual columns
--    - No extra fields that don't exist
--
-- Usage:
--   - Use get_user_credits_detailed() if you need subscription cycle info
--   - Use get_user_credits_simple() for just credit data
--   - Both functions return only fields that actually exist in the table
--
-- This fixes the display issue without modifying the table structure.
-- The functions ensure you only get valid fields, avoiding confusion from
-- non-existent columns like start_date, last_reset_date, reset_frequency.

