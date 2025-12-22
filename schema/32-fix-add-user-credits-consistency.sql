-- Migration: Fix add_user_credits to maintain subscription/addon credit consistency
-- Purpose: Fix data inconsistency where admin bonus credits only update credits_remaining
--          but not subscription_credits_remaining or addon_credits_remaining
-- Date: 2024
-- This migration is idempotent - safe to run multiple times

-- ============================================================================
-- PART 1: Fix add_user_credits function to update subscription/addon credits
-- ============================================================================

-- Drop ALL old function signatures to avoid conflicts
-- NOTE: Previous migrations (schema/21, schema/22) may have created an old function signature
--       with parameters (UUID, TEXT, INTEGER, UUID, TEXT, TEXT). This migration removes
--       all old versions and ensures only the correct signature exists.
-- Old signature 1: (UUID, TEXT, INTEGER, UUID, TEXT, TEXT) - from schema/06-functions.sql, schema/21, schema/22
DROP FUNCTION IF EXISTS add_user_credits(UUID, TEXT, INTEGER, UUID, TEXT, TEXT);
-- Old signature 2: (UUID, INTEGER, TEXT, UUID, TEXT, JSONB) - intermediate version
DROP FUNCTION IF EXISTS add_user_credits(UUID, INTEGER, TEXT, UUID, TEXT, JSONB);
-- Current signature: (UUID, INTEGER, TEXT, TEXT, TEXT, JSONB) - from schema/20
DROP FUNCTION IF EXISTS add_user_credits(UUID, INTEGER, TEXT, TEXT, TEXT, JSONB);

CREATE OR REPLACE FUNCTION add_user_credits(
    user_uuid UUID,
    amount INTEGER,
    description TEXT DEFAULT NULL,
    reference_id TEXT DEFAULT NULL,
    reference_type TEXT DEFAULT NULL,
    metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE(
    credits_total INTEGER,
    credits_remaining INTEGER
)
-- Note: Returns total_credits as credits_total and credits_remaining (stored directly) for compatibility
SECURITY DEFINER -- This allows the function to bypass RLS
SET search_path = public
AS $$
DECLARE
    new_total INTEGER;
    new_remaining INTEGER;
    reference_uuid UUID;
    credit_type TEXT; -- 'subscription' or 'addon' - determines where credits go
BEGIN
    -- Convert reference_id from TEXT to UUID if it's a valid UUID string
    IF reference_id IS NOT NULL THEN
        BEGIN
            reference_uuid := reference_id::UUID;
        EXCEPTION WHEN OTHERS THEN
            reference_uuid := NULL; -- If not a valid UUID, leave as NULL
        END;
    END IF;
    
    -- Determine credit type based on reference_type
    -- Admin bonuses and general additions go to subscription_credits_remaining
    -- Explicit addon purchases go to addon_credits_remaining
    IF reference_type = 'addon' OR reference_type = 'addon_purchase' THEN
        credit_type := 'addon';
    ELSE
        -- Default: admin bonuses, subscription credits, etc. go to subscription_credits_remaining
        credit_type := 'subscription';
    END IF;
    
    -- Add credits to user_credits table
    -- Update both subscription/addon credits AND total credits_remaining for consistency
    IF credit_type = 'addon' THEN
        -- Add to addon credits
        UPDATE public.user_credits
        SET 
            total_credits = total_credits + amount,
            addon_credits_remaining = COALESCE(addon_credits_remaining, 0) + amount,
            -- Recalculate credits_remaining from updated subscription + addon values
            credits_remaining = COALESCE(subscription_credits_remaining, 0) + (COALESCE(addon_credits_remaining, 0) + amount),
            updated_at = NOW()
        WHERE user_id = user_uuid
        RETURNING total_credits, credits_remaining INTO new_total, new_remaining;
    ELSE
        -- Add to subscription credits (default for admin bonuses, etc.)
        UPDATE public.user_credits
        SET 
            total_credits = total_credits + amount,
            subscription_credits_remaining = COALESCE(subscription_credits_remaining, 0) + amount,
            -- Recalculate credits_remaining from updated subscription + addon values
            credits_remaining = (COALESCE(subscription_credits_remaining, 0) + amount) + COALESCE(addon_credits_remaining, 0),
            updated_at = NOW()
        WHERE user_id = user_uuid
        RETURNING total_credits, credits_remaining INTO new_total, new_remaining;
    END IF;
    
    -- If no row was updated, create one
    IF NOT FOUND THEN
        IF credit_type = 'addon' THEN
            INSERT INTO public.user_credits (
                user_id, 
                total_credits, 
                credits_remaining,
                subscription_credits_remaining,
                addon_credits_remaining
            )
            VALUES (
                user_uuid, 
                amount, 
                amount,
                0,
                amount
            )
            RETURNING total_credits, credits_remaining INTO new_total, new_remaining;
        ELSE
            INSERT INTO public.user_credits (
                user_id, 
                total_credits, 
                credits_remaining,
                subscription_credits_remaining,
                addon_credits_remaining
            )
            VALUES (
                user_uuid, 
                amount, 
                amount,
                amount,
                0
            )
            RETURNING total_credits, credits_remaining INTO new_total, new_remaining;
        END IF;
    END IF;
    
    -- Record transaction (skip for admin adjustments to avoid action_id requirement)
    -- Only insert if reference_type is provided and it's not 'admin'
    IF reference_type IS NOT NULL AND reference_type != 'admin' THEN
        INSERT INTO public.credit_transactions (
            user_id, 
            action_id, 
            type,
            transaction_type, 
            credits_amount, 
            reference_id, 
            reference_type, 
            description,
            metadata
        ) 
        SELECT 
            user_uuid,
            (SELECT id FROM public.credit_actions WHERE action_name = reference_type LIMIT 1),
            reference_type,
            'addition',
            amount,
            reference_uuid, -- Use converted UUID
            reference_type,
            description,
            metadata
        WHERE EXISTS (SELECT 1 FROM public.credit_actions WHERE action_name = reference_type);
    END IF;
    
    -- Return total_credits and credits_remaining (stored directly)
    RETURN QUERY SELECT new_total, new_remaining;
END;
$$ LANGUAGE plpgsql;

-- Grant execute permission to authenticated users
GRANT EXECUTE ON FUNCTION add_user_credits(UUID, INTEGER, TEXT, TEXT, TEXT, JSONB) TO authenticated;

-- Add comment
COMMENT ON FUNCTION add_user_credits(UUID, INTEGER, TEXT, TEXT, TEXT, JSONB) IS 
'Adds credits to user account. Admin bonuses go to subscription_credits_remaining. 
Maintains consistency: credits_remaining = subscription_credits_remaining + addon_credits_remaining.

Function signature: add_user_credits(user_uuid UUID, amount INTEGER, description TEXT, reference_id TEXT, reference_type TEXT, metadata JSONB)
- Returns: TABLE(credits_total INTEGER, credits_remaining INTEGER)
- If reference_type = ''addon'' or ''addon_purchase'': credits go to addon_credits_remaining
- Otherwise: credits go to subscription_credits_remaining (default for admin bonuses)

NOTE: Old signature (UUID, TEXT, INTEGER, UUID, TEXT, TEXT) has been removed. Use this signature only.';

-- ============================================================================
-- PART 2: Fix existing data inconsistencies
-- ============================================================================

-- Fix any existing rows where credits_remaining doesn't match subscription + addon
-- This corrects data that was created before this fix
UPDATE public.user_credits
SET 
    credits_remaining = COALESCE(subscription_credits_remaining, 0) + COALESCE(addon_credits_remaining, 0),
    updated_at = NOW()
WHERE credits_remaining != (COALESCE(subscription_credits_remaining, 0) + COALESCE(addon_credits_remaining, 0));

-- ============================================================================
-- PART 3: Add constraint to prevent future inconsistencies (optional)
-- ============================================================================

-- Note: We could add a CHECK constraint, but it might be too strict if we want flexibility
-- For now, we'll rely on the function to maintain consistency
-- Uncomment below if you want to enforce it at the database level:

-- ALTER TABLE public.user_credits
-- ADD CONSTRAINT check_credits_remaining_consistency 
-- CHECK (
--     credits_remaining = COALESCE(subscription_credits_remaining, 0) + COALESCE(addon_credits_remaining, 0)
-- );

