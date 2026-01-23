-- Migration: CMS Dashboard Pages Content
-- Description: Inserts dashboard, subscription, billing history, and settings page content
-- Date: 2024-01-14
-- Note: This data is hardcoded in migrate-cms-initial-data.ts script

DO $$
DECLARE
    v_dashboard_page_id UUID;
    v_subscription_page_id UUID;
    v_billing_page_id UUID;
    v_settings_page_id UUID;
    v_section_id UUID;
BEGIN
    RAISE NOTICE 'Creating dashboard pages CMS structure...';

    -- ============================
    -- Dashboard Page
    -- ============================
    INSERT INTO public.cms_pages (slug, name, description, is_active, metadata)
    VALUES (
        'dashboard',
        'User Dashboard',
        'Main user dashboard page',
        true,
        '{}'::jsonb
    )
    ON CONFLICT (slug) DO UPDATE SET
        updated_at = NOW()
    RETURNING id INTO v_dashboard_page_id;

    -- Dashboard Header Section
    SELECT id INTO v_section_id FROM public.cms_sections WHERE page_id = v_dashboard_page_id AND type = 'header' AND name = 'Page Header';
    IF v_section_id IS NULL THEN
        INSERT INTO public.cms_sections (page_id, type, name, order_index, is_visible, config)
        VALUES (v_dashboard_page_id, 'header', 'Page Header', 0, true, '{}'::jsonb)
        RETURNING id INTO v_section_id;
    ELSE
        UPDATE public.cms_sections SET updated_at = NOW() WHERE id = v_section_id;
    END IF;

    INSERT INTO public.cms_content_blocks (section_id, key, content, content_type, order_index)
    VALUES
        (v_section_id, 'title', '{"text": "Welcome back, {name}!"}'::jsonb, 'text', 0),
        (v_section_id, 'description', '{"text": "Manage your videos and account"}'::jsonb, 'text', 1)
    ON CONFLICT (section_id, key) DO UPDATE SET
        content = EXCLUDED.content,
        updated_at = NOW();

    RAISE NOTICE 'Created dashboard page with header section';

    -- ============================
    -- Subscription Page
    -- ============================
    INSERT INTO public.cms_pages (slug, name, description, is_active, metadata)
    VALUES (
        'subscription',
        'Subscription Page',
        'Subscription and billing management page',
        true,
        '{}'::jsonb
    )
    ON CONFLICT (slug) DO UPDATE SET
        updated_at = NOW()
    RETURNING id INTO v_subscription_page_id;

    -- Subscription Header Section
    SELECT id INTO v_section_id FROM public.cms_sections WHERE page_id = v_subscription_page_id AND type = 'header' AND name = 'Page Header';
    IF v_section_id IS NULL THEN
        INSERT INTO public.cms_sections (page_id, type, name, order_index, is_visible, config)
        VALUES (v_subscription_page_id, 'header', 'Page Header', 0, true, '{}'::jsonb)
        RETURNING id INTO v_section_id;
    ELSE
        UPDATE public.cms_sections SET updated_at = NOW() WHERE id = v_section_id;
    END IF;

    INSERT INTO public.cms_content_blocks (section_id, key, content, content_type, order_index)
    VALUES
        (v_section_id, 'title', '{"text": "Subscription & Billing"}'::jsonb, 'text', 0),
        (v_section_id, 'subtitle', '{"text": "Manage your subscription plan and billing"}'::jsonb, 'text', 1)
    ON CONFLICT (section_id, key) DO UPDATE SET
        content = EXCLUDED.content,
        updated_at = NOW();

    -- Subscription Info Section
    SELECT id INTO v_section_id FROM public.cms_sections WHERE page_id = v_subscription_page_id AND type = 'info' AND name = 'Billing Support Section';
    IF v_section_id IS NULL THEN
        INSERT INTO public.cms_sections (page_id, type, name, order_index, is_visible, config)
        VALUES (v_subscription_page_id, 'info', 'Billing Support Section', 1, true, '{}'::jsonb)
        RETURNING id INTO v_section_id;
    ELSE
        UPDATE public.cms_sections SET updated_at = NOW() WHERE id = v_section_id;
    END IF;

    INSERT INTO public.cms_content_blocks (section_id, key, content, content_type, order_index)
    VALUES
        (v_section_id, 'title', '{"text": "Billing & Support"}'::jsonb, 'text', 0),
        (v_section_id, 'description', '{"text": "Need help with billing or have questions?"}'::jsonb, 'text', 1),
        (v_section_id, 'billingSupportText', '{"text": "For billing inquiries, subscription changes, or payment issues, please contact our billing support team."}'::jsonb, 'text', 2),
        (v_section_id, 'technicalSupportText', '{"text": "For technical issues, feature requests, or general questions about using the platform, our technical support team is here to help."}'::jsonb, 'text', 3)
    ON CONFLICT (section_id, key) DO UPDATE SET
        content = EXCLUDED.content,
        updated_at = NOW();

    RAISE NOTICE 'Created subscription page with 2 sections';

    -- ============================
    -- Billing History Page
    -- ============================
    INSERT INTO public.cms_pages (slug, name, description, is_active, metadata)
    VALUES (
        'billing-history',
        'Billing History',
        'Billing history and transaction records',
        true,
        '{}'::jsonb
    )
    ON CONFLICT (slug) DO UPDATE SET
        updated_at = NOW()
    RETURNING id INTO v_billing_page_id;

    -- Billing History Header Section
    SELECT id INTO v_section_id FROM public.cms_sections WHERE page_id = v_billing_page_id AND type = 'header' AND name = 'Page Header';
    IF v_section_id IS NULL THEN
        INSERT INTO public.cms_sections (page_id, type, name, order_index, is_visible, config)
        VALUES (v_billing_page_id, 'header', 'Page Header', 0, true, '{}'::jsonb)
        RETURNING id INTO v_section_id;
    ELSE
        UPDATE public.cms_sections SET updated_at = NOW() WHERE id = v_section_id;
    END IF;

    INSERT INTO public.cms_content_blocks (section_id, key, content, content_type, order_index)
    VALUES
        (v_section_id, 'title', '{"text": "Billing History"}'::jsonb, 'text', 0),
        (v_section_id, 'subtitle', '{"text": "View your payment history and transactions"}'::jsonb, 'text', 1)
    ON CONFLICT (section_id, key) DO UPDATE SET
        content = EXCLUDED.content,
        updated_at = NOW();

    RAISE NOTICE 'Created billing history page with header section';

    -- ============================
    -- Settings Page
    -- ============================
    INSERT INTO public.cms_pages (slug, name, description, is_active, metadata)
    VALUES (
        'settings',
        'Settings',
        'User settings and preferences',
        true,
        '{}'::jsonb
    )
    ON CONFLICT (slug) DO UPDATE SET
        updated_at = NOW()
    RETURNING id INTO v_settings_page_id;

    -- Settings Header Section
    SELECT id INTO v_section_id FROM public.cms_sections WHERE page_id = v_settings_page_id AND type = 'header' AND name = 'Page Header';
    IF v_section_id IS NULL THEN
        INSERT INTO public.cms_sections (page_id, type, name, order_index, is_visible, config)
        VALUES (v_settings_page_id, 'header', 'Page Header', 0, true, '{}'::jsonb)
        RETURNING id INTO v_section_id;
    ELSE
        UPDATE public.cms_sections SET updated_at = NOW() WHERE id = v_section_id;
    END IF;

    INSERT INTO public.cms_content_blocks (section_id, key, content, content_type, order_index)
    VALUES
        (v_section_id, 'title', '{"text": "Settings"}'::jsonb, 'text', 0),
        (v_section_id, 'subtitle', '{"text": "Manage your account settings and preferences"}'::jsonb, 'text', 1)
    ON CONFLICT (section_id, key) DO UPDATE SET
        content = EXCLUDED.content,
        updated_at = NOW();

    RAISE NOTICE 'Created settings page with header section';

    RAISE NOTICE '✅ Dashboard pages CMS content migration completed successfully!';
    RAISE NOTICE 'Created 4 pages: dashboard, subscription, billing-history, settings';
END $$;
