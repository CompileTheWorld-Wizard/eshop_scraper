-- Migration: Add reset_subscription_credits_on_renewal function
-- Purpose: Requirement 1 & 2 - Reset subscription credits on billing cycle renewal
-- Date: 2024
-- This migration is idempotent - safe to run multiple times

-- Drop function if it exists (to allow re-creation)
DROP FUNCTION IF EXISTS reset_subscription_credits_on_renewal(UUID);

-- ============================================================================
-- Function: reset_subscription_credits_on_renewal
-- Purpose: Requirement 1 & 2 - Reset subscription credits on billing cycle renewal
--          Unused credits do NOT roll over - reset to 0, then allocate new credits from plan
-- ============================================================================

CREATE OR REPLACE FUNCTION reset_subscription_credits_on_renewal(user_uuid UUID)
RETURNS BOOLEAN AS $$
DECLARE
    user_subscription RECORD;
    plan_monthly_credits INTEGER;
    current_period_start_val TIMESTAMPTZ;
    last_reset_val TIMESTAMPTZ;
    action_id_val UUID;
    balance_after_val INTEGER;  -- Store the balance after reset (required by credit_transactions table)
BEGIN
    -- Get user's active subscription and plan
    SELECT 
        us.id,
        us.plan_id,
        us.current_period_start,
        us.current_period_end,
        sp.monthly_credits
    INTO user_subscription
    FROM public.user_subscriptions us
    JOIN public.subscription_plans sp ON us.plan_id = sp.id
    WHERE us.user_id = user_uuid
      AND us.status = 'active'
    ORDER BY us.created_at DESC
    LIMIT 1;
    
    -- If no active subscription found, return false
    IF user_subscription IS NULL THEN
        RAISE NOTICE 'No active subscription found for user %', user_uuid;
        RETURN false;
    END IF;
    
    plan_monthly_credits := COALESCE(user_subscription.monthly_credits, 0);
    current_period_start_val := user_subscription.current_period_start;
    
    -- Get last reset timestamp for idempotency check
    SELECT last_billing_cycle_reset INTO last_reset_val
    FROM public.user_credits
    WHERE user_id = user_uuid;
    
    -- Idempotency check: if already reset for this billing period, skip
    IF last_reset_val IS NOT NULL 
       AND current_period_start_val IS NOT NULL
       AND last_reset_val >= current_period_start_val THEN
        RAISE NOTICE 'Credits already reset for user % in current billing period', user_uuid;
        RETURN true;
    END IF;
    
    -- Get action_id for 'subscription_renewal' transaction (use a generic action or create one)
    SELECT id INTO action_id_val
    FROM public.credit_actions
    WHERE action_name = 'subscription_renewal'
    LIMIT 1;
    
    -- If action doesn't exist, use a default action (e.g., 'subscription_plan')
    IF action_id_val IS NULL THEN
        SELECT id INTO action_id_val
        FROM public.credit_actions
        WHERE action_name = 'subscription_plan'
        LIMIT 1;
    END IF;
    
    -- If still no action found, try to get any action (fallback)
    IF action_id_val IS NULL THEN
        SELECT id INTO action_id_val
        FROM public.credit_actions
        WHERE is_active = true
        LIMIT 1;
    END IF;
    
    -- Reset subscription credits: set to 0, then allocate new credits from plan
    -- Expire all add-on credits (set to 0 and delete expired records)
    -- Capture balance_after using RETURNING clause (required by credit_transactions table)
    UPDATE public.user_credits
    SET 
        -- Reset subscription credits to 0, then allocate new credits
        subscription_credits_remaining = plan_monthly_credits,
        -- Expire all add-on credits (they don't roll over)
        addon_credits_remaining = 0,
        -- Update total remaining (subscription + addon)
        credits_remaining = plan_monthly_credits,
        -- Reset cycle tracking
        cycle_used_credits = 0,
        cycle_start_at = current_period_start_val,
        -- Update last reset timestamp
        last_billing_cycle_reset = NOW(),
        updated_at = NOW()
    WHERE user_id = user_uuid
    RETURNING credits_remaining INTO balance_after_val;
    
    -- If no row was updated, create one and capture balance_after
    IF NOT FOUND THEN
        INSERT INTO public.user_credits (
            user_id,
            credits_total,
            credits_remaining,
            subscription_credits_remaining,
            addon_credits_remaining,
            cycle_used_credits,
            cycle_start_at,
            last_billing_cycle_reset
        )
        VALUES (
            user_uuid,
            plan_monthly_credits,
            plan_monthly_credits,
            plan_monthly_credits,
            0,
            0,
            current_period_start_val,
            NOW()
        )
        RETURNING credits_remaining INTO balance_after_val;
    END IF;
    
    -- Delete expired addon_credits records (where expires_at <= current_period_end)
    DELETE FROM public.addon_credits
    WHERE user_id = user_uuid
      AND expires_at <= user_subscription.current_period_end;
    
    -- Record transaction for audit trail (only if action_id was found)
    -- balance_after is required by credit_transactions table (NOT NULL constraint)
    IF action_id_val IS NOT NULL THEN
        INSERT INTO public.credit_transactions (
            user_id,
            action_id,
            transaction_type,
            credits_amount,
            reference_id,
            reference_type,
            description,
            balance_after
        ) VALUES (
            user_uuid,
            action_id_val,
            'addition',
            plan_monthly_credits,
            user_subscription.plan_id,
            'subscription_renewal',
            format('Billing cycle renewal: allocated %s credits from plan (unused credits did not roll over)', plan_monthly_credits),
            balance_after_val
        );
    END IF;
    
    RETURN true;
END;
$$ LANGUAGE plpgsql;

-- Add comment to document the function
COMMENT ON FUNCTION reset_subscription_credits_on_renewal(UUID) IS 
'Resets subscription credits on billing cycle renewal. Sets subscription_credits_remaining to plan monthly_credits, expires all addon credits, and resets cycle tracking. Unused credits do NOT roll over.';

