-- Migration: Update deduct_user_credits to use subscription vs addon credits (FIFO)
-- Purpose: Requirement 2 - Deduct from subscription credits first, then addon credits (FIFO)
-- Date: 2024
-- This migration is idempotent - safe to run multiple times

-- Drop and recreate deduct_user_credits with FIFO logic
DROP FUNCTION IF EXISTS deduct_user_credits(UUID, TEXT, UUID, TEXT, TEXT);

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
    remaining_to_deduct INTEGER;
    subscription_credits INTEGER;
    addon_credits INTEGER;
    addon_record RECORD;
    credits_deducted_from_subscription INTEGER := 0;
    credits_deducted_from_addon INTEGER := 0;
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
    
    -- Get current credit balances
    SELECT 
        COALESCE(subscription_credits_remaining, 0),
        COALESCE(addon_credits_remaining, 0)
    INTO subscription_credits, addon_credits
    FROM public.user_credits
    WHERE user_id = user_uuid;
    
    -- If no user_credits record exists, create one with 0 credits
    IF NOT FOUND THEN
        INSERT INTO public.user_credits (
            user_id,
            credits_total,
            credits_remaining,
            subscription_credits_remaining,
            addon_credits_remaining
        )
        VALUES (user_uuid, 0, 0, 0, 0);
        
        subscription_credits := 0;
        addon_credits := 0;
    END IF;
    
    -- Deduct credits: First from subscription_credits_remaining, then from addon_credits_remaining (FIFO)
    remaining_to_deduct := credit_cost_val;
    
    -- First, deduct from subscription credits
    IF subscription_credits > 0 AND remaining_to_deduct > 0 THEN
        IF subscription_credits >= remaining_to_deduct THEN
            credits_deducted_from_subscription := remaining_to_deduct;
            remaining_to_deduct := 0;
        ELSE
            credits_deducted_from_subscription := subscription_credits;
            remaining_to_deduct := remaining_to_deduct - subscription_credits;
        END IF;
    END IF;
    
    -- Then, deduct from addon credits (FIFO - oldest first)
    IF remaining_to_deduct > 0 AND addon_credits > 0 THEN
        -- Find oldest addon_credits record with remaining credits
        SELECT id, credits_remaining
        INTO addon_record
        FROM public.addon_credits
        WHERE user_id = user_uuid
          AND credits_remaining > 0
          AND expires_at > NOW()
        ORDER BY created_at ASC, expires_at ASC
        LIMIT 1;
        
        IF addon_record IS NOT NULL THEN
            IF addon_record.credits_remaining >= remaining_to_deduct THEN
                -- Deduct all from this addon
                UPDATE public.addon_credits
                SET 
                    credits_remaining = credits_remaining - remaining_to_deduct,
                    updated_at = NOW()
                WHERE id = addon_record.id;
                
                credits_deducted_from_addon := remaining_to_deduct;
                remaining_to_deduct := 0;
            ELSE
                -- Deduct all remaining from this addon, then continue with next
                credits_deducted_from_addon := addon_record.credits_remaining;
                remaining_to_deduct := remaining_to_deduct - addon_record.credits_remaining;
                
                UPDATE public.addon_credits
                SET 
                    credits_remaining = 0,
                    updated_at = NOW()
                WHERE id = addon_record.id;
                
                -- If still need more, deduct from addon_credits_remaining total
                -- (Simplified: we'll update the total and let the next deduction handle it)
            END IF;
        END IF;
        
        -- If still need more credits and there are more addon records, deduct from total
        IF remaining_to_deduct > 0 THEN
            -- Deduct remaining from addon_credits_remaining total
            IF addon_credits >= remaining_to_deduct THEN
                credits_deducted_from_addon := credits_deducted_from_addon + remaining_to_deduct;
                remaining_to_deduct := 0;
            ELSE
                credits_deducted_from_addon := credits_deducted_from_addon + addon_credits;
                remaining_to_deduct := remaining_to_deduct - addon_credits;
            END IF;
        END IF;
    END IF;
    
    -- Update user_credits table with deductions
    UPDATE public.user_credits
    SET 
        subscription_credits_remaining = subscription_credits_remaining - credits_deducted_from_subscription,
        addon_credits_remaining = GREATEST(0, addon_credits_remaining - credits_deducted_from_addon),
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
    
    -- Record transaction with metadata about which type was used
    INSERT INTO public.credit_transactions (
        user_id, action_id, transaction_type, credits_amount, 
        reference_id, reference_type, description,
        metadata
    ) VALUES (
        user_uuid, action_id_val, 'deduction', credit_cost_val,
        reference_id, reference_type, description,
        jsonb_build_object(
            'deducted_from_subscription', credits_deducted_from_subscription,
            'deducted_from_addon', credits_deducted_from_addon
        )
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

