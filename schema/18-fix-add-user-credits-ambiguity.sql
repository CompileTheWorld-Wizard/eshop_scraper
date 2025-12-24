-- Migration: Fix add_user_credits function column ambiguity
-- Fixes: column reference "credits_remaining" is ambiguous error
-- Date: 2024

-- The issue was that the RETURNING clause in UPDATE statements was ambiguous
-- because the function return type has columns with the same names.
-- Solution: Separate UPDATE from SELECT to avoid ambiguity

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
-- Note: Returns credits_total and credits_remaining (stored directly) for compatibility
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
    -- Use explicit table column references to avoid ambiguity with return type column names
    IF credit_type = 'addon' THEN
        -- Add to addon credits
        UPDATE public.user_credits uc
        SET 
            total_credits = COALESCE(uc.total_credits, 0) + amount,
            addon_credits_remaining = COALESCE(uc.addon_credits_remaining, 0) + amount,
            -- Recalculate credits_remaining from updated subscription + addon values
            credits_remaining = COALESCE(uc.subscription_credits_remaining, 0) + (COALESCE(uc.addon_credits_remaining, 0) + amount),
            updated_at = NOW()
        WHERE uc.user_id = user_uuid;
        
        -- Get the updated values (separate SELECT to avoid ambiguity)
        SELECT COALESCE(uc.total_credits, 0), uc.credits_remaining 
        INTO new_total, new_remaining
        FROM public.user_credits uc
        WHERE uc.user_id = user_uuid;
    ELSE
        -- Add to subscription credits (default for admin bonuses, etc.)
        UPDATE public.user_credits uc
        SET 
            total_credits = COALESCE(uc.total_credits, 0) + amount,
            subscription_credits_remaining = COALESCE(uc.subscription_credits_remaining, 0) + amount,
            -- Recalculate credits_remaining from updated subscription + addon values
            credits_remaining = (COALESCE(uc.subscription_credits_remaining, 0) + amount) + COALESCE(uc.addon_credits_remaining, 0),
            updated_at = NOW()
        WHERE uc.user_id = user_uuid;
        
        -- Get the updated values (separate SELECT to avoid ambiguity)
        SELECT COALESCE(uc.total_credits, 0), uc.credits_remaining 
        INTO new_total, new_remaining
        FROM public.user_credits uc
        WHERE uc.user_id = user_uuid;
    END IF;
    
    -- If no row was updated (new_total is NULL), create one
    IF new_total IS NULL THEN
        IF credit_type = 'addon' THEN
            WITH inserted_credits AS (
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
                RETURNING total_credits AS insert_total, credits_remaining AS insert_remaining
            )
            SELECT insert_total, insert_remaining INTO new_total, new_remaining FROM inserted_credits;
        ELSE
            WITH inserted_credits AS (
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
                RETURNING total_credits AS insert_total, credits_remaining AS insert_remaining
            )
            SELECT insert_total, insert_remaining INTO new_total, new_remaining FROM inserted_credits;
        END IF;
    END IF;
    
    -- Record transaction (skip for admin adjustments to avoid action_id requirement)
    -- Only insert if reference_type is provided and it's not 'admin'
    IF reference_type IS NOT NULL AND reference_type != 'admin' THEN
        INSERT INTO public.credit_transactions (
            user_id, 
            action_id, 
            transaction_type, 
            credits_amount, 
            reference_id, 
            reference_type, 
            description,
            balance_after,
            metadata
        ) 
        SELECT 
            user_uuid,
            (SELECT id FROM public.credit_actions WHERE action_name = reference_type LIMIT 1),
            'addition',
            amount,
            reference_uuid, -- Use converted UUID
            reference_type,
            description,
            new_remaining, -- balance_after is required
            metadata
        WHERE EXISTS (SELECT 1 FROM public.credit_actions WHERE action_name = reference_type);
    END IF;
    
    -- Return credits_total and credits_remaining (stored directly)
    RETURN QUERY SELECT new_total, new_remaining;
END;
$$ LANGUAGE plpgsql;

-- Grant execute permission to authenticated users
GRANT EXECUTE ON FUNCTION add_user_credits(UUID, INTEGER, TEXT, TEXT, TEXT, JSONB) TO authenticated;

