-- Auto-Promo AI Initial Data
-- Default subscription plans and credit actions

-- Insert default subscription plans with credit configuration and 2024 pricing
INSERT INTO public.subscription_plans (name, display_name, description, price_monthly, price_yearly, monthly_credits, credit_config, watermark_enabled, is_active) VALUES
('free', 'Free Plan', 'Basic features with limited usage', 0, 0, 5, '{"video_merging": 1, "audio_generation": 1, "product_scraping": 1, "scenario_generation": 2, "video_scene_generation": 3}'::jsonb, true, true),
('starter', 'Starter Plan', 'Perfect for small businesses', 19.99, 199.99, 1000, '{"video_merging": 1, "audio_generation": 1, "product_scraping": 1, "scenario_generation": 2, "video_scene_generation": 3}'::jsonb, false, true),
('professional', 'Professional Plan', 'For growing businesses', 49.99, 499.99, 2500, '{"video_merging": 1, "audio_generation": 1, "product_scraping": 1, "scenario_generation": 2, "video_scene_generation": 3}'::jsonb, false, true),
('enterprise', 'Enterprise Plan', 'For large organizations', 99.99, 999.99, 5000, '{"video_merging": 1, "audio_generation": 1, "product_scraping": 1, "scenario_generation": 2, "video_scene_generation": 3}'::jsonb, false, true)
ON CONFLICT (name) DO UPDATE SET 
    price_monthly = EXCLUDED.price_monthly,
    price_yearly = EXCLUDED.price_yearly,
    monthly_credits = EXCLUDED.monthly_credits,
    credit_config = EXCLUDED.credit_config,
    watermark_enabled = EXCLUDED.watermark_enabled;

-- Insert default credit actions with 2024 credit costs
INSERT INTO public.credit_actions (action_name, display_name, description, base_credit_cost, is_active) VALUES
('scraping', 'Product Scraping', 'Scrape product information from e-commerce websites', 1, true),
('generate_scenario', 'Scenario Generation', 'Generate video scenarios based on product information', 2, true),
('generate_scene', 'Scene Generation', 'Generate individual video scenes', 25, true),
('generate_image', 'Image Generation', 'Generate AI images for video scenes using RunwayML', 2, true),
('generate_audio', 'Audio Generation', 'Generate audio narration for videos', 2, true),
('merge_video', 'Video Merging', 'Merge multiple scenes into final video', 0, true),
('upscale_video', 'Video Upscaling', 'Upscale video quality (5 credits per second)', 5, true)
ON CONFLICT (action_name) DO UPDATE SET
    base_credit_cost = EXCLUDED.base_credit_cost,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- Insert default plan credit configurations with 2024 limits
INSERT INTO public.plan_credit_configs (plan_id, action_id, credit_cost, monthly_limit, daily_limit, is_active)
SELECT 
    sp.id as plan_id,
    ca.id as action_id,
    ca.base_credit_cost as credit_cost,
    CASE 
        WHEN sp.name = 'free' THEN 
            CASE 
                WHEN ca.action_name = 'scraping' THEN 5  -- Free plan: 5 scrapings per month (uses all 5 credits)
                WHEN ca.action_name = 'generate_scenario' THEN 2  -- Free plan: 2 scenarios (costs 2 credits each = 4 credits, leaving 1 for scraping)
                WHEN ca.action_name = 'generate_scene' THEN 0  -- Not available on free plan
                WHEN ca.action_name = 'generate_image' THEN 0  -- Not available on free plan
                WHEN ca.action_name = 'generate_audio' THEN 0  -- Not available on free plan
                WHEN ca.action_name = 'merge_video' THEN 5  -- Video merging is free (0 credits) but limit to 5
                WHEN ca.action_name = 'upscale_video' THEN 0  -- Not available on free plan
                ELSE 0
            END
        WHEN sp.name = 'starter' THEN 
            CASE 
                WHEN ca.action_name = 'scraping' THEN 50
                WHEN ca.action_name = 'generate_scenario' THEN 10
                WHEN ca.action_name = 'generate_scene' THEN 40
                WHEN ca.action_name = 'generate_image' THEN 500
                WHEN ca.action_name = 'generate_audio' THEN 500
                WHEN ca.action_name = 'upscale_video' THEN 0  -- Not available on starter plan
                ELSE NULL
            END
        WHEN sp.name = 'professional' THEN 
            CASE 
                WHEN ca.action_name = 'scraping' THEN 100
                WHEN ca.action_name = 'generate_scenario' THEN 25
                WHEN ca.action_name = 'generate_scene' THEN 100
                WHEN ca.action_name = 'generate_image' THEN 1250
                WHEN ca.action_name = 'generate_audio' THEN 1250
                WHEN ca.action_name = 'upscale_video' THEN 100  -- Available on professional plan
                ELSE NULL
            END
        WHEN sp.name = 'enterprise' THEN 
            CASE 
                WHEN ca.action_name = 'scraping' THEN 200
                WHEN ca.action_name = 'generate_scenario' THEN 50
                WHEN ca.action_name = 'generate_scene' THEN 200
                WHEN ca.action_name = 'generate_image' THEN 2500
                WHEN ca.action_name = 'generate_audio' THEN 2500
                WHEN ca.action_name = 'upscale_video' THEN 500  -- Higher limit on enterprise plan
                ELSE NULL
            END
        ELSE NULL
    END as monthly_limit,
    CASE 
        WHEN sp.name = 'free' THEN 
            CASE 
                WHEN ca.action_name = 'scraping' THEN 5  -- Free plan: up to 5 scrapings per day (limited by credits)
                WHEN ca.action_name = 'generate_scenario' THEN 2  -- Free plan: up to 2 scenarios per day
                ELSE NULL
            END
        ELSE NULL
    END as daily_limit,
    true as is_active
FROM public.subscription_plans sp
CROSS JOIN public.credit_actions ca
WHERE sp.is_active = true AND ca.is_active = true
ON CONFLICT (plan_id, action_id) DO UPDATE SET
    credit_cost = EXCLUDED.credit_cost,
    monthly_limit = EXCLUDED.monthly_limit,
    daily_limit = EXCLUDED.daily_limit,
    is_active = EXCLUDED.is_active;

-- Insert default categories (parent categories)
INSERT INTO public.categories (id, name, description, sort_order) VALUES
('550e8400-e29b-41d4-a716-446655440001', 'Electronics', 'Electronic devices and accessories', 1),
('550e8400-e29b-41d4-a716-446655440002', 'Clothing & Fashion', 'Apparel, shoes, and fashion accessories', 2),
('550e8400-e29b-41d4-a716-446655440003', 'Home & Garden', 'Home improvement, furniture, and garden items', 3),
('550e8400-e29b-41d4-a716-446655440004', 'Sports & Outdoors', 'Sports equipment, fitness gear, and outdoor activities', 4),
('550e8400-e29b-41d4-a716-446655440005', 'Beauty & Personal Care', 'Cosmetics, skincare, and personal care products', 5),
('550e8400-e29b-41d4-a716-446655440006', 'Toys & Games', 'Toys, games, and entertainment items', 6),
('550e8400-e29b-41d4-a716-446655440007', 'Automotive', 'Car parts, accessories, and automotive products', 7),
('550e8400-e29b-41d4-a716-446655440008', 'Books & Media', 'Books, movies, music, and digital media', 8),
('550e8400-e29b-41d4-a716-446655440009', 'Food & Beverages', 'Snacks, drinks, and food products', 9),
('550e8400-e29b-41d4-a716-446655440010', 'Health & Wellness', 'Health supplements, medical devices, and wellness products', 10)
ON CONFLICT (name) DO NOTHING;

-- Insert parent categories
INSERT INTO public.categories (id, name, description, sort_order) VALUES
('550e8400-e29b-41d4-a716-446655440001', 'Electronics', 'All electronic items', 1),
('550e8400-e29b-41d4-a716-446655440002', 'Clothing & Fashion', 'All clothing and fashion items', 2),
('550e8400-e29b-41d4-a716-446655440003', 'Home & Garden', 'Home and garden products', 3),
('550e8400-e29b-41d4-a716-446655440004', 'Sports & Outdoors', 'Sports and outdoor gear', 4),
('550e8400-e29b-41d4-a716-446655440005', 'Beauty & Personal Care', 'Beauty and personal care products', 5)
ON CONFLICT (id) DO NOTHING;

-- Insert sub-categories
INSERT INTO public.categories (name, parent_id, description, sort_order) VALUES
-- Electronics sub-categories
('Laptops & Computers', '550e8400-e29b-41d4-a716-446655440001', 'Laptops, desktops, and computer accessories', 1),
('Smartphones & Phones', '550e8400-e29b-41d4-a716-446655440001', 'Mobile phones and phone accessories', 2),
('Tablets & E-readers', '550e8400-e29b-41d4-a716-446655440001', 'Tablets, e-readers, and related accessories', 3),
('Audio & Headphones', '550e8400-e29b-41d4-a716-446655440001', 'Speakers, headphones, and audio equipment', 4),
('Cameras & Photography', '550e8400-e29b-41d4-a716-446655440001', 'Cameras, lenses, and photography equipment', 5),

-- Clothing & Fashion sub-categories
('Men''s Clothing', '550e8400-e29b-41d4-a716-446655440002', 'Men''s apparel and accessories', 1),
('Women''s Clothing', '550e8400-e29b-41d4-a716-446655440002', 'Women''s apparel and accessories', 2),
('Kids'' Clothing', '550e8400-e29b-41d4-a716-446655440002', 'Children''s clothing and accessories', 3),
('Shoes & Footwear', '550e8400-e29b-41d4-a716-446655440002', 'Shoes, boots, and footwear for all ages', 4),
('Jewelry & Watches', '550e8400-e29b-41d4-a716-446655440002', 'Jewelry, watches, and fashion accessories', 5),

-- Home & Garden sub-categories
('Furniture', '550e8400-e29b-41d4-a716-446655440003', 'Home and office furniture', 1),
('Kitchen & Dining', '550e8400-e29b-41d4-a716-446655440003', 'Kitchen appliances and dining items', 2),
('Home Decor', '550e8400-e29b-41d4-a716-446655440003', 'Home decoration and accessories', 3),
('Garden & Outdoor', '550e8400-e29b-41d4-a716-446655440003', 'Garden tools and outdoor living items', 4),
('Lighting', '550e8400-e29b-41d4-a716-446655440003', 'Home and garden lighting solutions', 5),

-- Sports & Outdoors sub-categories
('Fitness & Exercise', '550e8400-e29b-41d4-a716-446655440004', 'Fitness equipment and exercise gear', 1),
('Team Sports', '550e8400-e29b-41d4-a716-446655440004', 'Equipment for team sports and activities', 2),
('Outdoor Recreation', '550e8400-e29b-41d4-a716-446655440004', 'Camping, hiking, and outdoor gear', 3),
('Water Sports', '550e8400-e29b-41d4-a716-446655440004', 'Swimming, surfing, and water activities', 4),
('Winter Sports', '550e8400-e29b-41d4-a716-446655440004', 'Skiing, snowboarding, and winter gear', 5),

-- Beauty & Personal Care sub-categories
('Skincare', '550e8400-e29b-41d4-a716-446655440005', 'Facial and body skincare products', 1),
('Makeup & Cosmetics', '550e8400-e29b-41d4-a716-446655440005', 'Makeup, cosmetics, and beauty tools', 2),
('Hair Care', '550e8400-e29b-41d4-a716-446655440005', 'Hair care products and styling tools', 3),
('Fragrances', '550e8400-e29b-41d4-a716-446655440005', 'Perfumes, colognes, and body sprays', 4),
('Personal Hygiene', '550e8400-e29b-41d4-a716-446655440005', 'Personal care and hygiene products', 5)
ON CONFLICT (name) DO NOTHING;
