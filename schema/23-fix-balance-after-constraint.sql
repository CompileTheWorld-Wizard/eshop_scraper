-- Migration: Fix balance_after constraint violation in deduct_user_credits
-- Description: Updates deduct_user_credits function to capture and include balance_after
--              in credit_transactions INSERT statement
-- Date: 2025-12-07

-- ========================================
-- PART 1: Update deduct_user_credits function to include balance_after
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
    balance_after_val INTEGER;  -- Store the balance after deduction
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
    -- CRITICAL: Capture the new balance using RETURNING
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
    WHERE user_id = user_uuid
    RETURNING credits_remaining INTO balance_after_val;
    
    -- If no row was updated, create one and apply deduction + cycle usage
    -- CRITICAL: Capture the new balance using RETURNING
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
        )
        RETURNING credits_remaining INTO balance_after_val;
    END IF;
    
    -- Record transaction (include balance_after)
    INSERT INTO public.credit_transactions (
        user_id, action_id, transaction_type, credits_amount, 
        reference_id, reference_type, description,
        balance_after
    ) VALUES (
        user_uuid, action_id_val, 'deduction', credit_cost_val,
        reference_id, reference_type, description,
        balance_after_val
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
-- Summary
-- ========================================
-- This migration fixes the constraint violation error:
-- "null value in column 'balance_after' of relation 'credit_transactions' violates not-null constraint"
--
-- Changes made:
-- 1. Added balance_after_val variable to DECLARE section
-- 2. Added RETURNING credits_remaining INTO balance_after_val to UPDATE statement
-- 3. Added RETURNING credits_remaining INTO balance_after_val to INSERT statement
-- 4. Added balance_after column to INSERT INTO credit_transactions
-- 5. Added balance_after_val value to VALUES clause
--
-- This ensures that the balance_after column is always populated with the user's
-- credit balance after the deduction is applied.

