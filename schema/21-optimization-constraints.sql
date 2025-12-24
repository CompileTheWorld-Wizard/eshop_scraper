-- Migration: Database Optimization - Constraints
-- Description: Adds check constraints to prevent data corruption and ensure consistency
-- Priority: MEDIUM
-- Risk: LOW (constraints can be dropped if issues occur)
-- Date: 2024
-- This migration is idempotent - safe to run multiple times

-- ============================================================================
-- CHECK CONSTRAINTS FOR DATA INTEGRITY
-- ============================================================================

-- 1. user_subscriptions - Ensure period dates are valid
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'check_period_dates' 
        AND conrelid = 'public.user_subscriptions'::regclass
    ) THEN
        ALTER TABLE public.user_subscriptions 
        ADD CONSTRAINT check_period_dates 
        CHECK (
            current_period_end IS NULL 
            OR current_period_start IS NULL 
            OR current_period_end >= current_period_start
        );
    END IF;
END $$;

-- 2. user_credits - Ensure credit consistency
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'check_credits_consistency' 
        AND conrelid = 'public.user_credits'::regclass
    ) THEN
        ALTER TABLE public.user_credits 
        ADD CONSTRAINT check_credits_consistency 
        CHECK (
            credits_remaining >= 0 
            AND subscription_credits_remaining >= 0 
            AND addon_credits_remaining >= 0
            AND credits_remaining = subscription_credits_remaining + addon_credits_remaining
        );
    END IF;
END $$;

-- 3. addon_credits - Ensure credits are within valid range
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'check_addon_credits' 
        AND conrelid = 'public.addon_credits'::regclass
    ) THEN
        ALTER TABLE public.addon_credits 
        ADD CONSTRAINT check_addon_credits 
        CHECK (
            credits_remaining >= 0 
            AND credits_remaining <= credits_amount
        );
    END IF;
END $$;

-- 4. credit_transactions - Ensure transaction amount is positive
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'check_transaction_amount' 
        AND conrelid = 'public.credit_transactions'::regclass
    ) THEN
        ALTER TABLE public.credit_transactions 
        ADD CONSTRAINT check_transaction_amount 
        CHECK (credits_amount > 0);
    END IF;
END $$;

-- ============================================================================
-- COMMENTS FOR DOCUMENTATION
-- ============================================================================

COMMENT ON CONSTRAINT check_period_dates ON public.user_subscriptions IS 
'Ensures current_period_end is not before current_period_start';

COMMENT ON CONSTRAINT check_credits_consistency ON public.user_credits IS 
'Ensures credit values are non-negative and credits_remaining equals sum of subscription and addon credits';

COMMENT ON CONSTRAINT check_addon_credits ON public.addon_credits IS 
'Ensures remaining credits are non-negative and do not exceed original amount';

COMMENT ON CONSTRAINT check_transaction_amount ON public.credit_transactions IS 
'Ensures transaction amounts are always positive';

-- ============================================================================
-- VALIDATE EXISTING DATA
-- ============================================================================

-- Check for existing data that violates constraints (will fail if violations exist)
-- These checks are informational - constraints will prevent future violations

DO $$
DECLARE
    violation_count INTEGER;
BEGIN
    -- Check user_subscriptions
    SELECT COUNT(*) INTO violation_count
    FROM public.user_subscriptions
    WHERE current_period_end IS NOT NULL 
      AND current_period_start IS NOT NULL 
      AND current_period_end < current_period_start;
    
    IF violation_count > 0 THEN
        RAISE WARNING 'Found % rows in user_subscriptions with invalid period dates', violation_count;
    END IF;
    
    -- Check user_credits
    SELECT COUNT(*) INTO violation_count
    FROM public.user_credits
    WHERE credits_remaining < 0 
       OR subscription_credits_remaining < 0 
       OR addon_credits_remaining < 0
       OR credits_remaining != (subscription_credits_remaining + addon_credits_remaining);
    
    IF violation_count > 0 THEN
        RAISE WARNING 'Found % rows in user_credits with inconsistent credit values', violation_count;
    END IF;
    
    -- Check addon_credits
    SELECT COUNT(*) INTO violation_count
    FROM public.addon_credits
    WHERE credits_remaining < 0 OR credits_remaining > credits_amount;
    
    IF violation_count > 0 THEN
        RAISE WARNING 'Found % rows in addon_credits with invalid credit values', violation_count;
    END IF;
    
    -- Check credit_transactions
    SELECT COUNT(*) INTO violation_count
    FROM public.credit_transactions
    WHERE credits_amount <= 0;
    
    IF violation_count > 0 THEN
        RAISE WARNING 'Found % rows in credit_transactions with non-positive amounts', violation_count;
    END IF;
END $$;

