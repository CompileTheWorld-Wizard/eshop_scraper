-- Migration: Fix credit functions to use credits_remaining instead of used_credits
-- Purpose: Update all credit-related functions to use credits_remaining (stored directly) 
--          instead of calculating total_credits - used_credits
-- Date: 2024
-- This migration is idempotent - safe to run multiple times

-- ========================================
-- PART 1: Ensure credits_remaining column exists
-- ========================================

-- Add credits_remaining column if it doesn't exist (for tables that might still have used_credits)
DO $$
BEGIN
    -- Check if credits_remaining column exists, if not add it
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'user_credits' 
        AND column_name = 'credits_remaining'
    ) THEN
        -- Add credits_remaining column
        ALTER TABLE public.user_credits
        ADD COLUMN credits_remaining INTEGER NOT NULL DEFAULT 0;
        
        -- Migrate existing data: calculate credits_remaining from total_credits - used_credits
        -- (if used_credits column exists)
        IF EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'user_credits' 
            AND column_name = 'used_credits'
        ) THEN
            UPDATE public.user_credits
            SET credits_remaining = GREATEST(0, COALESCE(total_credits, 0) - COALESCE(used_credits, 0))
            WHERE credits_remaining = 0; -- Only update rows that haven't been migrated yet
        ELSE
            -- If used_credits doesn't exist, set credits_remaining = total_credits
            UPDATE public.user_credits
            SET credits_remaining = COALESCE(total_credits, 0)
            WHERE credits_remaining = 0;
        END IF;
        
        -- Add comment
        COMMENT ON COLUMN public.user_credits.credits_remaining IS 
            'Remaining credits available to the user (stored directly, not calculated)';
    END IF;
END $$;

-- ========================================
-- PART 2: Update can_perform_action function
-- ========================================

DROP FUNCTION IF EXISTS can_perform_action(UUID, TEXT);

CREATE OR REPLACE FUNCTION can_perform_action(
    user_uuid UUID,
    action_name TEXT
)
RETURNS TABLE(
    can_perform BOOLEAN,
    reason TEXT,
    current_credits INTEGER,
    required_credits INTEGER,
    monthly_limit INTEGER,
    daily_limit INTEGER,
    monthly_used INTEGER,
    daily_used INTEGER
) AS $$
DECLARE
    user_credits INTEGER;
    action_cost INTEGER;
    user_plan_id UUID;
    monthly_limit_val INTEGER;
    daily_limit_val INTEGER;
    monthly_used_val INTEGER;
    daily_used_val INTEGER;
    plan_monthly_credits INTEGER;
    cycle_used INTEGER;
    cycle_start TIMESTAMPTZ;
    current_period_start TIMESTAMPTZ;
    subscription_status TEXT;
    subscription_cancel_at_period_end BOOLEAN;
    subscription_period_end TIMESTAMPTZ;
    rendering_blocked_val BOOLEAN;
    is_trial_user_val BOOLEAN;
    trial_preview_used_val BOOLEAN;
BEGIN
    -- Requirement 9: Check if user is a trial user
    SELECT 
        COALESCE(up.is_trial_user, false),
        COALESCE(up.trial_preview_used, false)
    INTO is_trial_user_val, trial_preview_used_val
    FROM public.user_profiles up
    WHERE up.user_id = user_uuid;
    
    -- Requirement 9: Trial users can only use preview_render (one-time, 0 credits)
    IF is_trial_user_val = true THEN
        IF can_perform_action.action_name != 'preview_render' THEN
            SELECT ca.base_credit_cost INTO action_cost
            FROM public.credit_actions ca
            WHERE ca.action_name = can_perform_action.action_name;
            
            RETURN QUERY SELECT 
                false AS can_perform,
                'Trial users can only use preview render - subscription required for other actions' AS reason,
                0 AS current_credits,
                action_cost AS required_credits,
                NULL::INTEGER AS monthly_limit,
                NULL::INTEGER AS daily_limit,
                NULL::INTEGER AS monthly_used,
                NULL::INTEGER AS daily_used;
            RETURN;
        ELSIF trial_preview_used_val = true THEN
            -- Preview already used
            SELECT ca.base_credit_cost INTO action_cost
            FROM public.credit_actions ca
            WHERE ca.action_name = can_perform_action.action_name;
            
            RETURN QUERY SELECT 
                false AS can_perform,
                'Trial preview already used - subscription required' AS reason,
                0 AS current_credits,
                action_cost AS required_credits,
                NULL::INTEGER AS monthly_limit,
                NULL::INTEGER AS daily_limit,
                NULL::INTEGER AS monthly_used,
                NULL::INTEGER AS daily_used;
            RETURN;
        ELSE
            -- Allow preview_render (0 credits, one-time use)
            RETURN QUERY SELECT 
                true AS can_perform,
                'Trial preview render allowed' AS reason,
                0 AS current_credits,
                0 AS required_credits,
                NULL::INTEGER AS monthly_limit,
                NULL::INTEGER AS daily_limit,
                NULL::INTEGER AS monthly_used,
                NULL::INTEGER AS daily_used;
            RETURN;
        END IF;
    END IF;
    
    -- Requirement 5: Check if subscription is canceled and past period end
    -- Requirement 7: Check if rendering is blocked due to payment failure
    SELECT 
        us.status,
        us.cancel_at_period_end,
        us.current_period_end,
        COALESCE(us.rendering_blocked, false)
    INTO subscription_status, subscription_cancel_at_period_end, subscription_period_end, rendering_blocked_val
    FROM public.user_subscriptions us
    WHERE us.user_id = user_uuid
    ORDER BY us.created_at DESC
    LIMIT 1;
    
    -- Requirement 7: Block if rendering is blocked (payment failure grace period expired)
    IF rendering_blocked_val = true THEN
        SELECT ca.base_credit_cost INTO action_cost
        FROM public.credit_actions ca
        WHERE ca.action_name = can_perform_action.action_name;
        
        RETURN QUERY SELECT 
            false AS can_perform,
            'Rendering blocked - payment required' AS reason,
            0 AS current_credits,
            action_cost AS required_credits,
            NULL::INTEGER AS monthly_limit,
            NULL::INTEGER AS daily_limit,
            NULL::INTEGER AS monthly_used,
            NULL::INTEGER AS daily_used;
        RETURN;
    END IF;
    
    -- Block if subscription is canceled and period has ended
    IF (subscription_status = 'canceled' OR subscription_cancel_at_period_end = true) 
       AND subscription_period_end IS NOT NULL 
       AND subscription_period_end < NOW() THEN
        SELECT ca.base_credit_cost INTO action_cost
        FROM public.credit_actions ca
        WHERE ca.action_name = can_perform_action.action_name;
        
        RETURN QUERY SELECT 
            false AS can_perform,
            'Subscription expired - credits no longer available' AS reason,
            0 AS current_credits,
            action_cost AS required_credits,
            NULL::INTEGER AS monthly_limit,
            NULL::INTEGER AS daily_limit,
            NULL::INTEGER AS monthly_used,
            NULL::INTEGER AS daily_used;
        RETURN;
    END IF;
    
    -- Get user's current credits (global remaining balance)
    -- Use credits_remaining directly (stored value, not calculated)
    SELECT COALESCE(uc.credits_remaining, 0) INTO user_credits
    FROM public.user_credits uc
    WHERE uc.user_id = user_uuid;
    
    -- Get action cost and limits for the user's active plan
    SELECT 
        pcc.credit_cost,
        pcc.monthly_limit,
        pcc.daily_limit,
        us.plan_id
    INTO action_cost, monthly_limit_val, daily_limit_val, user_plan_id
    FROM public.credit_actions ca
    LEFT JOIN public.plan_credit_configs pcc ON ca.id = pcc.action_id
    LEFT JOIN public.user_subscriptions us ON pcc.plan_id = us.plan_id
    WHERE ca.action_name = can_perform_action.action_name
      AND us.user_id = user_uuid
      AND us.status = 'active';
    
    -- If no active plan-specific config found, fall back to base cost and simple balance check
    IF user_plan_id IS NULL THEN
        SELECT ca.base_credit_cost INTO action_cost
        FROM public.credit_actions ca
        WHERE ca.action_name = can_perform_action.action_name;
        
        RETURN QUERY SELECT 
            user_credits >= action_cost AS can_perform,
            CASE 
                WHEN user_credits < action_cost THEN 'Insufficient credits'
                ELSE 'Can perform action'
            END AS reason,
            user_credits AS current_credits,
            action_cost AS required_credits,
            NULL::INTEGER AS monthly_limit,
            NULL::INTEGER AS daily_limit,
            NULL::INTEGER AS monthly_used,
            NULL::INTEGER AS daily_used;
        RETURN;
    END IF;
    
    -- Get usage counts (per-action daily/monthly limits)
    -- Handle case where credit_usage_tracking table might not exist
    BEGIN
        SELECT COALESCE(SUM(cut.usage_count), 0) INTO monthly_used_val
        FROM public.credit_usage_tracking cut
        JOIN public.credit_actions ca ON cut.action_id = ca.id
        WHERE cut.user_id = user_uuid
          AND ca.action_name = can_perform_action.action_name
          AND cut.usage_month = TO_CHAR(CURRENT_DATE, 'YYYY-MM');
    EXCEPTION 
        WHEN undefined_table THEN
            monthly_used_val := 0;
        WHEN OTHERS THEN
            monthly_used_val := 0;
    END;
    
    BEGIN
        SELECT COALESCE(SUM(cut.usage_count), 0) INTO daily_used_val
        FROM public.credit_usage_tracking cut
        JOIN public.credit_actions ca ON cut.action_id = ca.id
        WHERE cut.user_id = user_uuid
          AND ca.action_name = can_perform_action.action_name
          AND cut.usage_date = CURRENT_DATE;
    EXCEPTION 
        WHEN undefined_table THEN
            daily_used_val := 0;
        WHEN OTHERS THEN
            daily_used_val := 0;
    END;
    
    -- Get plan-level monthly credits for this user's plan
    SELECT sp.monthly_credits
    INTO plan_monthly_credits
    FROM public.subscription_plans sp
    WHERE sp.id = user_plan_id;
    
    -- Get current billing period start for the user's active subscription
    SELECT us.current_period_start
    INTO current_period_start
    FROM public.user_subscriptions us
    WHERE us.user_id = user_uuid
      AND us.plan_id = user_plan_id
      AND us.status = 'active'
    ORDER BY us.created_at DESC
    LIMIT 1;
    
    -- Get per-cycle usage from user_credits
    SELECT uc.cycle_used_credits, uc.cycle_start_at
    INTO cycle_used, cycle_start
    FROM public.user_credits uc
    WHERE uc.user_id = user_uuid;
    
    -- If cycle_start is not aligned with current_period_start, treat current cycle usage as 0
    IF cycle_start IS NULL OR current_period_start IS NULL OR cycle_start <> current_period_start THEN
        cycle_used := 0;
    END IF;
    
    -- Check if user can perform action
    RETURN QUERY SELECT 
        user_credits >= action_cost 
        AND (monthly_limit_val IS NULL OR monthly_used_val < monthly_limit_val)
        AND (daily_limit_val IS NULL OR daily_used_val < daily_limit_val)
        AND (
            plan_monthly_credits IS NULL
            OR plan_monthly_credits <= 0
            OR (cycle_used + action_cost) <= plan_monthly_credits
        ) AS can_perform,
        CASE 
            WHEN user_credits < action_cost THEN 'Insufficient credits'
            WHEN monthly_limit_val IS NOT NULL AND monthly_used_val >= monthly_limit_val THEN 'Monthly limit reached'
            WHEN daily_limit_val IS NOT NULL AND daily_used_val >= daily_limit_val THEN 'Daily limit reached'
            WHEN plan_monthly_credits IS NOT NULL 
                 AND plan_monthly_credits > 0 
                 AND (cycle_used + action_cost) > plan_monthly_credits
                 THEN 'Plan monthly credits exhausted for current billing cycle'
            ELSE 'Can perform action'
        END AS reason,
        user_credits AS current_credits,
        action_cost AS required_credits,
        monthly_limit_val AS monthly_limit,
        daily_limit_val AS daily_limit,
        monthly_used_val AS monthly_used,
        daily_used_val AS daily_used;
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- PART 3: Update deduct_user_credits function
-- ========================================

-- Drop ALL overloads of deduct_user_credits to prevent function overloading conflicts
-- This ensures no old versions remain with different parameter orders
DROP FUNCTION IF EXISTS public.deduct_user_credits CASCADE;

-- Alternative: If CASCADE doesn't work, drop all possible signatures explicitly:
-- DROP FUNCTION IF EXISTS public.deduct_user_credits(UUID, TEXT, UUID, TEXT, TEXT);
-- DROP FUNCTION IF EXISTS public.deduct_user_credits(UUID, TEXT, TEXT, UUID, TEXT);
-- DROP FUNCTION IF EXISTS public.deduct_user_credits(UUID, TEXT, INTEGER, TEXT, TEXT, TEXT);
-- DROP FUNCTION IF EXISTS public.deduct_user_credits(UUID, TEXT);

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
    
    -- Record transaction
    INSERT INTO public.credit_transactions (
        user_id, action_id, type, transaction_type, credits_amount, 
        reference_id, reference_type, description
    ) VALUES (
        user_uuid, action_id_val, action_name, 'deduction', credit_cost_val,
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
-- PART 4: Update get_user_credits function
-- ========================================

DROP FUNCTION IF EXISTS get_user_credits(UUID);

CREATE OR REPLACE FUNCTION get_user_credits(user_uuid UUID)
RETURNS TABLE(
    credits_total INTEGER,
    credits_remaining INTEGER,
    subscription_status TEXT,
    plan_name TEXT,
    plan_display_name TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COALESCE(uc.total_credits, 0) as credits_total,
        COALESCE(uc.credits_remaining, 0) as credits_remaining,
        COALESCE(us.status, 'no_subscription') as subscription_status,
        COALESCE(sp.name, 'no_plan') as plan_name,
        COALESCE(sp.display_name, 'No Plan') as plan_display_name
    FROM auth.users u
    LEFT JOIN public.user_credits uc ON u.id = uc.user_id
    LEFT JOIN public.user_subscriptions us ON u.id = us.user_id AND us.status = 'active'
    LEFT JOIN public.subscription_plans sp ON us.plan_id = sp.id
    WHERE u.id = user_uuid;
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- PART 5: Update get_user_status function
-- ========================================

DROP FUNCTION IF EXISTS get_user_status(UUID);

CREATE OR REPLACE FUNCTION get_user_status(user_uuid UUID)
RETURNS TABLE(
    user_id UUID,
    full_name TEXT,
    email TEXT,
    role TEXT,
    is_active BOOLEAN,
    onboarding_completed BOOLEAN,
    subscription_status TEXT,
    plan_name TEXT,
    plan_display_name TEXT,
    credits_total INTEGER,
    credits_remaining INTEGER,
    created_at TIMESTAMP WITH TIME ZONE,
    last_activity TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        u.id as user_id,
        up.full_name,
        u.email,
        up.role,
        up.is_active,
        up.onboarding_completed,
        COALESCE(us.status, 'no_subscription') as subscription_status,
        COALESCE(sp.name, 'no_plan') as plan_name,
        COALESCE(sp.display_name, 'No Plan') as plan_display_name,
        COALESCE(uc.total_credits, 0) as credits_total,
        COALESCE(uc.credits_remaining, 0) as credits_remaining,
        up.created_at,
        (SELECT MAX(created_at) FROM public.user_activities WHERE user_id = u.id) as last_activity
    FROM auth.users u
    LEFT JOIN public.user_profiles up ON u.id = up.user_id
    LEFT JOIN public.user_credits uc ON u.id = uc.user_id
    LEFT JOIN public.user_subscriptions us ON u.id = us.user_id AND us.status = 'active'
    LEFT JOIN public.subscription_plans sp ON us.plan_id = sp.id
    WHERE u.id = user_uuid;
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- PART 6: Update add_user_credits function
-- ========================================

DROP FUNCTION IF EXISTS add_user_credits(UUID, TEXT, INTEGER, UUID, TEXT, TEXT);
DROP FUNCTION IF EXISTS add_user_credits(UUID, INTEGER, TEXT, UUID, TEXT, JSONB);
DROP FUNCTION IF EXISTS add_user_credits(UUID, INTEGER, TEXT, TEXT, TEXT, JSONB);
DROP FUNCTION IF EXISTS add_user_credits(UUID, TEXT, INTEGER, TEXT, TEXT, TEXT);

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

-- ========================================
-- PART 7: Update initialize_user_profile function
-- ========================================

-- Note: This function is in schema/06-functions.sql, but we'll update it here for consistency
-- The base file should also be updated, but this ensures the function is correct

DO $$
BEGIN
    -- Check if initialize_user_profile function exists and update it
    IF EXISTS (
        SELECT 1 
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'public' 
        AND p.proname = 'initialize_user_profile'
    ) THEN
        -- Function exists, we'll update it via a separate statement if needed
        -- For now, the base file should be updated manually
        NULL;
    END IF;
END $$;

-- Add comment
COMMENT ON FUNCTION can_perform_action(UUID, TEXT) IS 
    'Checks if user can perform an action based on credits, limits, and subscription status. Uses credits_remaining directly.';
    
COMMENT ON FUNCTION deduct_user_credits(UUID, TEXT, UUID, TEXT, TEXT) IS 
    'Deducts credits from user. Uses credits_remaining (stored directly) instead of calculating from used_credits.';

COMMENT ON FUNCTION add_user_credits(UUID, INTEGER, TEXT, TEXT, TEXT, JSONB) IS 
    'Adds credits to user. Updates both total_credits and credits_remaining (stored directly).';

-- This migration is idempotent - safe to run multiple times

