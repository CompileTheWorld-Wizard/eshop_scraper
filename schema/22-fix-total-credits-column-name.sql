-- Migration: Fix total_credits Column Name
-- Description: Ensures user_credits table uses total_credits (not credits_total) to match application code
-- Priority: HIGH
-- Risk: LOW (only fixes schema definition, doesn't change existing data)
-- Date: 2024
-- This migration is idempotent - safe to run multiple times

-- ============================================================================
-- NOTE: This migration ensures schema matches the actual database structure
-- The database already has total_credits column, this just documents it
-- ============================================================================

-- Check if column exists as credits_total and rename it to total_credits
DO $$
BEGIN
    -- Check if credits_total column exists (old name)
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'user_credits' 
        AND column_name = 'credits_total'
    ) THEN
        -- Rename to total_credits to match application code
        ALTER TABLE public.user_credits 
        RENAME COLUMN credits_total TO total_credits;
        
        RAISE NOTICE 'Renamed credits_total to total_credits in user_credits table';
    ELSE
        -- Column already named total_credits or doesn't exist
        IF EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'user_credits' 
            AND column_name = 'total_credits'
        ) THEN
            RAISE NOTICE 'Column total_credits already exists in user_credits table';
        ELSE
            RAISE WARNING 'user_credits table or total_credits column does not exist';
        END IF;
    END IF;
END $$;

-- Add comment to document the column
COMMENT ON COLUMN public.user_credits.total_credits IS 
'Lifetime total of credits ever allocated to the user. Includes initial signup credits, subscription plan credits, add-on purchases, admin adjustments, and referral bonuses. This value only increases and never decreases.';

-- Verify the column exists and has correct type
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'user_credits' 
        AND column_name = 'total_credits'
        AND data_type = 'integer'
    ) THEN
        RAISE NOTICE '✓ Verified: total_credits column exists with correct type (integer)';
    ELSE
        RAISE WARNING '✗ Warning: total_credits column may not exist or has incorrect type';
    END IF;
END $$;

