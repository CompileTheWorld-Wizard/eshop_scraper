-- Auto-Promo AI Database Functions
-- Utility functions for the application

-- Function to update updated_at column automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

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
$$ LANGUAGE plpgsql;

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
$$ LANGUAGE plpgsql;

-- Function to check if user can perform an action
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
BEGIN
    -- Get user's current credits
    SELECT COALESCE(uc.credits_remaining, 0) INTO user_credits
    FROM public.user_credits uc
    WHERE uc.user_id = user_uuid;
    
    -- Get action cost and limits
    SELECT 
        pcc.credit_cost,
        pcc.monthly_limit,
        pcc.daily_limit,
        us.plan_id
    INTO action_cost, monthly_limit_val, daily_limit_val, user_plan_id
    FROM public.credit_actions ca
    LEFT JOIN public.plan_credit_configs pcc ON ca.id = pcc.action_id
    LEFT JOIN public.user_subscriptions us ON pcc.plan_id = us.plan_id
    WHERE ca.action_name = action_name
    AND us.user_id = user_uuid
    AND us.status = 'active';
    
    -- If no plan found, check if user has enough credits
    IF user_plan_id IS NULL THEN
        SELECT ca.base_credit_cost INTO action_cost
        FROM public.credit_actions ca
        WHERE ca.action_name = action_name;
        
        RETURN QUERY SELECT 
            user_credits >= action_cost as can_perform,
            CASE 
                WHEN user_credits < action_cost THEN 'Insufficient credits'
                ELSE 'Can perform action'
            END as reason,
            user_credits as current_credits,
            action_cost as required_credits,
            NULL as monthly_limit,
            NULL as daily_limit,
            NULL as monthly_used,
            NULL as daily_used;
        RETURN;
    END IF;
    
    -- Get usage counts
    SELECT COALESCE(SUM(usage_count), 0) INTO monthly_used_val
    FROM public.credit_usage_tracking cut
    JOIN public.credit_actions ca ON cut.action_id = ca.id
    WHERE cut.user_id = user_uuid
    AND ca.action_name = action_name
    AND cut.usage_month = TO_CHAR(CURRENT_DATE, 'YYYY-MM');
    
    SELECT COALESCE(SUM(usage_count), 0) INTO daily_used_val
    FROM public.credit_usage_tracking cut
    JOIN public.credit_actions ca ON cut.action_id = ca.id
    WHERE cut.user_id = user_uuid
    AND ca.action_name = action_name
    AND cut.usage_date = CURRENT_DATE;
    
    -- Check if user can perform action
    RETURN QUERY SELECT 
        user_credits >= action_cost 
        AND (monthly_limit_val IS NULL OR monthly_used_val < monthly_limit_val)
        AND (daily_limit_val IS NULL OR daily_used_val < daily_limit_val) as can_perform,
        CASE 
            WHEN user_credits < action_cost THEN 'Insufficient credits'
            WHEN monthly_limit_val IS NOT NULL AND monthly_used_val >= monthly_limit_val THEN 'Monthly limit reached'
            WHEN daily_limit_val IS NOT NULL AND daily_used_val >= daily_limit_val THEN 'Daily limit reached'
            ELSE 'Can perform action'
        END as reason,
        user_credits as current_credits,
        action_cost as required_credits,
        monthly_limit_val as monthly_limit,
        daily_limit_val as daily_limit,
        monthly_used_val as monthly_used,
        daily_used_val as daily_used;
END;
$$ LANGUAGE plpgsql;

-- Function to deduct user credits
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
BEGIN
    -- Check if user can perform action
    SELECT can_perform, reason INTO can_perform_val, reason_val
    FROM can_perform_action(user_uuid, action_name);
    
    IF NOT can_perform_val THEN
        RAISE EXCEPTION 'Cannot perform action: %', reason_val;
    END IF;
    
    -- Get action details
    SELECT id, base_credit_cost INTO action_id_val, credit_cost_val
    FROM public.credit_actions
    WHERE action_name = action_name;
    
    -- Deduct credits from user_credits table
    UPDATE public.user_credits
    SET 
        credits_remaining = credits_remaining - credit_cost_val,
        updated_at = NOW()
    WHERE user_id = user_uuid;
    
    -- If no row was updated, create one
    IF NOT FOUND THEN
        INSERT INTO public.user_credits (user_id, credits_total, credits_remaining)
        VALUES (user_uuid, 0, 0);
        
        UPDATE public.user_credits
        SET 
            credits_remaining = credits_remaining - credit_cost_val,
            updated_at = NOW()
        WHERE user_id = user_uuid;
    END IF;
    
    -- Record transaction
    INSERT INTO public.credit_transactions (
        user_id, action_id, type, transaction_type, credits_amount, 
        reference_id, reference_type, description
    ) VALUES (
        user_uuid, action_id_val, action_name, 'deduction', credit_cost_val,
        reference_id, reference_type, description
    );
    
    -- Update usage tracking
    INSERT INTO public.credit_usage_tracking (
        user_id, action_id, usage_date, usage_month, usage_count
    ) VALUES (
        user_uuid, action_id_val, CURRENT_DATE, TO_CHAR(CURRENT_DATE, 'YYYY-MM'), 1
    )
    ON CONFLICT (user_id, action_id, usage_date)
    DO UPDATE SET usage_count = credit_usage_tracking.usage_count + 1;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function to add user credits
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
    
    -- Record transaction
    INSERT INTO public.credit_transactions (
        user_id, action_id, type, transaction_type, credits_amount, 
        reference_id, reference_type, description
    ) VALUES (
        user_uuid, action_id_val, action_name, 'addition', credits_amount,
        reference_id, reference_type, description
    );
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function to increment video views
CREATE OR REPLACE FUNCTION increment_video_views(video_uuid UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE public.shorts
    SET views = views + 1
    WHERE id = video_uuid;
END;
$$ LANGUAGE plpgsql;

-- Function to increment video downloads
CREATE OR REPLACE FUNCTION increment_video_downloads(video_uuid UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE public.shorts
    SET downloads = downloads + 1
    WHERE id = video_uuid;
END;
$$ LANGUAGE plpgsql;

-- Function to sync user credits to profile
CREATE OR REPLACE FUNCTION sync_user_credits_to_profile(user_uuid UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE public.user_profiles
    SET 
        credits_total = COALESCE(uc.credits_total, 0),
        credits_remaining = COALESCE(uc.credits_remaining, 0),
        updated_at = NOW()
    FROM public.user_credits uc
    WHERE public.user_profiles.user_id = user_uuid
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
$$ LANGUAGE plpgsql;

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
$$ LANGUAGE plpgsql;

-- Trigger to automatically sync credits when user_credits table is updated
CREATE OR REPLACE FUNCTION trigger_sync_user_credits()
RETURNS TRIGGER AS $$
BEGIN
    -- Sync credits for the affected user
    PERFORM sync_user_credits_to_profile(NEW.user_id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

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
        10, -- Free tier credits
        10
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
        credits_remaining
    ) VALUES (
        user_uuid,
        50, -- Free tier credits
        50  -- Free tier credits (remaining = total for new users)
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
$$ LANGUAGE plpgsql;

-- Create trigger on user_credits table
DROP TRIGGER IF EXISTS sync_user_credits_trigger ON public.user_credits;
CREATE TRIGGER sync_user_credits_trigger
    AFTER INSERT OR UPDATE ON public.user_credits
    FOR EACH ROW
    EXECUTE FUNCTION trigger_sync_user_credits(); 