-- Migration: Remove used_credits column from user_credits table
-- Description: Removes the deprecated used_credits column since it's redundant
--              and can be calculated as total_credits - credits_remaining
-- Date: 2025-12-07
-- This migration is idempotent - safe to run multiple times

-- ========================================
-- PART 1: Drop used_credits column if it exists
-- ========================================

DO $$
BEGIN
    -- Check if used_credits column exists and drop it
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'user_credits' 
        AND column_name = 'used_credits'
    ) THEN
        -- Drop the column
        ALTER TABLE public.user_credits
        DROP COLUMN used_credits;
        
        RAISE NOTICE 'Dropped used_credits column from user_credits table';
    ELSE
        RAISE NOTICE 'used_credits column does not exist in user_credits table - nothing to drop';
    END IF;
END $$;

-- ========================================
-- Summary
-- ========================================
-- This migration removes the deprecated used_credits column from user_credits table.
--
-- Why it's safe to remove:
-- 1. used_credits is redundant - can be calculated as total_credits - credits_remaining
-- 2. No business logic uses the stored column value
-- 3. All functions use credits_remaining directly
-- 4. Views calculate used_credits dynamically (total_credits - credits_remaining)
-- 5. The column was deprecated in migration 20-fix-credits-remaining-migration.sql
--
-- Impact:
-- - No code changes needed (nothing references the stored column)
-- - Views will continue to work (they calculate it dynamically)
-- - Functions will continue to work (they use credits_remaining)
-- - Cleaner schema without redundant data
--
-- This migration is idempotent - safe to run multiple times.

