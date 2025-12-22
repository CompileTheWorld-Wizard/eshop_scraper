import threading
import time
import re
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from app.models import ProductInfo, TaskStatusResponse, TaskStatus, TaskPriority
from app.utils import generate_task_id, proxy_manager, user_agent_manager, is_valid_url
from app.utils.credit_utils import can_perform_action, deduct_credits
from app.utils.task_management import (
    create_task, start_task, update_task_progress, 
    complete_task, fail_task, get_task_status, TaskType, TaskStatus as TMStatus
)
from app.config import settings
from bs4 import BeautifulSoup
from app.logging_config import get_logger

logger = get_logger(__name__)

    
class ScrapingService:
    """Main service for orchestrating scraping operations"""
    
    def __init__(self):
        # Platform detection indicators for HTML analysis
        self.platform_indicators = {
                            'shopify': {
                    'patterns': [
                        r'Shopify\.theme',
                        r'shopify-section',
                        r'shopify\.analytics',
                        r'shopify\.checkout',
                        r'Shopify\.routes',
                        r'Shopify\.locale',
                        r'shop\.myshopify\.com',
                        r'window\.Shopify',
                        r'Shopify\.money_format',
                        r'Shopify\.country',
                        r'ShopifyAnalytics',
                        r'cdn\.shopify\.com',
                        r'shopifycloud\.com',
                    ],
                    'meta_tags': [
                        'shopify-digital-wallet',
                        'shopify-checkout-api-token',
                        'shopify-platform',
                    ],
                    'script_sources': [
                        'cdn.shopify.com',
                        'shopifycloud.com',
                        'monorail-edge.shopifysvc.com',
                    ],
                    'css_classes': [
                        'shopify-section',
                        'shopify-block',
                        'shopify-payment-button',
                    ],
                },
                'bigcommerce': {
                    'patterns': [
                        r'window\.product_attributes',
                        r'window\.BCData',
                        r'window\.product',
                        r'BigCommerce',
                        r'bigcommerce',
                        r'BC\.',
                        r'bc\.',
                    ],
                    'meta_tags': [
                        'bigcommerce-platform',
                        'bc-platform',
                    ],
                    'script_sources': [
                        'cdn.bigcommerce.com',
                        'bigcommerce.com',
                        'api.bigcommerce.com',
                    ],
                    'css_classes': [
                        'productView',
                        'productView-title',
                        'productView-price',
                        'productView-description',
                        'productView-image',
                    ],
                },
                'squarespace': {
                    'patterns': [
                        r'window\.Squarespace',
                        r'window\.SQ',
                        r'window\.SQUARESpace_CONTEXT',
                        r'Squarespace',
                        r'SQ\.',
                        r'sq\.',
                    ],
                    'meta_tags': [
                        'squarespace-platform',
                        'sq-platform',
                    ],
                    'script_sources': [
                        'cdn.squarespace.com',
                        'squarespace.com',
                        'api.squarespace.com',
                    ],
                    'css_classes': [
                        'sqs-product',
                        'product-title',
                        'product-price',
                        'product-description',
                        'product-image',
                    ],
                },
            'woocommerce': {
                'patterns': [
                    r'wp-content\/plugins\/woocommerce',
                    r'woocommerce\.js',
                    r'wc-ajax',
                    r'wc_add_to_cart_params',
                    r'wc_single_product_params',
                    r'woocommerce_params',
                    r'wc_cart_fragments_params',
                    r'wc_cart_hash',
                    r'woocommerce-cart',
                    r'woocommerce-checkout',
                    r'add-to-cart',
                    r'WooCommerce',
                    r'woocommerce\.min\.js',
                    r'woocommerce\.css',
                    r'woocommerce\.min\.css',
                ],
                'meta_tags': [
                    'woocommerce-enabled',
                    'generator.*woocommerce',
                    'woocommerce-version',
                ],
                'script_sources': [
                    'wp-content/plugins/woocommerce',
                    'woocommerce/assets',
                    'woocommerce.js',
                    'woocommerce.min.js',
                ],
            },
            'wordpress': {
                'patterns': [
                    r'wp-content',
                    r'wp-includes',
                    r'wp-admin',
                    r'wordpress',
                    r'wp_nonce',
                    r'wpdb',
                    r'wp-json',
                    r'rest_route',
                    r'wp_ajax',
                    r'WordPress',
                ],
                'meta_tags': [
                    'generator.*wordpress',
                    'generator.*WordPress',
                ],
                'script_sources': [
                    'wp-includes',
                    'wp-content',
                    'wp-admin',
                ],
                'css_classes': [
                    'wp-',
                    'wordpress',
                    'wp-block',
                ],
            },
            'squarespace': {
                'patterns': [
                    r'squarespace',
                    r'static1\.squarespace\.com',
                    r'assets\.squarespace\.com',
                    r'sqsp\.net',
                    r'squarespace-cdn',
                    r'Squarespace',
                    r'SQUARESPACE_ROLLUPS',
                    r'squarespace\.com',
                    r'Y\.Squarespace',
                ],
                'meta_tags': [
                    'squarespace-platform-preview',
                    'generator.*squarespace',
                ],
                'script_sources': [
                    'squarespace.com',
                    'squarespacestatus.com',
                    'static1.squarespace.com',
                    'assets.squarespace.com',
                ],
                'css_classes': [
                    'squarespace',
                    'sqs-',
                    'sqsrte-',
                ],
            },
            'magento': {
                'patterns': [
                    r'magento',
                    r'mage\/cookies',
                    r'skin\/frontend',
                    r'Mage\.Cookies',
                    r'MAGENTO_ROOT',
                    r'Magento',
                    r'mage\/js',
                    r'checkout\/cart',
                    r'customer\/account',
                    r'Mage\.apply',
                    r'magentosite',
                ],
                'meta_tags': [
                    'magento',
                    'generator.*magento',
                ],
                'script_sources': [
                    'magento',
                    'mage/',
                ],
                'css_classes': [
                    'magento',
                    'catalog-product',
                    'checkout-cart',
                    'page-layout-',
                    'cms-',
                ],
            },
            'webflow': {
                'patterns': [
                    r'webflow',
                    r'assets\.website-files\.com',
                    r'uploads-ssl\.webflow\.com',
                    r'Webflow',
                    r'w-node-',
                    r'w-embed',
                    r'webflow\.js',
                    r'wf-active',
                    r'wf-loading',
                ],
                'meta_tags': [
                    'webflow-platform',
                    'generator.*webflow',
                ],
                'script_sources': [
                    'webflow.com',
                    'assets.website-files.com',
                    'uploads-ssl.webflow.com',
                ],
                'css_classes': [
                    'w-node-',
                    'w-embed',
                    'w-form',
                    'w-button',
                    'w-tab',
                    'w-slider',
                ],
            },
            'wix': {
                'patterns': [
                    r'wixstatic\.com',
                    r'parastorage\.com',
                    r'static\.wixstatic\.com',
                    r'wix-code-public-path',
                    r'Wix\.com',
                    r'WixSite',
                    r'SITE_CONTAINER',
                    r'wix\.com',
                    r'wixapps\.net',
                    r'wix_typography',
                ],
                'meta_tags': [
                    'wix-platform',
                    'generator.*wix',
                ],
                'script_sources': [
                    'wix.com',
                    'wixstatic.com',
                    'parastorage.com',
                    'wixapps.net',
                ],
                'css_classes': [
                    'wixui-',
                    'SITE_CONTAINER',
                    'mesh-layout',
                    'wix-ads',
                ],
            }
        }
    
    # ============================================================================
    # PUBLIC API METHODS
    # ============================================================================
    
    def start_scraping_task(
        self,
        url: str,
        user_id: str,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        target_language: Optional[str] = None
    ) -> TaskStatusResponse:
        """
        Start a scraping task asynchronously using threads
        
        Args:
            url: Product URL to scrape
            user_id: User ID associated with the task (required)
            proxy: Custom proxy to use
            user_agent: Custom user agent to use
            target_language: Target language for content extraction
            
        Returns:
            TaskStatusResponse with task_id and PENDING status
        """
        # Create task in MongoDB first to get the actual task ID
        try:
            # Create the task in MongoDB and get the actual task ID
            logger.info(f"Creating MongoDB task for URL: {url}")
            actual_task_id = create_task(
                TaskType.SCRAPING,
                url=url,
                user_id=user_id,
                target_language=target_language,
                proxy=proxy,
                user_agent=user_agent
            )
            if not actual_task_id:
                raise Exception("Failed to create task in MongoDB")
            
            logger.info(f"Successfully created MongoDB task with ID: {actual_task_id}")
            
            # Start the task
            logger.info(f"Starting MongoDB task {actual_task_id}")
            task_started = start_task(actual_task_id)
            if not task_started:
                raise Exception("Failed to start task in MongoDB")
            
            logger.info(f"Successfully created and started MongoDB task {actual_task_id}")
            
        except Exception as e:
            logger.error(f"Failed to create MongoDB task for {url}: {e}")
            # Fallback to local task creation if MongoDB fails
            fallback_task_id = generate_task_id(url)
            response = TaskStatusResponse(
                task_id=fallback_task_id,
                status=TaskStatus.FAILED,
                url=url,
                task_type="scraping",
                progress=None,
                message=f"Failed to create task: {str(e)}",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                priority=TaskPriority.NORMAL,
                user_id=user_id,
                session_id=None,
                detail={}
            )
            return response
        
        # Initialize response with the actual task ID from MongoDB
        detail = {}
        # Note: target_language is not included in detail for scraping tasks
        
        response = TaskStatusResponse(
            task_id=actual_task_id,
            status=TaskStatus.PENDING,
            url=url,
            task_type="scraping",
            progress=None,
            message="Task created, waiting to start",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            priority=TaskPriority.NORMAL,
            user_id=user_id,
            session_id=None,
            detail=detail
        )
        
        # Start scraping in a separate thread
        thread = threading.Thread(
            target=self._execute_scraping_task_thread,
            args=(actual_task_id, url, user_id, proxy, user_agent, target_language),
            daemon=True
        )
        thread.start()
        
        logger.info(f"Started scraping task {actual_task_id} for {url} by user {user_id} in thread")
        return response

    def _execute_scraping_task_thread(
        self,
        task_id: str,
        url: str,
        user_id: str,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        target_language: Optional[str] = None
    ):
        """
        Execute the actual scraping task in a separate thread
        
        Args:
            task_id: The task ID to execute
            url: Product URL to scrape
            user_id: User ID associated with the task
            proxy: Custom proxy to use
            user_agent: Custom user agent to use
            target_language: Target language for content extraction
        """
        logger.info(f"Starting execute_scraping_task for task_id: {task_id}, url: {url}")
        try:
            # Validate URL
            if not is_valid_url(url):
                raise ValueError(f"Invalid URL format: {url}")
            
            # Check user's credit
            credit_check = can_perform_action(user_id, "scraping")
            if credit_check.get("error"):
                raise ValueError(f"Credit check failed: {credit_check['error']}")
            
            if not credit_check.get("can_perform", False):
                reason = credit_check.get("reason", "Insufficient credits")
                current_credits = credit_check.get("current_credits", 0)
                required_credits = credit_check.get("required_credits", 1)
                raise ValueError(f"Credit check failed: {reason}. Current credits: {current_credits}, Required: {required_credits}")
            
            logger.info(f"Credit check passed for user {user_id}. Can perform scraping action.")
            
            # Update task status in MongoDB
            update_task_progress(task_id, 1, "Starting scraping process")
            
            # Get proxy and user agent if not provided
            if not proxy and settings.ROTATE_PROXIES:
                proxy = proxy_manager.get_proxy()
            
            if not user_agent and settings.ROTATE_USER_AGENTS:
                user_agent = user_agent_manager.get_user_agent()
            
            # First, get HTML content using browser manager with retry logic
            update_task_progress(task_id, 2, "Fetching page content")
            from app.browser_manager import browser_manager
            
            # Use timeout logic to prevent blocking
            start_time = time.time()
            timeout_seconds = settings.BROWSER_PAGE_FETCH_TIMEOUT / 1000.0
            
            try:
                html_content = browser_manager.get_page_content_with_retry(url, proxy, user_agent, True)
                
                # Check if we exceeded timeout
                if time.time() - start_time > timeout_seconds:
                    raise Exception(f"Page content fetching timed out after {timeout_seconds} seconds")
                    
            except Exception as e:
                if time.time() - start_time > timeout_seconds:
                    raise Exception(f"Page content fetching timed out after {timeout_seconds} seconds")
                else:
                    raise e
            
            # Detect platform based on URL and content
            update_task_progress(task_id, 3, "Detecting e-commerce platform")
            platform, platform_confidence, platform_indicators = self._detect_platform_smart(url, html_content)
            
            # Create appropriate extractor based on detected platform
            update_task_progress(task_id, 4, "Creating platform-specific extractor")
            from app.extractors.factory import ExtractorFactory
            from app.extractors.cdiscount import CDiscountExtractor
            extractor = ExtractorFactory.create_extractor(platform, html_content, url)
            
            logger.info(f"Extractor created successfully: {type(extractor).__name__}")
            
            # Check for captcha and solve if needed
            update_task_progress(task_id, 5, "Checking for captcha")
            
            # Use platform-specific captcha detection if available
            captcha_detected = False
            
            # Use direct type checking instead of hasattr
            if isinstance(extractor, CDiscountExtractor) and platform == 'cdiscount':
                logger.info("Using CDiscount-specific captcha detection")
                captcha_detected = extractor.detect_cdiscount_captcha()
            else:
                logger.info("Using generic captcha detection")
                captcha_detected = extractor.detect_captcha()
            
            if captcha_detected:
                logger.info(f"Captcha detected on {url}, attempting to solve...")
                update_task_progress(task_id, 6, "Solving captcha")
                
                # Get a fresh page for captcha solving
                page = browser_manager.create_page(user_agent)
                try:
                    # Navigate to the URL again
                    page.goto(url, wait_until='domcontentloaded', timeout=120000)
                    
                    # Wait a bit for the page to fully load before solving captcha
                    page.wait_for_timeout(3000)
                    
                    # Solve the captcha
                    captcha_solved = extractor.solve_captcha(page)
                    
                    if captcha_solved:
                        logger.info("Captcha solved successfully, waiting for page to stabilize...")
                        
                        # Wait longer for the page to process after captcha solving
                        page.wait_for_timeout(10000)  # Wait 10 seconds for page to process
                        
                        # Additional waiting for page to fully process after captcha solving
                        try:
                            # Wait for network idle to ensure all requests are complete
                            page.wait_for_load_state('networkidle', timeout=30000)
                        except Exception:
                            pass
                        
                        # Wait for DOM content to be ready
                        try:
                            page.wait_for_load_state('domcontentloaded', timeout=20000)
                        except Exception:
                            pass
                        
                        # Additional wait for JavaScript execution
                        page.wait_for_timeout(5000)
                        
                        # Wait for page stability
                        try:
                            page.wait_for_function(
                                """
                                () => {
                                    return new Promise((resolve) => {
                                        setTimeout(() => {
                                            // Check if page is stable and no loading indicators
                                            const isStable = !document.querySelector('[style*="animation"]') && 
                                                           !document.querySelector('[class*="loading"]') &&
                                                           !document.querySelector('[class*="spinner"]') &&
                                                           document.readyState === 'complete';
                                            resolve(isStable);
                                        }, 3000);
                                    });
                                }
                                """,
                                timeout=30000
                            )
                        except Exception:
                            pass
                        
                        # Get updated HTML content after captcha solving and page stabilization
                        html_content = page.content()
                        
                        # Recreate extractor with updated content
                        extractor = ExtractorFactory.create_extractor(platform, html_content, url)
                        
                        # Keep the page open for a bit longer to ensure everything is processed
                        page.wait_for_timeout(2000)
                        
                    else:
                        logger.warning("Failed to solve captcha, proceeding with original content")
                except Exception as captcha_error:
                    logger.error(f"Error during captcha solving: {captcha_error}")
                finally:
                    page.close()
            else:
                logger.info("No captcha detected, proceeding with normal extraction")
            
            # Extract product information using the platform-specific extractor
            update_task_progress(task_id, 7, "Extracting product information")
            product_info = extractor.extract_product_info()
            
            # Update task progress before saving to database
            update_task_progress(task_id, 8, "Saving product to database and detecting category")
            
            # Update task with results
            product_id, short_id = self._save_product_to_supabase(user_id, product_info, url, platform, target_language, task_id)
            
            # Complete the task in MongoDB with product_id and short_id
            complete_task(task_id, {
                "product_id": product_id,
                "short_id": short_id
            })
            
            logger.info(f"Successfully scraped product from {url}")
            
            # Deduct credits on successful scraping
            try:
                success = deduct_credits(
                    user_id=user_id, 
                    action_name="scraping",
                    reference_id=product_id,
                    reference_type="product",
                    description=f"Product scraping completed for {url}"
                )
                if success:
                    logger.info(f"Successfully deducted credits for user {user_id} for scraping task {task_id}")
                else:
                    logger.warning(f"Failed to deduct credits for user {user_id} for scraping task {task_id}")
            except Exception as credit_error:
                logger.error(f"Error deducting credits for user {user_id} for scraping task {task_id}: {credit_error}")
            
            # Clean up browser resources in the same thread where they were created
            try:
                from app.browser_manager import browser_manager
                browser_manager.cleanup()
                logger.info(f"Browser cleanup completed for task {task_id}")
            except Exception as cleanup_error:
                logger.warning(f"Browser cleanup failed for task {task_id}: {cleanup_error}")
            
        except Exception as e:
            logger.error(f"Error in execute_scraping_task for task_id: {task_id}: {e}", exc_info=True)
            
            # Update task with error in MongoDB
            fail_task(task_id, str(e))
            
            # Clean up browser resources even on error
            try:
                from app.browser_manager import browser_manager
                browser_manager.cleanup()
                logger.info(f"Browser cleanup completed for failed task {task_id}")
            except Exception as cleanup_error:
                logger.warning(f"Browser cleanup failed for failed task {task_id}: {cleanup_error}")
        
        logger.info(f"Completed execute_scraping_task for task_id: {task_id}")

    def scrape_product_with_user(
        self,
        url: str,
        user_id: str,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        target_language: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None
    ) -> TaskStatusResponse:
        """
        Scrape product information from URL with user authentication
        
        Args:
            url: Product URL to scrape
            user_id: User ID associated with the task
            proxy: Custom proxy to use
            user_agent: Custom user agent to use
            target_language: Target language for content extraction
            detail: Additional details for the task
            
        Returns:
            TaskStatusResponse with task information
        """
        # Create task in MongoDB first to get the actual task ID
        try:
            # Create the task in MongoDB and get the actual task ID
            logger.info(f"Creating MongoDB task for URL: {url}")
            actual_task_id = create_task(
                TaskType.SCRAPING,
                url=url,
                user_id=user_id,
                target_language=target_language,
                proxy=proxy,
                user_agent=user_agent
            )
            if not actual_task_id:
                raise Exception("Failed to create task in MongoDB")
            
            logger.info(f"Successfully created MongoDB task with ID: {actual_task_id}")
            
            # Start the task
            logger.info(f"Starting MongoDB task {actual_task_id}")
            task_started = start_task(actual_task_id)
            if not task_started:
                raise Exception("Failed to start task in MongoDB")
            
            logger.info(f"Successfully created and started MongoDB task {actual_task_id}")
            
        except Exception as e:
            logger.error(f"Failed to create MongoDB task for {url}: {e}")
            # Fallback to local task creation if MongoDB fails
            fallback_task_id = generate_task_id(url)
            response = TaskStatusResponse(
                task_id=fallback_task_id,
                status=TaskStatus.FAILED,
                url=url,
                task_type="scraping",
                progress=None,
                message=f"Failed to create task: {str(e)}",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                priority=TaskPriority.NORMAL,
                user_id=user_id,
                session_id=None,
                detail=detail
            )
            return response
        
        # Initialize response with the actual task ID from MongoDB
        response = TaskStatusResponse(
            task_id=actual_task_id,
            status=TaskStatus.PENDING,
            url=url,
            task_type="scraping",
            progress=None,
            message="Task created, waiting to start",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            priority=TaskPriority.NORMAL,
            user_id=user_id,
            session_id=None,
            detail=detail
        )
        
        # Start scraping in a separate thread
        thread = threading.Thread(
            target=self._execute_scraping_task_thread,
            args=(actual_task_id, url, user_id, proxy, user_agent, target_language),
            daemon=True
        )
        thread.start()
        
        logger.info(f"Started scraping task {actual_task_id} for {url} by user {user_id} in thread")
        return response

    def scrape_product(
        self,
        url: str,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        target_language: Optional[str] = None
    ) -> TaskStatusResponse:
        """
        Scrape product information from URL (synchronous version for backward compatibility)
        
        Args:
            url: Product URL to scrape
            proxy: Custom proxy to use
            user_agent: Custom user agent to use
            target_language: Target language for content extraction
            
        Returns:
            TaskStatusResponse with product information
        """
        # Create task in MongoDB first to get the actual task ID
        try:
            # Create the task in MongoDB and get the actual task ID
            logger.info(f"Creating MongoDB task for URL: {url}")
            actual_task_id = create_task(
                TaskType.SCRAPING,
                url=url,
                proxy=proxy,
                user_agent=user_agent
            )
            if not actual_task_id:
                raise Exception("Failed to create task in MongoDB")
            
            logger.info(f"Successfully created MongoDB task with ID: {actual_task_id}")
            
            # Start the task
            logger.info(f"Starting MongoDB task {actual_task_id}")
            task_started = start_task(actual_task_id)
            if not task_started:
                raise Exception("Failed to start task in MongoDB")
            
            logger.info(f"Successfully created and started MongoDB task {actual_task_id}")
            
        except Exception as e:
            logger.error(f"Failed to create MongoDB task for URL {url}: {e}")
            # Continue with scraping even if MongoDB task creation fails
            actual_task_id = generate_task_id(url)  # Fallback to generated ID
        
        # Initialize response with the actual task ID from MongoDB
        response = TaskStatusResponse(
            task_id=actual_task_id,
            status=TaskStatus.PENDING,
            url=url,
            task_type="scraping",
            progress=None,
            message="Task created, waiting to start",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            priority=TaskPriority.NORMAL,
            user_id=None,
            session_id=None,
            detail={}
        )
        
        try:
            # Validate URL
            if not is_valid_url(url):
                raise ValueError(f"Invalid URL format: {url}")
            
            # Check user's credit (for synchronous scraping, we'll use a default user_id)
            # Note: In production, this should be passed as a parameter
            default_user_id = "00000000-0000-0000-0000-000000000000"  # Placeholder
            credit_check = can_perform_action(default_user_id, "scraping")
            if credit_check.get("error"):
                raise ValueError(f"Credit check failed: {credit_check['error']}")
            
            if not credit_check.get("can_perform", False):
                reason = credit_check.get("reason", "Insufficient credits")
                current_credits = credit_check.get("current_credits", 0)
                required_credits = credit_check.get("required_credits", 1)
                raise ValueError(f"Credit check failed: {reason}. Current credits: {current_credits}, Required: {required_credits}")
            
            logger.info(f"Credit check passed for user {default_user_id}. Can perform scraping action.")
            
            # Update task status in MongoDB
            update_task_progress(actual_task_id, 1, "Starting scraping process")
            
            # Get proxy and user agent if not provided
            if not proxy and settings.ROTATE_PROXIES:
                proxy = proxy_manager.get_proxy()
            
            if not user_agent and settings.ROTATE_USER_AGENTS:
                user_agent = user_agent_manager.get_user_agent()
            
            # First, get HTML content using browser manager
            update_task_progress(actual_task_id, 2, "Fetching page content")
            from app.browser_manager import browser_manager
            html_content = browser_manager.get_page_content_with_retry(url, proxy, user_agent, True)
            
            # Detect platform based on URL and content
            update_task_progress(actual_task_id, 3, "Detecting e-commerce platform")
            platform, platform_confidence, platform_indicators = self._detect_platform_smart(url, html_content)
            
            # Create appropriate extractor based on detected platform
            update_task_progress(actual_task_id, 4, "Creating platform-specific extractor")
            from app.extractors.factory import ExtractorFactory
            from app.extractors.cdiscount import CDiscountExtractor
            extractor = ExtractorFactory.create_extractor(platform, html_content, url)
            
            logger.info(f"Extractor created successfully: {type(extractor).__name__}")
            logger.info(f"About to start captcha detection for platform: {platform}")
            
            # Check for captcha and solve if needed
            update_task_progress(actual_task_id, 5, "Checking for captcha")
            logger.info("Starting captcha detection process...")
            
            # Use platform-specific captcha detection if available
            captcha_detected = False
            
            # Debug: Check extractor type and available methods
            logger.info(f"Extractor type: {type(extractor).__name__}")
            logger.info(f"Platform: {platform}")
            logger.info(f"Has detect_cdiscount_captcha method: {hasattr(extractor, 'detect_cdiscount_captcha')}")
            logger.info(f"Available methods: {[method for method in dir(extractor) if 'captcha' in method.lower()]}")
            
            # Use direct type checking instead of hasattr
            if isinstance(extractor, CDiscountExtractor) and platform == 'cdiscount':
                logger.info("Using CDiscount-specific captcha detection")
                captcha_detected = extractor.detect_cdiscount_captcha()
                logger.info(f"CDiscount captcha detection result: {captcha_detected}")
            else:
                logger.info("Using generic captcha detection")
                captcha_detected = extractor.detect_captcha()
                logger.info(f"Generic captcha detection result: {captcha_detected}")
            
            if captcha_detected:
                logger.info(f"Captcha detected on {url}, attempting to solve...")
                update_task_progress(actual_task_id, 6, "Solving captcha")
                
                # Get a fresh page for captcha solving
                page = browser_manager.create_page(user_agent)
                try:
                    # Navigate to the URL again
                    page.goto(url, wait_until='domcontentloaded', timeout=120000)
                    
                    # Solve the captcha
                    captcha_solved = extractor.solve_captcha(page)
                    if captcha_solved:
                        logger.info("Captcha solved successfully, re-fetching content")
                        # Get updated HTML content after captcha solving
                        html_content = page.content()
                        
                        # Recreate extractor with updated content
                        extractor = ExtractorFactory.create_extractor(platform, html_content, url)
                    else:
                        logger.warning("Failed to solve captcha, proceeding with original content")
                except Exception as captcha_error:
                    logger.error(f"Error during captcha solving: {captcha_error}")
                finally:
                    page.close()
            else:
                logger.info("No captcha detected, proceeding with normal extraction")
            
            # Extract product information using the platform-specific extractor
            update_task_progress(actual_task_id, 7, "Extracting product information")
            product_info = extractor.extract_product_info()
            
            # Update task progress before saving to database
            update_task_progress(actual_task_id, 8, "Saving product to database and detecting category")
            
            # Update task with results
            product_id, short_id = self._save_product_to_supabase(default_user_id, product_info, url, platform, target_language, actual_task_id)
            
            # Complete the task in MongoDB with product_id and short_id
            complete_task(actual_task_id, {
                "product_id": product_id,
                "short_id": short_id
            })
            
            # Update response with results
            response.status = TaskStatus.COMPLETED
            response.message = "Scraping completed successfully"
            response.product_info = product_info
            response.completed_at = datetime.now()
            response.detected_platform = platform
            response.platform_confidence = platform_confidence
            response.platform_indicators = platform_indicators or []
            response.supabase_product_id = product_id
            response.short_id = short_id
            
            # Add short_id to response detail
            if short_id:
                response.detail = {"short_id": short_id}
            else:
                response.detail = {}
            
            logger.info(f"Successfully scraped product from {url}")
            
            # Deduct credits on successful scraping
            try:
                success = deduct_credits(
                    user_id=default_user_id, 
                    action_name="scraping",
                    reference_id=product_id,
                    reference_type="product",
                    description=f"Product scraping completed for {url}"
                )
                if success:
                    logger.info(f"Successfully deducted credits for user {default_user_id} for scraping task {actual_task_id}")
                else:
                    logger.warning(f"Failed to deduct credits for user {default_user_id} for scraping task {actual_task_id}")
            except Exception as credit_error:
                logger.error(f"Error deducting credits for user {default_user_id} for scraping task {actual_task_id}: {credit_error}")
            
            # Clean up browser resources
            try:
                from app.browser_manager import browser_manager
                browser_manager.cleanup()
                logger.info(f"Browser cleanup completed for task {actual_task_id}")
            except Exception as cleanup_error:
                logger.warning(f"Browser cleanup failed for task {actual_task_id}: {cleanup_error}")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error in scrape_product for {url}: {error_msg}", exc_info=True)
            
            # Update task with error in MongoDB
            fail_task(actual_task_id, error_msg)
            
            # Update response with error
            response.status = TaskStatus.FAILED
            response.message = error_msg
            response.error = error_msg
            response.completed_at = datetime.now()
            
            # Clean up browser resources even on error
            try:
                from app.browser_manager import browser_manager
                browser_manager.cleanup()
                logger.info(f"Browser cleanup completed for failed task {actual_task_id}")
            except Exception as cleanup_error:
                logger.warning(f"Browser cleanup failed for failed task {actual_task_id}: {cleanup_error}")
        
        return response

    # ============================================================================
    # TASK MANAGEMENT METHODS
    # ============================================================================
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status"""
        try:
            task = get_task_status(task_id)
            if not task:
                logger.warning(f"Task {task_id} not found in MongoDB")
                return None
            
            # Convert Task object to dictionary format for backward compatibility
            task_dict = {
                'status': task.task_status,
                'created_at': task.created_at,
                'updated_at': task.updated_at,
                'url': task.url,
                'user_id': task.user_id,
                'message': task.task_status_message,
                'progress': task.progress,
                'current_step': task.current_step,
                'current_step_name': task.current_step_name,
                'error_message': task.error_message,
                # Note: Platform data is stored in Supabase, but product_id is stored in task metadata
                'platform': None,
                'platform_confidence': None,
                'platform_indicators': None,
                'product_id': task.task_metadata.get('product_id') if task.task_metadata else None,
                'short_id': task.task_metadata.get('short_id') if task.task_metadata else None
            }
            
            return task_dict
            
        except Exception as e:
            logger.error(f"Error getting task status for {task_id}: {e}")
            return None
    
    def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get all active tasks"""
        # Since we removed the get_tasks_by_status function, 
        # we'll return an empty dictionary for now
        # In the future, this could be enhanced to work with the fallback storage
        return {}
    
    def cleanup_completed_tasks(self, max_age_hours: int = 24):
        """Clean up old completed tasks"""
        try:
            from app.utils.task_management import cleanup_old_tasks
            # Convert hours to days for the cleanup function
            days_old = max_age_hours / 24.0
            if days_old < 1:
                days_old = 1  # Minimum 1 day
            
            deleted_count = cleanup_old_tasks(int(days_old))
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old tasks from MongoDB")
            else:
                logger.info("No old tasks to clean up")
                
        except Exception as e:
            logger.error(f"Error cleaning up completed tasks: {e}")

    # ============================================================================
    # PLATFORM DETECTION METHODS
    # ============================================================================
    
    def _detect_platform_smart(self, url: str, html_content: str) -> Tuple[Optional[str], float, List[str]]:
        """
        Smart platform detection: URL-only for known platforms, URL+content for others
        Returns: (platform, confidence, indicators)
        """
        # Platforms that only need URL-based detection
        url_only_platforms = ['amazon', 'ebay', 'cdiscount', 'jd', 'otto', 'bol']
        
        # First try URL-based detection
        url_platform, url_confidence, url_indicators = self._detect_platform_from_url(url)
        
        # If it's a URL-only platform and we detected it, return immediately
        if url_platform and url_platform in url_only_platforms and url_confidence >= 0.9:
            logger.info(f"Platform detected from URL (URL-only platform): {url_platform} (confidence: {url_confidence})")
            return url_platform, url_confidence, url_indicators
        
        # For other platforms (like Shopify), try HTML analysis as well
        if url_platform and url_platform not in url_only_platforms:
            # For platforms like Shopify, check HTML content too
            html_platform, html_confidence, html_indicators = self._detect_platform_from_html_safely(html_content, url)
            
            # If both methods found the same platform, increase confidence
            if html_platform == url_platform:
                combined_confidence = min(url_confidence + html_confidence * 0.3, 1.0)
                combined_indicators = url_indicators + [f"HTML analysis confirmed: {html_platform} (confidence: {html_confidence:.2f})"]
                logger.info(f"Platform confirmed by both URL and HTML: {url_platform} (confidence: {combined_confidence:.2f})")
                return url_platform, combined_confidence, combined_indicators
            elif html_platform and html_confidence > url_confidence:
                # HTML analysis found a different platform with higher confidence
                combined_indicators = html_indicators + [f"URL analysis suggested: {url_platform} (confidence: {url_confidence:.2f})"]
                logger.info(f"Platform detected from HTML with higher confidence: {html_platform} (confidence: {html_confidence:.2f})")
                return html_platform, html_confidence, combined_indicators
            else:
                # Stick with URL detection
                logger.info(f"Platform detected from URL: {url_platform} (confidence: {url_confidence})")
                return url_platform, url_confidence, url_indicators
        
        # If URL detection failed, try HTML analysis for any platform
        html_platform, html_confidence, html_indicators = self._detect_platform_from_html_safely(html_content, url)
        if html_platform:
            logger.info(f"Platform detected from HTML analysis: {html_platform} (confidence: {html_confidence:.2f})")
            return html_platform, html_confidence, html_indicators
        
        # No platform detected
        return None, 0.0, ["No platform detected from URL or HTML analysis"]

    def _detect_platform_from_url(self, url: str) -> Tuple[Optional[str], float, List[str]]:
        """
        Detect platform from URL first
        Returns: (platform, confidence, indicators)
        """
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # URL-based platform detection
            url_platforms = {
                'amazon': {
                    'domains': ['amazon.com', 'www.amazon.com', 'amazon.co.uk', 'www.amazon.co.uk', 
                               'amazon.de', 'www.amazon.de', 'amazon.fr', 'www.amazon.fr', 
                               'amazon.it', 'www.amazon.it', 'amazon.es', 'www.amazon.es', 
                               'amazon.nl', 'www.amazon.nl', 'amazon.ca', 'www.amazon.ca', 
                               'amazon.com.au', 'www.amazon.com.au', 'amazon.co.jp', 'www.amazon.co.jp', 
                               'amazon.in', 'www.amazon.in'],
                    'confidence': 0.95,
                    'indicators': [f"Amazon domain detected: {domain}"]
                },
                'ebay': {
                    'domains': ['ebay.com', 'www.ebay.com', 'ebay.co.uk', 'www.ebay.co.uk', 
                               'ebay.de', 'www.ebay.de', 'ebay.fr', 'www.ebay.fr', 
                               'ebay.it', 'www.ebay.it', 'ebay.es', 'www.ebay.es', 
                               'ebay.ca', 'www.ebay.ca', 'ebay.nl', 'www.ebay.nl', 
                               'ebay.com.au', 'www.ebay.com.au'],
                    'confidence': 0.95,
                    'indicators': [f"eBay domain detected: {domain}"]
                },
                'otto': {
                    'domains': ['otto.de', 'www.otto.de'],
                    'confidence': 0.95,
                    'indicators': [f"Otto domain detected: {domain}"]
                },
                'bol': {
                    'domains': ['bol.com', 'www.bol.com'],
                    'confidence': 0.95,
                    'indicators': [f"Bol.com domain detected: {domain}"]
                },
                'jd': {
                    'domains': ['jd.com', 'www.jd.com', 'global.jd.com', 'www.global.jd.com'],
                    'confidence': 0.95,
                    'indicators': [f"JD.com domain detected: {domain}"]
                },
                'cdiscount': {
                    'domains': ['cdiscount.com', 'www.cdiscount.com'],
                    'confidence': 0.95,
                    'indicators': [f"CDiscount domain detected: {domain}"]
                },
                'shopify': {
                    'domains': ['myshopify.com', '*.myshopify.com', 'shop.myshopify.com'],
                    'confidence': 0.95,
                    'indicators': [f"Shopify domain detected: {domain}"]
                },
                'bigcommerce': {
                    'domains': ['bigcommerce.com', '*.bigcommerce.com', 'api.bigcommerce.com'],
                    'confidence': 0.95,
                    'indicators': [f"Bigcommerce domain detected: {domain}"]
                },
                'squarespace': {
                    'domains': ['squarespace.com', '*.squarespace.com', 'api.squarespace.com'],
                    'confidence': 0.95,
                    'indicators': [f"Squarespace domain detected: {domain}"]
                }
            }
            
            # Check if domain matches any known platform
            for platform, config in url_platforms.items():
                # Check exact match first
                if domain in config['domains']:
                    return platform, config['confidence'], config['indicators']
                
                # Check wildcard patterns
                for pattern in config['domains']:
                    if pattern.startswith('*.'):
                        suffix = pattern[2:]  # Remove '*.' prefix
                        if domain.endswith(suffix):
                            return platform, config['confidence'], config['indicators']
            
            # No URL-based platform detected
            return None, 0.0, [f"No known platform detected from URL domain: {domain}"]
            
        except Exception as e:
            logger.warning(f"URL-based platform detection failed for {url}: {e}")
            return None, 0.0, [f"URL-based platform detection failed: {str(e)}"]

    def _detect_platform_from_html_safely(self, html_content: str, url: str) -> Tuple[Optional[str], float, List[str]]:
        """
        Safely detect platform from HTML content with error handling
        Returns: (platform, confidence, indicators)
        """
        try:
            platform, confidence, indicators = self._analyze_content_for_platform(html_content)
            return platform, confidence, indicators
        except Exception as e:
            logger.warning(f"Platform detection from HTML failed for {url}: {e}")
            # Return default values if detection fails
            return None, 0.0, [f"Platform detection failed: {str(e)}"]

    def _analyze_content_for_platform(self, html_content: str) -> Tuple[Optional[str], float, List[str]]:
        """Analyze HTML content for platform indicators using only reliable methods"""
        soup = BeautifulSoup(html_content, 'html.parser')
        scores = {}
        all_indicators = {}
        
        for platform, config in self.platform_indicators.items():
            score = 0
            indicators = []
            
            # 1. Check HTML patterns (search entire HTML content) - Most reliable
            for pattern in config.get('patterns', []):
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                if matches:
                    match_count = len(matches)
                    pattern_score = min(0.4 * match_count, 0.8)  # Increased weight for patterns
                    score += pattern_score
                    indicators.append(f"HTML pattern '{pattern}' found {match_count} time(s)")
            
            # 2. Check meta tags - Very reliable
            meta_tags = soup.find_all('meta')
            for meta_pattern in config.get('meta_tags', []):
                for meta in meta_tags:
                    # Check all meta attributes
                    meta_content = ' '.join([
                        str(meta.get('content', '')),
                        str(meta.get('name', '')),
                        str(meta.get('property', '')),
                        str(meta.get('http-equiv', ''))
                    ])
                    if re.search(meta_pattern, meta_content, re.IGNORECASE):
                        score += 0.6  # Increased weight for meta tags
                        indicators.append(f"Meta tag pattern: {meta_pattern}")
                        break
            
            # 3. Check external script sources - Reliable
            scripts = soup.find_all('script')
            for script_pattern in config.get('script_sources', []):
                for script in scripts:
                    # Check src attribute only (external scripts)
                    src = script.get('src', '')
                    if src and script_pattern in src:
                        score += 0.5  # Increased weight for external scripts
                        indicators.append(f"External script: {script_pattern}")
            
            if score > 0:
                scores[platform] = min(score, 1.0)  # Cap at 1.0
                all_indicators[platform] = indicators
        
        # Handle platform conflicts and preferences
        if 'wordpress' in scores and 'woocommerce' in scores:
            # WooCommerce is WordPress-based, so if WooCommerce is detected with decent confidence, prefer it
            if scores['woocommerce'] >= 0.3:
                scores.pop('wordpress', None)
                all_indicators.pop('wordpress', None)
            elif scores['wordpress'] > scores['woocommerce'] * 2:
                # If WordPress score is much higher, it's likely plain WordPress
                scores.pop('woocommerce', None)
                all_indicators.pop('woocommerce', None)
        
        if not scores:
            return None, 0.0, ["No platform indicators found"]
        
        best_platform = max(scores, key=scores.get)
        confidence = scores[best_platform]
        indicators = all_indicators[best_platform]
        
        return best_platform, confidence, indicators

    # ============================================================================
    # SCRAPER CREATION METHODS
    # ============================================================================
    


    # ============================================================================
    # TASK UPDATE METHODS
    # ============================================================================
    
    # Task update methods are now handled by MongoDB task management utilities
    # See app.utils.task_management for update_task_progress, complete_task, fail_task, etc.
    
    def _save_product_to_supabase(self, user_id: str, product_info, original_url: str, platform: Optional[str] = None, target_language: Optional[str] = None, task_id: Optional[str] = None):
        """
        Save scraped product data to Supabase products table and create a shorts entry
        
        Args:
            user_id: User ID who requested the scraping
            product_info: Extracted product information
            original_url: Original product URL that was scraped
            platform: Detected e-commerce platform
            target_language: Target language for content generation (defaults to 'en-US')
            
        Returns:
            tuple: (product_id, short_id) or (None, None) if failed
        """
        try:
            from app.utils.supabase_utils import supabase_manager
            
            if not supabase_manager.is_connected():
                logger.warning("Supabase not connected, skipping product save")
                return None, None
            
            # Validate required fields
            if not product_info.title:
                logger.warning("Product title is missing, skipping save to Supabase")
                return None, None
            
            # Prepare product data for Supabase
            product_data = {
                "user_id": user_id,
                "title": product_info.title,
                "description": product_info.description or "",
                "price": float(product_info.price) if product_info.price and product_info.price > 0 else None,
                "currency": product_info.currency or "USD",
                "images": self._convert_images_to_jsonb_format(product_info.images or []),
                "original_url": original_url,
                "platform": platform or "unknown",
                "rating": float(product_info.rating) if product_info.rating and product_info.rating > 0 else None,
                "review_count": int(product_info.review_count) if product_info.review_count and product_info.review_count > 0 else None,
                "specifications": product_info.specifications or {},
                "metadata": {
                    "scraped_at": datetime.now().isoformat(),
                    "platform_detected": platform,
                    "source_url": original_url
                }
            }
            
            # Remove None values to avoid database errors
            product_data = {k: v for k, v in product_data.items() if v is not None}
                        
            # Detect category using OpenAI before saving
            detected_category_id = self._detect_category_with_openai(product_info)
            if detected_category_id:
                product_data["category_id"] = detected_category_id
                logger.info(f"Detected category ID for product '{product_info.title}': {detected_category_id}")
            else:
                logger.warning(f"Failed to detect category for product '{product_info.title}', proceeding without category")
            
            # Create a shorts entry first
            short_id = self._create_shorts_entry(user_id, product_info, target_language)
            
            if not short_id:
                logger.warning("Failed to create shorts entry, skipping product save")
                return None, None
            
            # Add short_id to product data
            product_data["short_id"] = short_id
            
            # Insert into products table
            result = supabase_manager.insert_record_sync("products", product_data)
            
            if result:
                product_id = result.get('id')
                logger.info(f"Successfully saved product to Supabase for user {user_id}: {product_data['title']} (ID: {product_id}) linked to short {short_id}")
                
                # Session for scraping task was already created when task was created
                # No need to create session here since it's created immediately
                
                return product_id, short_id
            else:
                logger.error(f"Failed to save product to Supabase for user {user_id}")
                # Try to clean up the created short
                try:
                    supabase_manager.client.table('shorts').delete().eq('id', short_id).execute()
                    logger.info(f"Cleaned up orphaned short {short_id} after product creation failed")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to clean up orphaned short {short_id}: {cleanup_error}")
                return None, None
                
        except ImportError:
            logger.warning("Supabase utils not available, skipping product save")
            return None, None
        except Exception as e:
            logger.error(f"Error saving product to Supabase: {e}", exc_info=True)
            # Don't raise the exception to avoid breaking the scraping flow
            return None, None

    def _create_shorts_entry(self, user_id: str, product_info, target_language: Optional[str] = None):
        """
        Create a shorts entry in the shorts table for a newly scraped product
        
        Args:
            user_id: User ID who owns the product
            product_info: The extracted product information
            target_language: Target language for content generation (defaults to 'en-US')
        """
        try:
            from app.utils.supabase_utils import supabase_manager
            
            if not supabase_manager.is_connected():
                logger.warning("Supabase not connected, skipping shorts creation")
                return None
            
            # Set default target language if not provided
            if not target_language:
                target_language = "en-US"
            
            # Prepare shorts data
            shorts_data = {
                "user_id": user_id,
                "title": f"Short for {product_info.title}",
                "description": f"Auto-generated short video project for {product_info.title}",
                "status": "draft",
                "target_language": target_language,
                "metadata": {
                    "auto_created": True,
                    "created_from_scraping": True,
                    "product_title": product_info.title,
                    "product_platform": getattr(product_info, 'platform', 'unknown'),
                    "created_at": datetime.now().isoformat()
                }
            }
            
            # Insert into shorts table
            result = supabase_manager.insert_record_sync("shorts", shorts_data)
            
            if result:
                short_id = result.get('id')
                logger.info(f"Successfully created shorts entry: Short ID {short_id}")
                return short_id
            else:
                logger.warning(f"Failed to create shorts entry")
                return None
                
        except Exception as e:
            logger.error(f"Error creating shorts entry: {e}", exc_info=True)
            # Don't raise the exception to avoid breaking the main flow
            return None

    def _detect_category_with_openai(self, product_info) -> Optional[str]:
        """
        Detect product category using OpenAI based on product information.
        
        Args:
            product_info: Extracted product information containing title, description, and specifications
            
        Returns:
            str: Detected category ID (UUID) or None if detection fails
        """
        try:
            from app.utils.supabase_utils import get_categories
            import openai
            
            # Check if OpenAI API key is configured
            if not settings.OPENAI_API_KEY:
                logger.warning("OpenAI API key not configured, skipping category detection")
                return None
            
            # Get categories from database
            categories = get_categories()
            if not categories:
                logger.warning("No categories found in database, skipping category detection")
                return None
            
            # Filter to only include sub-categories (those with parent_id)
            sub_categories = [cat for cat in categories if cat.get('parent_id')]
            if not sub_categories:
                logger.warning("No sub-categories found in database, skipping category detection")
                return None
            
            # Prepare product information for category detection
            product_info_text = {
                'title': product_info.title,
                'description': getattr(product_info, 'description', '') or '',
                'specifications': getattr(product_info, 'specifications', {}) or {}
            }
            
            # Create prompt for category detection
            prompt = f"""Analyze the following product information and determine the most appropriate sub-category name from the provided list:

Product Title: {product_info_text['title']}
Product Description: {product_info_text['description'][:500]}
Product Specifications: {', '.join([f"{k}: {v}" for k, v in product_info_text['specifications'].items()])}

Please respond with ONLY the exact category name from the list below. Do not include any other text or explanation.

Available sub-categories:
{chr(10).join([f"- {cat['name']}" for cat in sub_categories])}"""
            
            # Initialize OpenAI client
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            
            logger.info("Sending category detection request to OpenAI...")
            
            # Call OpenAI for category detection with simple text response
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a product categorization expert. Choose the most appropriate sub-category from the provided list. Respond with ONLY the exact category name, no other text."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            logger.info("OpenAI response received")
            logger.info(f"Response choices: {len(response.choices)}")
            
            # Process the text response
            if not response.choices:
                raise Exception("No choices in OpenAI response")

            message = response.choices[0].message
            content = message.content
            
            if not content:
                raise Exception("No content in OpenAI response")
            
            # Clean the response content (remove extra whitespace, newlines, etc.)
            detected_category_name = content.strip()
            
            # Find the matching category in our sub-categories
            matched_category = None
            for cat in sub_categories:
                if cat['name'].lower() == detected_category_name.lower():
                    matched_category = cat
                    break
            
            if matched_category:
                logger.info(f"Successfully detected sub-category: {matched_category['name']} (ID: {matched_category['id']})")
                return matched_category['id']
            else:
                # Try fuzzy matching if exact match fails
                logger.warning(f"Exact match failed for '{detected_category_name}', trying fuzzy matching")
                
                # Try to find partial matches
                for cat in sub_categories:
                    if detected_category_name.lower() in cat['name'].lower() or cat['name'].lower() in detected_category_name.lower():
                        logger.info(f"Fuzzy match found: {cat['name']} (ID: {cat['id']})")
                        return cat['id']
                
                # If no match found, use the first available sub-category as fallback
                fallback_category_id = sub_categories[0]['id']
                fallback_category_name = sub_categories[0]['name']
                logger.info(f"No match found for '{detected_category_name}', using fallback: {fallback_category_name} (ID: {fallback_category_id})")
                return fallback_category_id

        except ImportError:
            logger.warning("OpenAI library not available, skipping category detection")
            return None
        except Exception as e:
            logger.error(f"Error in category detection: {e}", exc_info=True)
            return None

    def _convert_images_to_jsonb_format(self, images: List[str]) -> Dict[str, Dict]:
        """
        Convert a list of image URLs to JSONB format where each URL is a key with an empty object as value.
        
        Args:
            images: List of image URLs
            
        Returns:
            Dictionary with image URLs as keys and empty objects as values
        """
        if not images:
            return {}
        
        # Convert list of URLs to object format: {url: {}}
        return {url: {} for url in images if url}

# Global scraping service instance
scraping_service = ScrapingService() 