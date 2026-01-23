-- Migration: CMS Legal Documents
-- Description: Inserts legal documents (Terms, Privacy, DPA, Cookies) from i18n and hardcoded content
-- Date: 2024-01-14
-- Note: This ensures all legal documents are included when cloning database
-- These documents are based on src/i18n/locales/en.json and migrate-cms-initial-data.ts

DO $$
BEGIN
    RAISE NOTICE 'Creating legal documents...';

    -- ============================
    -- Terms of Service
    -- ============================
    INSERT INTO public.cms_legal_documents (
        document_type,
        locale,
        version,
        content,
        effective_date,
        is_published,
        created_by
    )
    VALUES (
        'terms',
        'en',
        1,
        '<h1>PromoNexAi Terms of Service</h1>
<p><strong>Effective Date:</strong> October 1, 2025</p>

<section>
  <h2>1. Introduction</h2>
  <p>These Terms of Service ("Terms") govern your access and use of PromoNexAi B.V.''s services. By creating an account or using our platform, you agree to these Terms.</p>
</section>

<section>
  <h2>2. Company Information</h2>
  <p><strong>PromoNexAi B.V.</strong></p>
  <p>Herengracht 123, 1015 BS Amsterdam, The Netherlands</p>
  <p>Chamber of Commerce (KvK): 87654321</p>
  <p>VAT: NL123456789B01</p>
  <p>Email: info@promonexai.com</p>
</section>

<section>
  <h2>3. Services</h2>
  <p>PromoNexAi provides an AI-powered marketing video generation platform, using Google Gemini, ElevenLabs, and Runway.</p>
  <p>After a video has been fully generated, PromoNexAi also provides the option to directly upload or share the video to supported third-party platforms (including TikTok, Instagram, YouTube, and X) with a single click.</p>
</section>

<section>
  <h2>4. User Responsibilities</h2>
  <p>Users are solely responsible for:</p>
  <ul>
    <li>Ensuring product URLs are lawful and belong to their own products.</li>
    <li>Confirming they have read the scraping warning before scraping any URL.</li>
    <li>Choosing correct scenarios, languages, voices, and settings.</li>
    <li>Understanding that AI-generated content may differ from expectations.</li>
    <li>Any consequences of deleting videos or data from their dashboard.</li>
    <li>Compliance with the Terms of Service and community guidelines of any third-party platforms (TikTok, Instagram, YouTube, X) when using the upload feature.</li>
  </ul>
  <p>PromoNexAi is not responsible for user errors, misuse of the scraping tool, or penalties imposed by third-party platforms.</p>
</section>

<section>
  <h2>5. Payment and Refund Policy</h2>
  <p>Customers are billed only for successfully generated videos. If a video fails due to a technical error, the customer will not be charged. Refunds are not provided for user mistakes or deletion of videos, except where required by law.</p>
</section>

<section>
  <h2>6. Intellectual Property</h2>
  <p>Users retain ownership of their input and generated content. PromoNexAi retains rights to its platform and technology.</p>
</section>

<section>
  <h2>7. Limitations of Liability</h2>
  <p>PromoNexAi provides the service ''as is''. Liability is limited to fees paid in the past 12 months. PromoNexAi is not liable for indirect damages, scraping misuse, or third-party platform actions.</p>
</section>

<section>
  <h2>8. Account and Age Restriction</h2>
  <p>You must be 16 years or older to use PromoNexAi.</p>
</section>

<section>
  <h2>9. Termination</h2>
  <p>Accounts may be suspended or terminated for violations of these Terms, scraping misuse, or unlawful activity.</p>
</section>

<section>
  <h2>10. Governing Law</h2>
  <p>These Terms are governed by the laws of the Netherlands and EU regulations.</p>
</section>

<section>
  <h2>Contact</h2>
  <p>For questions, contact:</p>
  <p>📧 <em>support@promonexai.com</em></p>
</section>',
        '2025-10-01',
        true,
        NULL
    )
    ON CONFLICT (document_type, locale, version) DO UPDATE SET
        updated_at = NOW();

    RAISE NOTICE 'Created Terms of Service';

    -- ============================
    -- Privacy Policy
    -- ============================
    INSERT INTO public.cms_legal_documents (
        document_type,
        locale,
        version,
        content,
        effective_date,
        is_published,
        created_by
    )
    VALUES (
        'privacy',
        'en',
        1,
        '<h1>PromoNexAi Privacy Policy</h1>
<p><strong>Effective Date:</strong> October 1, 2025</p>

<section>
  <h2>1. Introduction</h2>
  <p>PromoNexAi B.V. respects your privacy. This Privacy Policy explains how we collect, use, and share personal data.</p>
</section>

<section>
  <h2>2. Company Information</h2>
  <p><strong>PromoNexAi B.V.</strong></p>
  <p>Herengracht 123, 1015 BS Amsterdam, The Netherlands</p>
  <p>Chamber of Commerce (KvK): 87654321</p>
  <p>VAT: NL123456789B01</p>
  <p>Email: privacy@promonexai.com</p>
</section>

<section>
  <h2>3. Data We Collect</h2>
  <ul>
    <li>Account data (name, email, billing)</li>
    <li>Product data scraped from URLs</li>
    <li>Usage data</li>
    <li>Technical data (IP, browser, device)</li>
    <li>Payment data (processed by Stripe)</li>
  </ul>
</section>

<section>
  <h2>4. How We Use Data</h2>
  <p>We use data to provide services, process payments, improve features, send notifications, and comply with legal obligations.</p>
</section>

<section>
  <h2>5. AI and Third-Party Services</h2>
  <p>We use Google Gemini, ElevenLabs, Runway, and Pexels for AI generation. Data may be shared with these providers under their privacy policies.</p>
</section>

<section>
  <h2>6. Google API Disclosure</h2>
  <p>PromoNexAi''s use and transfer of information received from Google APIs will adhere to Google API Services User Data Policy, including the Limited Use requirements.</p>
</section>

<section>
  <h2>7. Data Retention</h2>
  <p>We retain data as long as your account is active, or as needed for service delivery and legal compliance.</p>
</section>

<section>
  <h2>8. Data Sharing</h2>
  <p>We do not sell personal data. We share data only with service providers, for legal reasons, or with your consent. When using the upload/share feature, data is sent to third-party platforms (TikTok, Instagram, YouTube, X) per their terms.</p>
</section>

<section>
  <h2>9. International Transfers</h2>
  <p>Your data may be processed outside the EU/EEA. We ensure adequate safeguards (e.g., Standard Contractual Clauses).</p>
</section>

<section>
  <h2>10. User Responsibility</h2>
  <p>You are responsible for ensuring URLs are lawful and that you comply with third-party platform terms when uploading or sharing content.</p>
</section>

<section>
  <h2>11. Your Rights</h2>
  <p>You have the right to access, correct, delete, restrict processing, port data, and object to processing. You can also withdraw consent or lodge a complaint with a data protection authority.</p>
</section>

<section>
  <h2>12. Cookies</h2>
  <p>We use cookies for authentication, preferences, and analytics. See our Cookie Policy for details.</p>
</section>

<section>
  <h2>13. Children</h2>
  <p>Users must be 16 years or older.</p>
</section>

<section>
  <h2>14. Security</h2>
  <p>We implement industry-standard security measures. No method is 100% secure.</p>
</section>

<section>
  <h2>15. Changes</h2>
  <p>We may update this Privacy Policy. Continued use after changes means acceptance.</p>
</section>

<section>
  <h2>Contact</h2>
  <p>For questions, contact:</p>
  <p>📧 <em>privacy@promonexai.com</em></p>
</section>',
        '2025-10-01',
        true,
        NULL
    )
    ON CONFLICT (document_type, locale, version) DO UPDATE SET
        updated_at = NOW();

    RAISE NOTICE 'Created Privacy Policy';

    -- ============================
    -- Data Processing Agreement (DPA)
    -- ============================
    INSERT INTO public.cms_legal_documents (
        document_type,
        locale,
        version,
        content,
        effective_date,
        is_published,
        created_by
    )
    VALUES (
        'dpa',
        'en',
        1,
        '<h1>PromoNexAi Data Processing Agreement (DPA)</h1>
<p><strong>Effective Date:</strong> October 1, 2025</p>

<section>
  <h2>1. Parties and Roles</h2>
  <p>This Data Processing Agreement ("DPA") is between PromoNexAi B.V. ("Processor") and the customer ("Controller"). This DPA applies to the processing of personal data in connection with the PromoNexAi services.</p>
</section>

<section>
  <h2>2. Subject Matter and Duration</h2>
  <p><strong>Subject Matter:</strong> Processing personal data for AI-powered video generation services, including scraping, script generation, voiceover creation, video assembly, and optional direct upload/sharing to third-party platforms.</p>
  <p><strong>Duration:</strong> The term of this DPA is for the duration of the service agreement between the parties.</p>
</section>

<section>
  <h2>3. Nature and Purpose of Processing</h2>
  <p>PromoNexAi processes personal data to provide video generation services, including analyzing product URLs, generating marketing scripts, creating voiceovers, assembling videos, and facilitating direct upload to social media platforms.</p>
</section>

<section>
  <h2>4. Categories of Data Subjects</h2>
  <p>Users of the PromoNexAi platform, including business owners, marketers, and content creators.</p>
</section>

<section>
  <h2>5. Categories of Personal Data</h2>
  <ul>
    <li>Account information (name, email, billing details)</li>
    <li>Product URLs and scraped data</li>
    <li>User-generated content (scripts, preferences)</li>
    <li>Usage and technical data (IP addresses, device information)</li>
    <li>Payment data (processed by third-party payment processors)</li>
  </ul>
</section>

<section>
  <h2>6. Processor Obligations</h2>
  <p>PromoNexAi will:</p>
  <ul>
    <li>Process personal data only on documented instructions from the Controller</li>
    <li>Ensure confidentiality of personnel processing personal data</li>
    <li>Implement appropriate technical and organizational security measures</li>
    <li>Engage sub-processors only with prior written authorization</li>
    <li>Assist the Controller in responding to data subject requests</li>
    <li>Assist the Controller in ensuring compliance with GDPR obligations</li>
    <li>Delete or return personal data upon termination of services</li>
    <li>Make available information necessary to demonstrate compliance</li>
  </ul>
</section>

<section>
  <h2>7. Sub-Processors</h2>
  <p>PromoNexAi uses the following sub-processors:</p>
  <ul>
    <li>Google Gemini (AI script generation)</li>
    <li>ElevenLabs (text-to-speech/voiceover generation)</li>
    <li>Runway (video generation)</li>
    <li>Pexels (stock footage)</li>
    <li>Stripe (payment processing)</li>
    <li>Supabase (database hosting)</li>
    <li>Third-party platforms (TikTok, Instagram, YouTube, X) when using upload/share features</li>
  </ul>
</section>

<section>
  <h2>8. International Transfers</h2>
  <p>Personal data may be transferred to countries outside the EU/EEA. PromoNexAi ensures such transfers comply with GDPR through Standard Contractual Clauses or other approved mechanisms.</p>
</section>

<section>
  <h2>9. Data Security</h2>
  <p>PromoNexAi implements industry-standard security measures, including encryption, access controls, regular security audits, and incident response procedures.</p>
</section>

<section>
  <h2>10. Data Breach Notification</h2>
  <p>In the event of a personal data breach, PromoNexAi will notify the Controller without undue delay and no later than 72 hours after becoming aware of the breach.</p>
</section>

<section>
  <h2>11. Audit Rights</h2>
  <p>The Controller has the right to audit PromoNexAi''s compliance with this DPA, subject to reasonable notice and confidentiality obligations.</p>
</section>

<section>
  <h2>12. Liability and Indemnification</h2>
  <p>Each party''s liability under this DPA is subject to the limitations set out in the main service agreement.</p>
</section>

<section>
  <h2>13. Termination</h2>
  <p>Upon termination of services, PromoNexAi will delete or return all personal data to the Controller, unless retention is required by law.</p>
</section>

<section>
  <h2>14. Governing Law</h2>
  <p>This DPA is governed by the laws of the Netherlands and is subject to GDPR compliance.</p>
</section>

<section>
  <h2>Contact</h2>
  <p>For DPA-related questions, contact:</p>
  <p>📧 <em>dpo@promonexai.com</em></p>
</section>',
        '2025-10-01',
        true,
        NULL
    )
    ON CONFLICT (document_type, locale, version) DO UPDATE SET
        updated_at = NOW();

    RAISE NOTICE 'Created Data Processing Agreement (DPA)';

    -- ============================
    -- Cookie Policy
    -- ============================
    INSERT INTO public.cms_legal_documents (
        document_type,
        locale,
        version,
        content,
        effective_date,
        is_published,
        created_by
    )
    VALUES (
        'cookies',
        'en',
        1,
        '<h1>PromoNexAi B.V. Cookie Policy</h1>
<p><strong>Effective Date:</strong> October 1, 2025</p>

<section>
  <h2>1. Introduction</h2>
  <p>This Cookie Policy explains how PromoNexAi B.V. ("we", "our") uses cookies and similar technologies on our website and app.</p>
</section>

<section>
  <h2>2. What Are Cookies?</h2>
  <p>Cookies are small text files placed on your device to store data that can be recalled by a web server in the domain that placed the cookie.</p>
</section>

<section>
  <h2>3. How We Use Cookies</h2>
  <p>We use cookies to operate, secure, and improve our services, to remember your preferences, and to analyze usage.</p>
</section>

<section>
  <h2>4. Types of Cookies We Use</h2>
  <ul>
    <li><strong>Strictly Necessary:</strong> required for basic site functionality (authentication, security).</li>
    <li><strong>Functional:</strong> remember preferences such as language and region.</li>
    <li><strong>Analytics:</strong> measure traffic and usage to improve performance.</li>
    <li><strong>Marketing:</strong> personalize ads and measure campaign effectiveness (only with consent).</li>
  </ul>
</section>

<section>
  <h2>5. Cookie Retention</h2>
  <p>Cookie lifetimes vary: session cookies expire when you close your browser; persistent cookies remain for a defined period (typically 1–24 months) unless deleted earlier by you.</p>
</section>

<section>
  <h2>6. Third‑Party Cookies</h2>
  <p>We may use third‑party services (e.g., analytics, payment, AI providers) that place cookies on your device. These parties have their own privacy and cookie policies.</p>
</section>

<section>
  <h2>7. Your Choices & Consent</h2>
  <p>When you first visit, we present a cookie banner where you can accept all cookies or manage preferences. You can also change your preferences at any time via the cookie settings link in the footer or your browser settings.</p>
</section>

<section>
  <h2>8. Do Not Track</h2>
  <p>Our services do not currently respond to Do Not Track signals.</p>
</section>

<section>
  <h2>9. Changes to This Policy</h2>
  <p>We may update this Cookie Policy from time to time. Changes will be posted with a new effective date.</p>
</section>

<section>
  <h2>10. Contact</h2>
  <p>For questions, contact us at:</p>
  <p>📧 <em>privacy@promonexai.com</em></p>
</section>',
        '2025-10-01',
        true,
        NULL
    )
    ON CONFLICT (document_type, locale, version) DO UPDATE SET
        updated_at = NOW();

    RAISE NOTICE 'Created Cookie Policy';

    RAISE NOTICE '✅ Legal documents migration completed successfully!';
    RAISE NOTICE 'Created 4 documents: Terms, Privacy, DPA, Cookies';
END $$;
