-- Migration: Rollback user_credits display functions
-- Description: Removes the functions created in migration 25-fix-user-credits-display-function.sql
-- Date: 2025-12-07
-- This migration is idempotent - safe to run multiple times

-- ========================================
-- PART 1: Drop the functions if they exist
-- ========================================

DROP FUNCTION IF EXISTS get_user_credits_detailed(UUID);
DROP FUNCTION IF EXISTS get_user_credits_simple(UUID);

-- ========================================
-- Summary
-- ========================================
-- This migration removes the functions created in 25-fix-user-credits-display-function.sql:
-- - get_user_credits_detailed()
-- - get_user_credits_simple()
--
-- After running this, the functions will be removed and you can use the original
-- get_user_credits() function or query the table directly.

