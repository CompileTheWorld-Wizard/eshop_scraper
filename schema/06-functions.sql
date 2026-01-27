-- Auto-Promo AI Database Functions
-- Utility functions for the application

-- Function to get user credits
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
$$ LANGUAGE plpgsql
SET search_path = public;

-- Function to get user status
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
$$ LANGUAGE plpgsql
SET search_path = public;

-- Function to check if user can perform an action (consolidated from migrations 15, 20)
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
$$ LANGUAGE plpgsql
SET search_path = public;

-- Function to deduct user credits (consolidated from migrations 15, 20, 21, 22, 23, 29)
-- Latest version includes FIFO logic for subscription vs addon credits
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
    balance_after_val INTEGER;  -- Store the balance after deduction (required by credit_transactions)
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
            total_credits,
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
    -- CRITICAL: Capture balance_after using RETURNING clause (required by credit_transactions table)
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
    WHERE user_id = user_uuid
    RETURNING credits_remaining INTO balance_after_val;
    
    -- If no row was updated, create one and apply deduction + cycle usage
    -- CRITICAL: Capture balance_after using RETURNING clause
    IF NOT FOUND THEN
        INSERT INTO public.user_credits (
            user_id,
            total_credits,
            credits_remaining,
            subscription_credits_remaining,
            addon_credits_remaining,
            cycle_used_credits,
            cycle_start_at
        )
        VALUES (
            user_uuid,
            0,
            0 - credit_cost_val,  -- Start with 0, deduct credit_cost_val
            0 - credits_deducted_from_subscription,
            0 - credits_deducted_from_addon,
            CASE WHEN current_period_start IS NULL THEN 0 ELSE credit_cost_val END,
            current_period_start
        )
        RETURNING credits_remaining INTO balance_after_val;
    END IF;
    
    -- Record transaction with metadata about which type was used
    -- balance_after is required by credit_transactions table (NOT NULL constraint)
    INSERT INTO public.credit_transactions (
        user_id, action_id, transaction_type, credits_amount, 
        reference_id, reference_type, description,
        balance_after,
        metadata
    ) VALUES (
        user_uuid, action_id_val, 'deduction', credit_cost_val,
        reference_id, reference_type, description,
        balance_after_val,
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
$$ LANGUAGE plpgsql
SET search_path = public;

-- Function to add user credits (consolidated from migrations 14, 20, 21, 22, 32, 34)
-- Latest version maintains subscription/addon credit consistency
CREATE OR REPLACE FUNCTION add_user_credits(
    user_uuid UUID,
    amount INTEGER,
    description TEXT DEFAULT NULL,
    reference_id TEXT DEFAULT NULL,
    reference_type TEXT DEFAULT NULL,
    metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE(
    result_credits_total INTEGER,
    result_credits_remaining INTEGER
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
        
        -- Get the updated values
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
        
        -- Get the updated values
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
    -- Use explicit aliases to avoid ambiguity with table column names
    RETURN QUERY SELECT new_total AS credits_total, new_remaining AS credits_remaining;
END;
$$ LANGUAGE plpgsql
SET search_path = public;

-- Grant execute permission to authenticated users
GRANT EXECUTE ON FUNCTION add_user_credits(UUID, INTEGER, TEXT, TEXT, TEXT, JSONB) TO authenticated;

-- Function to increment video views
CREATE OR REPLACE FUNCTION increment_video_views(video_uuid UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE public.shorts
    SET views = views + 1
    WHERE id = video_uuid;
END;
$$ LANGUAGE plpgsql
SET search_path = public;

-- Function to increment video downloads
CREATE OR REPLACE FUNCTION increment_video_downloads(video_uuid UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE public.shorts
    SET downloads = downloads + 1
    WHERE id = video_uuid;
END;
$$ LANGUAGE plpgsql
SET search_path = public;

-- Function to sync user credits to profile (consolidated from migration 34)
-- Uses explicit table aliases to avoid ambiguous column references
CREATE OR REPLACE FUNCTION sync_user_credits_to_profile(user_uuid UUID)
RETURNS VOID AS $$
BEGIN
    -- Use explicit table aliases to avoid ambiguity
    -- Note: user_credits table uses 'total_credits' column name
    UPDATE public.user_profiles up
    SET 
        credits_total = COALESCE(uc.total_credits, 0),
        credits_remaining = COALESCE(uc.credits_remaining, 0),
        updated_at = NOW()
    FROM public.user_credits uc
    WHERE up.user_id = user_uuid
    AND uc.user_id = user_uuid;
    
    -- If no user_credits record exists, set to 0
    IF NOT FOUND THEN
        UPDATE public.user_profiles
        SET 
            credits_total = 0,
            credits_remaining = 0,
            updated_at = NOW()
        WHERE user_id = user_uuid;
    END IF;
END;
$$ LANGUAGE plpgsql
SET search_path = public;

-- Function to sync all user credits (for admin use)
CREATE OR REPLACE FUNCTION sync_all_user_credits()
RETURNS INTEGER AS $$
DECLARE
    user_record RECORD;
    synced_count INTEGER := 0;
BEGIN
    FOR user_record IN 
        SELECT DISTINCT user_id 
        FROM public.user_credits
    LOOP
        PERFORM sync_user_credits_to_profile(user_record.user_id);
        synced_count := synced_count + 1;
    END LOOP;
    
    RETURN synced_count;
END;
$$ LANGUAGE plpgsql
SET search_path = public;

-- Trigger to automatically sync credits when user_credits table is updated
CREATE OR REPLACE FUNCTION trigger_sync_user_credits()
RETURNS TRIGGER AS $$
BEGIN
    -- Sync credits for the affected user
    PERFORM sync_user_credits_to_profile(NEW.user_id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = public;

-- Function to initialize user on signup with free plan
CREATE OR REPLACE FUNCTION initialize_user_on_signup(
    user_uuid UUID,
    user_email TEXT
)
RETURNS BOOLEAN AS $$
DECLARE
    free_plan_id UUID;
BEGIN
    -- Get the free plan ID
    SELECT id INTO free_plan_id
    FROM public.subscription_plans
    WHERE name = 'free' AND is_active = true
    LIMIT 1;
    
    -- Create user profile if it doesn't exist, or update referral_link if missing
    INSERT INTO public.user_profiles (
        user_id,
        referral_link,
        role,
        is_active,
        credits_total,
        credits_remaining
    ) VALUES (
        user_uuid,
        'https://promonexai.com/en/register?ref=' || encode(convert_to(COALESCE(user_email, ''), 'UTF8'), 'base64'), -- Generate referral_link as URL with base64 encoded email
        'user',
        true,
        5, -- Free tier credits (matches subscription_plans.monthly_credits for free plan)
        5
    )
    ON CONFLICT (user_id) DO UPDATE SET
        referral_link = COALESCE(user_profiles.referral_link, 'https://promonexai.com/en/register?ref=' || encode(convert_to(COALESCE(user_email, ''), 'UTF8'), 'base64'));
    
    -- Create user subscription for free plan if it doesn't exist
    IF free_plan_id IS NOT NULL THEN
        INSERT INTO public.user_subscriptions (
            user_id,
            plan_id,
            status,
            current_period_start,
            current_period_end,
            cancel_at_period_end
        ) VALUES (
            user_uuid,
            free_plan_id,
            'active',
            NOW(),
            NOW() + INTERVAL '1 year', -- 1 year from now
            false
        )
        ON CONFLICT (user_id) DO NOTHING;
    END IF;
    
    -- Initialize user credits if they don't exist
    INSERT INTO public.user_credits (
        user_id,
        total_credits,
        credits_remaining,
        subscription_credits_remaining,
        addon_credits_remaining
    ) VALUES (
        user_uuid,
        5, -- Free tier credits (matches subscription_plans.monthly_credits for free plan)
        5, -- Free tier credits (remaining = total for new users)
        5, -- Subscription credits = 5
        0  -- No addon credits initially
    )
    ON CONFLICT (user_id) DO NOTHING;
    
    -- Log the user registration activity
    INSERT INTO public.user_activities (
        user_id,
        action,
        resource_type,
        resource_id,
        details
    ) VALUES (
        user_uuid,
        'user_registered',
        'user',
        user_uuid,
        jsonb_build_object(
            'email', user_email,
            'plan', 'free',
            'signup_method', 'email'
        )
    );
    
    RETURN true;
END;
$$ LANGUAGE plpgsql
SET search_path = public;

-- Create trigger on user_credits table
DROP TRIGGER IF EXISTS sync_user_credits_trigger ON public.user_credits;
CREATE TRIGGER sync_user_credits_trigger
    AFTER INSERT OR UPDATE ON public.user_credits
    FOR EACH ROW
    EXECUTE FUNCTION trigger_sync_user_credits(); 

-- ============================================================================
-- Function: reset_subscription_credits_on_renewal (consolidated from migrations 31, 06)
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
            total_credits,
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
$$ LANGUAGE plpgsql
SET search_path = public;

-- Add comment to document the function
COMMENT ON FUNCTION reset_subscription_credits_on_renewal(UUID) IS 
'Resets subscription credits on billing cycle renewal. Sets subscription_credits_remaining to plan monthly_credits, expires all addon credits, and resets cycle tracking. Unused credits do NOT roll over.';

-- ============================================================================
-- MISSING FUNCTIONS FROM ORIGINAL DATABASE
-- ============================================================================

-- Function: ensure_target_language_case
-- Description: Trigger function to ensure target_language is stored as provided (case-sensitive)
CREATE OR REPLACE FUNCTION public.ensure_target_language_case()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    -- Ensure the target_language is stored exactly as provided (case-sensitive)
    NEW.target_language = NEW.target_language;
    RETURN NEW;
END;
$$;

-- Function: ensure_user_has_credits
-- Description: Ensures user has credits record (legacy - creates basic credits)
CREATE OR REPLACE FUNCTION public.ensure_user_has_credits(user_uuid UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    existing_credits_count INTEGER;
BEGIN
    -- Check if user already has credits
    SELECT COUNT(*) INTO existing_credits_count
    FROM public.user_credits
    WHERE user_id = user_uuid;
    
    -- If no credits exist, create them
    IF existing_credits_count = 0 THEN
        INSERT INTO public.user_credits (
            user_id,
            total_credits,
            used_credits
        ) VALUES (
            user_uuid,
            10, -- Free tier credits
            0
        );
        
        RETURN true;
    END IF;
    
    RETURN false;
END;
$$;

-- Function: ensure_user_has_free_plan
-- Description: Ensures user has free plan subscription
CREATE OR REPLACE FUNCTION public.ensure_user_has_free_plan(user_uuid UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    free_plan_id UUID;
    existing_subscription_count INTEGER;
    user_email TEXT;
BEGIN
    -- Get user email
    SELECT email INTO user_email
    FROM auth.users
    WHERE id = user_uuid;
    
    -- Get the free plan ID
    SELECT id INTO free_plan_id
    FROM public.subscription_plans
    WHERE name = 'free' AND is_active = true
    LIMIT 1;
    
    -- Check if user already has a subscription
    SELECT COUNT(*) INTO existing_subscription_count
    FROM public.user_subscriptions
    WHERE user_id = user_uuid AND status = 'active';
    
    -- If no active subscription and free plan exists, create one
    IF existing_subscription_count = 0 AND free_plan_id IS NOT NULL THEN
        INSERT INTO public.user_subscriptions (
            user_id,
            plan_id,
            status,
            current_period_start,
            current_period_end,
            cancel_at_period_end
        ) VALUES (
            user_uuid,
            free_plan_id,
            'active',
            NOW(),
            NOW() + INTERVAL '1 year',
            false
        );
        
        -- Log the activity
        INSERT INTO public.user_activities (
            user_id,
            action,
            resource_type,
            resource_id,
            details
        ) VALUES (
            user_uuid,
            'free_plan_assigned',
            'subscription',
            free_plan_id,
            jsonb_build_object(
                'email', user_email,
                'plan', 'free',
                'reason', 'migration_ensure_free_plan'
            )
        );
        
        RETURN true;
    END IF;
    
    RETURN false;
END;
$$;

-- Function: ensure_user_has_profile
-- Description: Ensures user has profile record
CREATE OR REPLACE FUNCTION public.ensure_user_has_profile(user_uuid UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    existing_profile_count INTEGER;
    user_email TEXT;
BEGIN
    -- Get user email
    SELECT email INTO user_email
    FROM auth.users
    WHERE id = user_uuid;
    
    -- Check if user already has a profile
    SELECT COUNT(*) INTO existing_profile_count
    FROM public.user_profiles
    WHERE user_id = user_uuid;
    
    -- If no profile exists, create one
    IF existing_profile_count = 0 THEN
        INSERT INTO public.user_profiles (
            user_id,
            email,
            role,
            is_active,
            credits_total,
            credits_remaining
        ) VALUES (
            user_uuid,
            user_email,
            'user',
            true,
            10, -- Free tier credits
            10
        );
        
        RETURN true;
    END IF;
    
    RETURN false;
END;
$$;

-- Function: get_all_active_plans
-- Description: Returns all active subscription plans
CREATE OR REPLACE FUNCTION public.get_all_active_plans()
RETURNS TABLE(
    id UUID,
    name TEXT,
    display_name TEXT,
    description TEXT,
    price_monthly DECIMAL,
    price_yearly DECIMAL,
    monthly_credits INTEGER,
    is_active BOOLEAN
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        sp.id,
        sp.name,
        sp.display_name,
        sp.description,
        sp.price_monthly,
        sp.price_yearly,
        sp.monthly_credits,
        sp.is_active
    FROM public.subscription_plans sp
    WHERE sp.is_active = true
    ORDER BY sp.price_monthly ASC;
END;
$$;

-- Function: get_plan_by_name
-- Description: Returns subscription plan by name
CREATE OR REPLACE FUNCTION public.get_plan_by_name(plan_name TEXT)
RETURNS TABLE(
    id UUID,
    name TEXT,
    display_name TEXT,
    description TEXT,
    price_monthly DECIMAL,
    price_yearly DECIMAL,
    monthly_credits INTEGER,
    is_active BOOLEAN
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        sp.id,
        sp.name,
        sp.display_name,
        sp.description,
        sp.price_monthly,
        sp.price_yearly,
        sp.monthly_credits,
        sp.is_active
    FROM public.subscription_plans sp
    WHERE sp.name = plan_name AND sp.is_active = true;
END;
$$;

-- Function: get_plan_credit_configs_with_actions
-- Description: Returns plan credit configs with action details
CREATE OR REPLACE FUNCTION public.get_plan_credit_configs_with_actions(plan_uuid UUID)
RETURNS TABLE(
    id UUID,
    plan_id UUID,
    action_id UUID,
    credit_cost INTEGER,
    monthly_limit INTEGER,
    daily_limit INTEGER,
    is_active BOOLEAN,
    action_name TEXT,
    display_name TEXT,
    description TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        pcc.id,
        pcc.plan_id,
        pcc.action_id,
        pcc.credit_cost,
        pcc.monthly_limit,
        pcc.daily_limit,
        pcc.is_active,
        ca.action_name,
        ca.display_name,
        ca.description
    FROM public.plan_credit_configs pcc
    JOIN public.credit_actions ca ON pcc.action_id = ca.id
    WHERE pcc.plan_id = plan_uuid AND pcc.is_active = true AND ca.is_active = true
    ORDER BY ca.action_name;
END;
$$;

-- Function: handle_new_user_signup
-- Description: Trigger function to handle new user signup (auth.users trigger)
CREATE OR REPLACE FUNCTION public.handle_new_user_signup()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    free_plan_id UUID;
    user_email TEXT;
BEGIN
    -- Get user email from the NEW record
    user_email := NEW.email;
    
    -- Get the free plan ID
    SELECT id INTO free_plan_id
    FROM public.subscription_plans
    WHERE name = 'free' AND is_active = true
    LIMIT 1;
    
    -- Create user profile if it doesn't exist
    INSERT INTO public.user_profiles (
        user_id,
        email,
        role,
        is_active,
        credits_total,
        credits_remaining
    ) VALUES (
        NEW.id,
        user_email,
        'user',
        true,
        10, -- Free tier credits
        10
    )
    ON CONFLICT (user_id) DO NOTHING;
    
    -- Create user subscription for free plan if it doesn't exist
    IF free_plan_id IS NOT NULL THEN
        INSERT INTO public.user_subscriptions (
            user_id,
            plan_id,
            status,
            current_period_start,
            current_period_end,
            cancel_at_period_end
        ) VALUES (
            NEW.id,
            free_plan_id,
            'active',
            NOW(),
            NOW() + INTERVAL '1 year', -- 1 year from now
            false
        )
        ON CONFLICT (user_id) DO NOTHING;
    END IF;
    
    -- Initialize user credits if they don't exist
    INSERT INTO public.user_credits (
        user_id,
        total_credits,
        used_credits
    ) VALUES (
        NEW.id,
        10, -- Free tier credits
        0
    )
    ON CONFLICT (user_id) DO NOTHING;
    
    -- Log the user registration activity
    INSERT INTO public.user_activities (
        user_id,
        action,
        resource_type,
        resource_id,
        details
    ) VALUES (
        NEW.id,
        'user_registered',
        'user',
        NEW.id,
        jsonb_build_object(
            'email', user_email,
            'plan', 'free',
            'signup_method', 'email'
        )
    );
    
    RETURN NEW;
END;
$$;

-- Add comments
COMMENT ON FUNCTION ensure_target_language_case() IS 'Trigger function to preserve target_language case sensitivity';
COMMENT ON FUNCTION ensure_user_has_credits(UUID) IS 'Legacy function - ensures user has credits record';
COMMENT ON FUNCTION ensure_user_has_free_plan(UUID) IS 'Ensures user has free plan subscription';
COMMENT ON FUNCTION ensure_user_has_profile(UUID) IS 'Ensures user has profile record';
COMMENT ON FUNCTION get_all_active_plans() IS 'Returns all active subscription plans';
COMMENT ON FUNCTION get_plan_by_name(TEXT) IS 'Returns subscription plan by name';
COMMENT ON FUNCTION get_plan_credit_configs_with_actions(UUID) IS 'Returns plan credit configs with action details';
COMMENT ON FUNCTION handle_new_user_signup() IS 'Trigger function for auth.users to initialize new user data'; 