-- Auto-Promo AI Credit System Schema
-- Credit packages, actions, configurations, and tracking

-- Credit packages for purchase
CREATE TABLE IF NOT EXISTS public.credit_packages (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name TEXT NOT NULL,
    credits INTEGER NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(plan_id, action_id)
);

-- User credit balances
CREATE TABLE IF NOT EXISTS public.user_credits (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    credits_total INTEGER NOT NULL DEFAULT 0,
    credits_remaining INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id)
);

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
    action_id UUID REFERENCES public.credit_actions(id) NOT NULL,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('deduction', 'addition', 'refund')),
    credits_amount INTEGER NOT NULL,
    reference_id UUID, -- ID of the related record (e.g., short_id, product_id)
    reference_type TEXT, -- Type of reference (e.g., 'short', 'product', 'purchase')
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

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

-- Triggers for updated_at columns
CREATE TRIGGER update_credit_actions_updated_at 
    BEFORE UPDATE ON public.credit_actions 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_plan_credit_configs_updated_at 
    BEFORE UPDATE ON public.plan_credit_configs 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_credits_updated_at 
    BEFORE UPDATE ON public.user_credits 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_credit_usage_tracking_updated_at 
    BEFORE UPDATE ON public.credit_usage_tracking 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

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

-- Add comment to document the new credit system
COMMENT ON TABLE public.credit_actions IS 'Credit costs: Audio=2, Video=25, Image=2, Scraping=1, Scenario=2, Upscale=5 per second';
COMMENT ON TABLE public.credit_adjustments IS 'Admin credit adjustments with audit trail and notification tracking'; 