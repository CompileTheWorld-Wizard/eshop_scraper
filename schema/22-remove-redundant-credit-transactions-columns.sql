-- Migration: Remove redundant type and amount columns from credit_transactions
-- Description: Removes the redundant 'type' and 'amount' columns from credit_transactions table
-- These columns duplicate information already available via action_id (JOIN) and credits_amount
-- Date: 2025-12-07

-- ========================================
-- PART 1: Update deduct_user_credits function (remove type and amount)
-- ========================================

CREATE OR REPLACE FUNCTION deduct_user_credits(
    user_uuid UUID,
    action_name TEXT,
    reference_id UUID DEFAULT NULL,
    reference_type TEXT DEFAULT NULL,
    description TEXT DEFAULT NULL
)
RETURNS BOOLEAN AS $$
DECLARE
    action_id_val UUID;
    credit_cost_val INTEGER;
    can_perform_val BOOLEAN;
    reason_val TEXT;
    user_plan_id UUID;
    current_period_start TIMESTAMPTZ;
BEGIN
    -- Check if user can perform action (includes cancellation check from can_perform_action)
    SELECT can_perform, reason INTO can_perform_val, reason_val
    FROM can_perform_action(user_uuid, action_name);
    
    IF NOT can_perform_val THEN
        RAISE EXCEPTION 'Cannot perform action: %', reason_val;
    END IF;
    
    -- Get action details (base credit cost)
    SELECT ca.id, ca.base_credit_cost INTO action_id_val, credit_cost_val
    FROM public.credit_actions ca
    WHERE ca.action_name = deduct_user_credits.action_name;
    
    -- CRITICAL: Check if action was found
    IF action_id_val IS NULL OR credit_cost_val IS NULL THEN
        RAISE EXCEPTION 'Action not found: %', deduct_user_credits.action_name;
    END IF;
    
    -- Requirement 9: If this is a preview_render for a trial user, mark preview as used
    IF deduct_user_credits.action_name = 'preview_render' THEN
        UPDATE public.user_profiles
        SET 
            trial_preview_used = true,
            trial_preview_used_at = NOW(),
            updated_at = NOW()
        WHERE user_id = user_uuid
          AND is_trial_user = true
          AND trial_preview_used = false;
    END IF;
    
    -- Get user's active plan (if any) and current billing period start
    SELECT us.plan_id, us.current_period_start
    INTO user_plan_id, current_period_start
    FROM public.user_subscriptions us
    WHERE us.user_id = user_uuid
      AND us.status = 'active'
    ORDER BY us.created_at DESC
    LIMIT 1;
    
    -- Deduct credits from user_credits table and update per-cycle usage
    -- Note: preview_render has 0 credit cost, so no actual deduction happens
    -- Update credits_remaining (decrement by credit_cost_val) - stored directly, not calculated
    UPDATE public.user_credits
    SET 
        credits_remaining = credits_remaining - credit_cost_val,
        cycle_used_credits = CASE
            WHEN current_period_start IS NULL THEN cycle_used_credits
            WHEN cycle_start_at IS NULL OR cycle_start_at <> current_period_start
                THEN credit_cost_val
            ELSE cycle_used_credits + credit_cost_val
        END,
        cycle_start_at = CASE
            WHEN current_period_start IS NULL THEN cycle_start_at
            ELSE current_period_start
        END,
        updated_at = NOW()
    WHERE user_id = user_uuid;
    
    -- If no row was updated, create one and apply deduction + cycle usage
    IF NOT FOUND THEN
        INSERT INTO public.user_credits (
            user_id,
            total_credits,
            credits_remaining,
            cycle_used_credits,
            cycle_start_at
        )
        VALUES (
            user_uuid,
            0,
            0 - credit_cost_val,  -- Start with 0, deduct credit_cost_val
            CASE WHEN current_period_start IS NULL THEN 0 ELSE credit_cost_val END,
            current_period_start
        );
    END IF;
    
    -- Record transaction (removed redundant type and amount columns)
    INSERT INTO public.credit_transactions (
        user_id, action_id, transaction_type, credits_amount, 
        reference_id, reference_type, description
    ) VALUES (
        user_uuid, action_id_val, 'deduction', credit_cost_val,
        reference_id, reference_type, description
    );
    
    -- Update usage tracking (only if table exists)
    BEGIN
        INSERT INTO public.credit_usage_tracking (
            user_id, action_id, usage_date, usage_month, usage_count
        ) VALUES (
            user_uuid, action_id_val, CURRENT_DATE, TO_CHAR(CURRENT_DATE, 'YYYY-MM'), 1
        )
        ON CONFLICT (user_id, action_id, usage_date)
        DO UPDATE SET usage_count = credit_usage_tracking.usage_count + 1;
    EXCEPTION 
        WHEN undefined_table THEN
            -- Table doesn't exist, skip usage tracking (no-op)
            NULL;
        WHEN OTHERS THEN
            -- Any other error, skip usage tracking (no-op)
            NULL;
    END;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- PART 2: Update add_user_credits function (remove type and amount)
-- ========================================

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
    -- Removed redundant type and amount columns
    IF reference_type IS NOT NULL AND reference_type != 'admin' THEN
        INSERT INTO public.credit_transactions (
            user_id, 
            action_id, 
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

-- ========================================
-- PART 3: Update add_user_credits function (alternative signature)
-- ========================================

CREATE OR REPLACE FUNCTION add_user_credits(
    user_uuid UUID,
    action_name TEXT,
    credits_amount INTEGER,
    reference_id UUID DEFAULT NULL,
    reference_type TEXT DEFAULT NULL,
    description TEXT DEFAULT NULL
)
RETURNS BOOLEAN AS $$
DECLARE
    action_id_val UUID;
BEGIN
    -- Get action ID
    SELECT id INTO action_id_val
    FROM public.credit_actions
    WHERE action_name = action_name;
    
    -- Add credits to user_credits table
    UPDATE public.user_credits
    SET 
        credits_total = credits_total + credits_amount,
        credits_remaining = credits_remaining + credits_amount,
        updated_at = NOW()
    WHERE user_id = user_uuid;
    
    -- If no row was updated, create one
    IF NOT FOUND THEN
        INSERT INTO public.user_credits (user_id, credits_total, credits_remaining)
        VALUES (user_uuid, credits_amount, credits_amount);
    END IF;
    
    -- Record transaction (removed redundant type and amount columns)
    INSERT INTO public.credit_transactions (
        user_id, action_id, transaction_type, credits_amount, 
        reference_id, reference_type, description
    ) VALUES (
        user_uuid, action_id_val, 'addition', credits_amount,
        reference_id, reference_type, description
    );
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- PART 4: Drop the redundant columns
-- ========================================

-- First, drop NOT NULL constraints if they exist (in case columns are still being used)
DO $$
BEGIN
    -- Drop NOT NULL constraint on type column if it exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'credit_transactions' 
        AND column_name = 'type'
    ) THEN
        ALTER TABLE public.credit_transactions ALTER COLUMN type DROP NOT NULL;
    END IF;
    
    -- Drop NOT NULL constraint on amount column if it exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'credit_transactions' 
        AND column_name = 'amount'
    ) THEN
        ALTER TABLE public.credit_transactions ALTER COLUMN amount DROP NOT NULL;
    END IF;
END $$;

-- Drop the columns if they exist
DO $$
BEGIN
    -- Drop type column if it exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'credit_transactions' 
        AND column_name = 'type'
    ) THEN
        ALTER TABLE public.credit_transactions DROP COLUMN type;
    END IF;
    
    -- Drop amount column if it exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'credit_transactions' 
        AND column_name = 'amount'
    ) THEN
        ALTER TABLE public.credit_transactions DROP COLUMN amount;
    END IF;
END $$;

-- ========================================
-- Summary
-- ========================================
-- This migration removes the redundant 'type' and 'amount' columns from credit_transactions.
-- 
-- The 'type' column was redundant because:
--   - Action name can be obtained via JOIN: credit_transactions.action_id -> credit_actions.action_name
--   - Or use reference_type if it matches the action name
--
-- The 'amount' column was redundant because:
--   - credits_amount already stores the same value
--
-- All functions have been updated to remove references to these columns.
-- This migration is idempotent - safe to run multiple times.

