-- Auto-Promo AI Subscription System Schema
-- Subscription plans and user subscriptions management

-- Subscription plans
CREATE TABLE IF NOT EXISTS public.subscription_plans (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT,
    price_monthly NUMERIC,
    price_yearly NUMERIC,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    monthly_credits INTEGER NOT NULL DEFAULT 0,
    credit_config JSONB NOT NULL DEFAULT '{"video_merging": 1, "audio_generation": 1, "product_scraping": 1, "scenario_generation": 2, "video_scene_generation": 3}'::jsonb,
    watermark_enabled BOOLEAN DEFAULT false
);

-- Row Level Security for subscription_plans table
-- Enable RLS on subscription_plans (from migration 31-fix-subscription-plans-rls.sql)
ALTER TABLE public.subscription_plans ENABLE ROW LEVEL SECURITY;

-- RLS Policies for subscription_plans
-- Allow authenticated users to read subscription plans (they need to see available plans)
CREATE POLICY "Authenticated users can view subscription plans" ON public.subscription_plans
FOR SELECT
USING (auth.uid() IS NOT NULL);

-- Allow admins to manage subscription plans
CREATE POLICY "Admins can manage subscription plans" ON public.subscription_plans
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

-- Grant permissions for subscription_plans
GRANT SELECT ON public.subscription_plans TO authenticated;
GRANT ALL ON public.subscription_plans TO service_role;

-- Add comment
COMMENT ON TABLE public.subscription_plans IS 'Subscription plan definitions (Free, Premium, etc.). RLS enabled: authenticated users can read to view available plans, only admins can modify.';

-- User subscriptions
CREATE TABLE IF NOT EXISTS public.user_subscriptions (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    plan_id UUID REFERENCES public.subscription_plans(id) NOT NULL,
    stripe_subscription_id TEXT UNIQUE,
    stripe_customer_id TEXT,
    status TEXT NOT NULL DEFAULT 'active', -- active, canceled, past_due, etc.
    current_period_start TIMESTAMP WITH TIME ZONE,
    current_period_end TIMESTAMP WITH TIME ZONE,
    cancel_at_period_end BOOLEAN DEFAULT false,
    payment_method_last4 TEXT,
    payment_method_brand TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    billing_cycle TEXT NOT NULL DEFAULT 'monthly' CHECK (billing_cycle IN ('monthly', 'yearly')),
    downgrade_to_plan_id UUID REFERENCES public.subscription_plans(id),
    downgrade_scheduled_at TIMESTAMP WITH TIME ZONE,
    payment_failed_at TIMESTAMP WITH TIME ZONE,
    grace_period_ends_at TIMESTAMP WITH TIME ZONE,
    rendering_blocked BOOLEAN NOT NULL DEFAULT false
);

-- Indexes for subscription tables
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_user_id ON public.user_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_status ON public.user_subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_plan_id ON public.user_subscriptions(plan_id);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_billing_cycle ON public.user_subscriptions(billing_cycle);

-- Add comment to document the credit system
COMMENT ON COLUMN public.subscription_plans.monthly_credits IS 'Monthly credit allocation for this subscription plan';
COMMENT ON COLUMN public.subscription_plans.credit_config IS 'Credit costs per action for this plan (overrides base costs from credit_actions)';
COMMENT ON COLUMN public.subscription_plans.watermark_enabled IS 'Whether this plan includes watermarks on generated videos';
COMMENT ON TABLE public.subscription_plans IS 'Monthly credits: Free=5, Starter=1000, Professional=2500, Enterprise=5000'; 