-- Migration: Fix add_user_credits function RLS issue
-- Description: Makes add_user_credits function SECURITY DEFINER to bypass RLS policies
-- This allows admins to add credits to any user without RLS blocking the operation
-- Date: 2024

-- Drop all existing overloads to avoid conflicts
DROP FUNCTION IF EXISTS add_user_credits(UUID, TEXT, INTEGER, UUID, TEXT, TEXT);
DROP FUNCTION IF EXISTS add_user_credits(UUID, INTEGER, TEXT, UUID, TEXT, JSONB);
DROP FUNCTION IF EXISTS add_user_credits(UUID, INTEGER, TEXT, TEXT, TEXT, JSONB);
DROP FUNCTION IF EXISTS add_user_credits(UUID, TEXT, INTEGER, TEXT, TEXT, TEXT);

-- Create a single unified function that matches the code's call signature
-- This function accepts amount directly and handles reference_id as TEXT (can be UUID string or other string)
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
    current_used INTEGER;
    reference_uuid UUID;
BEGIN
    -- Convert reference_id from TEXT to UUID if it's a valid UUID string
    IF reference_id IS NOT NULL THEN
        BEGIN
            reference_uuid := reference_id::UUID;
        EXCEPTION WHEN OTHERS THEN
            reference_uuid := NULL; -- If not a valid UUID, leave as NULL
        END;
    END IF;
    
    -- Add credits to user_credits table
    -- Note: The table uses total_credits and credits_remaining (stored directly, not calculated)
    UPDATE public.user_credits
    SET 
        total_credits = total_credits + amount,
        credits_remaining = credits_remaining + amount,
        updated_at = NOW()
    WHERE user_id = user_uuid
    RETURNING total_credits, credits_remaining INTO new_total, new_remaining;
    
    -- If no row was updated, create one
    IF NOT FOUND THEN
        INSERT INTO public.user_credits (user_id, total_credits, credits_remaining)
        VALUES (user_uuid, amount, amount)
        RETURNING total_credits, credits_remaining INTO new_total, new_remaining;
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

-- This migration is idempotent - safe to run multiple times

