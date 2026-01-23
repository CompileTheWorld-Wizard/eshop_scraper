-- Auto-Promo AI Credit System Schema
-- Credit packages, actions, configurations, and tracking

-- Credit packages for purchase
CREATE TABLE IF NOT EXISTS public.credit_packages (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    credits INTEGER NOT NULL,
    price NUMERIC NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Row Level Security for credit_packages table
-- Enable RLS on credit_packages (from migration 29-fix-credit-packages-rls.sql)
ALTER TABLE public.credit_packages ENABLE ROW LEVEL SECURITY;

-- RLS Policies for credit_packages
-- Allow authenticated users to read credit packages (they need to see available packages)
CREATE POLICY "Authenticated users can view credit packages" ON public.credit_packages
FOR SELECT
USING (auth.uid() IS NOT NULL);

-- Allow admins to manage credit packages
CREATE POLICY "Admins can manage credit packages" ON public.credit_packages
FOR ALL
USING (
    EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE user_profiles.user_id = auth.uid()
        AND user_profiles.role = 'admin'
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE user_profiles.user_id = auth.uid()
        AND user_profiles.role = 'admin'
    )
);

-- Grant permissions for credit_packages
GRANT SELECT ON public.credit_packages TO authenticated;
GRANT ALL ON public.credit_packages TO service_role;

-- Add comment
COMMENT ON TABLE public.credit_packages IS 'Credit packages available for purchase. RLS enabled: authenticated users can read, only admins can modify. Pricing reference data.';

-- Credit action types (configurable by admin)
CREATE TABLE IF NOT EXISTS public.credit_actions (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    action_name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT,
    base_credit_cost INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Plan-specific credit configurations
CREATE TABLE IF NOT EXISTS public.plan_credit_configs (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    plan_id UUID REFERENCES public.subscription_plans(id) ON DELETE CASCADE NOT NULL,
    action_id UUID REFERENCES public.credit_actions(id) ON DELETE CASCADE NOT NULL,
    credit_cost INTEGER NOT NULL DEFAULT 1,
    monthly_limit INTEGER, -- NULL means unlimited
    daily_limit INTEGER, -- NULL means unlimited
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(plan_id, action_id)
);

-- Row Level Security for plan_credit_configs table
-- Enable RLS on plan_credit_configs (from migration 30-fix-plan-credit-configs-rls.sql)
ALTER TABLE public.plan_credit_configs ENABLE ROW LEVEL SECURITY;

-- RLS Policies for plan_credit_configs
-- Allow authenticated users to read plan configs (for plan transparency)
CREATE POLICY "Authenticated users can view plan credit configs" ON public.plan_credit_configs
FOR SELECT
USING (auth.uid() IS NOT NULL);

-- Allow admins to manage plan credit configs
CREATE POLICY "Admins can manage plan credit configs" ON public.plan_credit_configs
FOR ALL
USING (
    EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE user_profiles.user_id = auth.uid()
        AND user_profiles.role = 'admin'
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE user_profiles.user_id = auth.uid()
        AND user_profiles.role = 'admin'
    )
);

-- Grant permissions for plan_credit_configs
GRANT SELECT ON public.plan_credit_configs TO authenticated;
GRANT ALL ON public.plan_credit_configs TO service_role;

-- Add comment
COMMENT ON TABLE public.plan_credit_configs IS 'Plan-specific credit configurations (costs and limits per action per plan). RLS enabled: authenticated users can read for transparency, only admins can modify.';

-- User credit balances
CREATE TABLE IF NOT EXISTS public.user_credits (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    total_credits INTEGER DEFAULT 0,
    start_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_reset_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    reset_frequency TEXT DEFAULT 'monthly',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    cycle_used_credits INTEGER NOT NULL DEFAULT 0,
    cycle_start_at TIMESTAMP WITH TIME ZONE,
    credits_remaining INTEGER NOT NULL DEFAULT 0,
    subscription_credits_remaining INTEGER NOT NULL DEFAULT 0,
    addon_credits_remaining INTEGER NOT NULL DEFAULT 0,
    last_billing_cycle_reset TIMESTAMP WITH TIME ZONE,
    UNIQUE(user_id)
);

-- Add comments for user_credits columns
COMMENT ON COLUMN public.user_credits.credits_remaining IS 'Remaining credits available to the user (stored directly, not calculated). Equals subscription_credits_remaining + addon_credits_remaining.';
COMMENT ON COLUMN public.user_credits.cycle_used_credits IS 'Total subscription-plan credits consumed in the current billing cycle. Used to enforce monthly_credits per cycle without rollover.';
COMMENT ON COLUMN public.user_credits.cycle_start_at IS 'Billing cycle start timestamp this cycle_used_credits value belongs to (mirrors user_subscriptions.current_period_start).';
COMMENT ON COLUMN public.user_credits.subscription_credits_remaining IS 'Credits from subscription plan that reset every billing cycle. These do NOT roll over.';
COMMENT ON COLUMN public.user_credits.addon_credits_remaining IS 'Credits from add-on purchases that expire at the end of current billing cycle. These do NOT roll over.';
COMMENT ON COLUMN public.user_credits.last_billing_cycle_reset IS 'Timestamp when credits were last reset on billing cycle renewal. Used for idempotency checks.';

-- Ensure credits_remaining column exists (migration 20)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'user_credits' 
        AND column_name = 'credits_remaining'
    ) THEN
        ALTER TABLE public.user_credits
        ADD COLUMN credits_remaining INTEGER NOT NULL DEFAULT 0;
        
        -- Migrate existing data if needed
        UPDATE public.user_credits
        SET credits_remaining = COALESCE(total_credits, 0)
        WHERE credits_remaining = 0;
    END IF;
END $$;

-- Remove deprecated used_credits column if it exists (migration 24)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'user_credits' 
        AND column_name = 'used_credits'
    ) THEN
        ALTER TABLE public.user_credits
        DROP COLUMN used_credits;
    END IF;
END $$;

-- Credit usage tracking (for analytics and limits)
CREATE TABLE IF NOT EXISTS public.credit_usage_tracking (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    action_id UUID REFERENCES public.credit_actions(id) NOT NULL,
    usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
    usage_month TEXT NOT NULL DEFAULT TO_CHAR(CURRENT_DATE, 'YYYY-MM'),
    usage_count INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, action_id, usage_date)
);

-- Credit transactions (audit trail)
CREATE TABLE IF NOT EXISTS public.credit_transactions (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    action_id UUID REFERENCES public.credit_actions(id),
    description TEXT,
    reference_id TEXT,
    reference_type TEXT,
    balance_after INTEGER NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    transaction_type TEXT NOT NULL DEFAULT 'deduction' CHECK (transaction_type IN ('deduction', 'addition', 'refund')),
    credits_amount INTEGER NOT NULL
);

-- Remove redundant columns if they exist (migration 22)
DO $$
BEGIN
    -- Drop NOT NULL constraints first if they exist
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'credit_transactions' 
        AND column_name = 'type'
    ) THEN
        ALTER TABLE public.credit_transactions ALTER COLUMN type DROP NOT NULL;
        ALTER TABLE public.credit_transactions DROP COLUMN type;
    END IF;
    
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'credit_transactions' 
        AND column_name = 'amount'
    ) THEN
        ALTER TABLE public.credit_transactions ALTER COLUMN amount DROP NOT NULL;
        ALTER TABLE public.credit_transactions DROP COLUMN amount;
    END IF;
END $$;

-- Indexes for credit system tables
CREATE INDEX IF NOT EXISTS idx_user_credits_user_id ON public.user_credits(user_id);
CREATE INDEX IF NOT EXISTS idx_credit_transactions_user_id ON public.credit_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_credit_transactions_created_at ON public.credit_transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_credit_transactions_action_id ON public.credit_transactions(action_id);
CREATE INDEX IF NOT EXISTS idx_credit_actions_name ON public.credit_actions(action_name);
CREATE INDEX IF NOT EXISTS idx_plan_credit_configs_plan_id ON public.plan_credit_configs(plan_id);
CREATE INDEX IF NOT EXISTS idx_plan_credit_configs_action_id ON public.plan_credit_configs(action_id);
CREATE INDEX IF NOT EXISTS idx_credit_usage_tracking_user_id ON public.credit_usage_tracking(user_id);
CREATE INDEX IF NOT EXISTS idx_credit_usage_tracking_action_id ON public.credit_usage_tracking(action_id);
CREATE INDEX IF NOT EXISTS idx_credit_usage_tracking_date ON public.credit_usage_tracking(usage_date);
CREATE INDEX IF NOT EXISTS idx_credit_usage_tracking_month ON public.credit_usage_tracking(usage_month);

-- Credit adjustments (admin adjustments with audit trail)
CREATE TABLE IF NOT EXISTS public.credit_adjustments (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    admin_id UUID REFERENCES auth.users(id) ON DELETE SET NULL NOT NULL,
    adjustment_amount INTEGER NOT NULL, -- Can be positive or negative
    reason TEXT, -- Optional reason for adjustment
    description TEXT, -- Optional detailed description
    notification_sent BOOLEAN DEFAULT false,
    notification_sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for credit_adjustments table
CREATE INDEX IF NOT EXISTS idx_credit_adjustments_user_id ON public.credit_adjustments(user_id);
CREATE INDEX IF NOT EXISTS idx_credit_adjustments_admin_id ON public.credit_adjustments(admin_id);
CREATE INDEX IF NOT EXISTS idx_credit_adjustments_created_at ON public.credit_adjustments(created_at);
CREATE INDEX IF NOT EXISTS idx_credit_adjustments_notification_sent ON public.credit_adjustments(notification_sent);

-- Add-on credits tracking with expiration
CREATE TABLE IF NOT EXISTS public.addon_credits (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    credits_amount INTEGER NOT NULL,
    credits_remaining INTEGER NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    purchase_transaction_id UUID REFERENCES public.credit_transactions(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE public.addon_credits IS 'Tracks individual add-on credit purchases. Credits expire at the end of the current billing cycle and do NOT roll over.';
COMMENT ON COLUMN public.addon_credits.expires_at IS 'Expiration date set to user''s current_period_end at time of purchase. Credits expire at this date.';
COMMENT ON COLUMN public.addon_credits.credits_remaining IS 'Remaining credits from this specific add-on purchase. Used for FIFO expiration tracking.';

-- Indexes for addon_credits table
CREATE INDEX IF NOT EXISTS idx_addon_credits_user_id ON public.addon_credits(user_id);
CREATE INDEX IF NOT EXISTS idx_addon_credits_expires_at ON public.addon_credits(expires_at);
CREATE INDEX IF NOT EXISTS idx_addon_credits_user_expires ON public.addon_credits(user_id, expires_at) 
WHERE credits_remaining > 0;

-- Index for user_credits last_billing_cycle_reset (from migration 28)
CREATE INDEX IF NOT EXISTS idx_user_credits_last_billing_cycle_reset 
ON public.user_credits(last_billing_cycle_reset) 
WHERE last_billing_cycle_reset IS NOT NULL;

-- Row Level Security for credit_actions table
-- Enable RLS on credit_actions (from migration 28-fix-credit-actions-rls.sql)
ALTER TABLE public.credit_actions ENABLE ROW LEVEL SECURITY;

-- RLS Policies for credit_actions
-- Allow authenticated users to read credit actions (they need to see costs)
CREATE POLICY "Authenticated users can view credit actions" ON public.credit_actions
FOR SELECT
USING (auth.uid() IS NOT NULL);

-- Allow admins to manage credit actions
CREATE POLICY "Admins can manage credit actions" ON public.credit_actions
FOR ALL
USING (
    EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE user_profiles.user_id = auth.uid()
        AND user_profiles.role = 'admin'
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE user_profiles.user_id = auth.uid()
        AND user_profiles.role = 'admin'
    )
);

-- Grant permissions for credit_actions
GRANT SELECT ON public.credit_actions TO authenticated;
GRANT ALL ON public.credit_actions TO service_role;

-- Add comments to document the credit system
COMMENT ON TABLE public.credit_actions IS 'Credit action types with costs. RLS enabled: authenticated users can read, only admins can modify. Reference data for credit system.';
COMMENT ON TABLE public.credit_adjustments IS 'Admin credit adjustments with audit trail and notification tracking';
COMMENT ON TABLE public.credit_usage_tracking IS 'Tracks credit usage per action for daily/monthly limits and analytics'; 