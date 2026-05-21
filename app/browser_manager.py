import time
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext
from app.config import settings
from app.logging_config import get_logger


logger = get_logger(__name__)


class BrowserManager:
    """Manages browser instances with configurable headless and proxy settings"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.playwright = None
        self.browser_name: Optional[str] = None
        
    def setup_browser(
        self,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        browser_name: Optional[str] = None,
    ) -> Tuple[Browser, BrowserContext, Page]:
        """
        Setup browser with optional proxy and user agent
        
        Args:
            proxy: Optional proxy string (e.g., "http://user:pass@host:port")
            user_agent: Optional custom user agent
            
        Returns:
            Tuple of (Browser, BrowserContext, Page) instances
        """
        try:
            # Clean up existing browser if any
            self.cleanup()
            
            self.playwright = sync_playwright().start()
            selected_browser = browser_name or settings.DEFAULT_BROWSER
            browser_config = settings.get_browser_config(selected_browser)
            playwright_browser_name = browser_config.get("name", "chromium")
            
            # Chrome launch arguments for stealth and performance
            launch_args = [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-extensions',
                '--disable-plugins',
                '--disable-background-networking',
                '--disable-default-apps',
                '--disable-sync',
                '--disable-translate',
                '--hide-scrollbars',
                '--mute-audio',
                '--no-first-run',
                '--safebrowsing-disable-auto-update',
                '--ignore-certificate-errors',
                '--ignore-ssl-errors',
                '--ignore-certificate-errors-spki-list',
                '--disable-blink-features=AutomationControlled',
                '--disable-automation',
                '--disable-webrtc-encryption',
                '--disable-webrtc-hw-encoding',
                '--disable-webrtc-hw-decoding',
                '--disable-webrtc-multiple-routes',
                '--disable-2d-canvas-clip-aa',
                '--disable-3d-apis',
                '--disable-accelerated-2d-canvas',
                '--disable-webgl',
                '--disable-webgl2',
                '--disable-audio-service',
                '--disable-audio-input',
                '--disable-audio-output',
                '--disable-font-subpixel-positioning',
                '--lang=en-US,en',
                '--accept-lang=en-US,en;q=0.9',
                '--memory-pressure-off',
                '--max_old_space_size=4096',
                '--disable-client-side-phishing-detection',
                '--disable-component-extensions-with-background-pages',
                '--disable-domain-reliability',
                '--disable-features=TranslateUI',
                '--disable-prompt-on-repost',
                '--force-color-profile=srgb',
                '--metrics-recording-only',
                '--password-store=basic',
                '--use-mock-keychain',
                # Additional arguments for better JavaScript execution
                '--enable-javascript',
                '--enable-scripts',
                '--allow-running-insecure-content',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-background-timer-throttling=false',
                '--disable-renderer-backgrounding=false',
            ]
            
            # Launch Chrome browser with configurable headless setting
            launch_options = {
                "headless": settings.PLAYWRIGHT_HEADLESS,
            }
            if playwright_browser_name == "chromium":
                launch_options["args"] = launch_args
            else:
                launch_options["args"] = [
                    arg for arg in browser_config.get("args", [])
                    if arg != "--devtools"
                ]
                if browser_config.get("firefox_user_prefs"):
                    launch_options["firefox_user_prefs"] = browser_config["firefox_user_prefs"]
            
            if proxy:
                launch_options["proxy"] = self._build_proxy_config(proxy)
                logger.info(f"Playwright proxy configured: {self._safe_proxy_label(proxy)}")
            
            try:
                browser_launcher = getattr(self.playwright, playwright_browser_name)
                self.browser = browser_launcher.launch(**launch_options)
                self.browser_name = selected_browser
            except Exception as launch_error:
                if playwright_browser_name == "chromium":
                    raise
                logger.warning(
                    f"Failed to launch configured browser '{selected_browser}' "
                    f"({launch_error}); falling back to Chromium"
                )
                fallback_options = {
                    "headless": settings.PLAYWRIGHT_HEADLESS,
                    "args": launch_args
                }
                if proxy:
                    fallback_options["proxy"] = self._build_proxy_config(proxy)
                self.browser = self.playwright.chromium.launch(**fallback_options)
                self.browser_name = settings.DEFAULT_BROWSER
            
            # Create browser context with additional settings
            context_options = {
                'viewport': {
                    'width': settings.PLAYWRIGHT_VIEWPORT_WIDTH,
                    'height': settings.PLAYWRIGHT_VIEWPORT_HEIGHT
                },
                'user_agent': user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'ignore_https_errors': True,
                'java_script_enabled': True,
                'locale': 'en-US',
                'timezone_id': 'Europe/Amsterdam',
                'has_touch': False,
                'is_mobile': False,
                'device_scale_factor': 1,
                'color_scheme': 'light',
            }
            
            self.context = self.browser.new_context(**context_options)
            
            # Create page
            page = self.context.new_page()
            
            # Set timeouts
            page.set_default_timeout(settings.PLAYWRIGHT_TIMEOUT)
            page.set_default_navigation_timeout(settings.PLAYWRIGHT_TIMEOUT)
            
            # Apply image blocking by default
            page.route("**/*", self._block_resources)
            logger.info("Image blocking enabled by default")
            
            logger.info(
                f"Browser setup completed - Browser: {self.browser_name}, "
                f"Headless: {settings.PLAYWRIGHT_HEADLESS}, Proxy: {proxy is not None}"
            )
            return self.browser, self.context, page
            
        except Exception as e:
            logger.error(f"Failed to setup Chrome browser: {e}")
            self.cleanup()
            raise
    
    def create_page(self, user_agent: Optional[str] = None) -> Page:
        """
        Create a new page with configured settings
        
        Args:
            user_agent: Optional custom user agent
            block_images: Whether to block image requests
            
        Returns:
            Page instance
        """
        if not self.browser or not self.context:
            self.setup_browser()
            return self.context.pages[0] if self.context.pages else self.context.new_page()
        
        page = self.context.new_page()
        
        # Always block images and videos
        page.route("**/*", self._block_resources)
        logger.info("Image blocking enabled for new page")
        
        return page
    
    def _block_resources(self, route):
        """Block image, video, and other non-essential resources"""
        resource_type = route.request.resource_type
        url = route.request.url.lower()
        
        # Log blocked requests for debugging
        logger.debug(f"Checking request: {resource_type} - {url}")
        
        # Block images, media, fonts, and other non-essential resources
        if resource_type in ['image', 'media']:
            logger.debug(f"Blocking {resource_type}: {url}")
            route.abort()
        # Also block common image file extensions regardless of resource type
        elif any(ext in url for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp', '.ico', '.tiff']):
            logger.debug(f"Blocking image extension: {url}")
            route.abort()
        # Block any URL containing image-related query parameters
        elif any(param in url for param in ['width=', 'height=', 'crop=', 'v=', '&width=', '&height=', '&crop=']):
            logger.debug(f"Blocking image params: {url}")
            route.abort()
        else:
            route.continue_()
    
    def get_page_content(self, url: str, proxy: Optional[str] = None, user_agent: Optional[str] = None) -> str:
        """
        Get HTML content from a URL
        
        Args:
            url: URL to fetch
            proxy: Optional proxy
            user_agent: Optional user agent
            
        Returns:
            HTML content as string
        """
        page = None
        try:
            effective_proxy = proxy
            if self._should_bypass_proxy_for_url(url):
                if proxy:
                    logger.info("Temporarily bypassing proxy for Otto verification")
                    effective_proxy = None
                    if self.browser:
                        self.cleanup()
            
            requested_browser = self._get_browser_name_for_url(url)
            
            # Setup browser if needed. Recreate it when a URL needs a different
            # browser engine, e.g. eBay is configured to use Firefox.
            if not self.browser or self.browser_name != requested_browser:
                if self.browser:
                    self.cleanup()
                self.setup_browser(proxy=effective_proxy, user_agent=user_agent, browser_name=requested_browser)
            
            # Create page
            page = self.create_page(user_agent)
            
            # Navigate to URL
            logger.info(f"Navigating to: {url}")
            response = page.goto(url, wait_until='domcontentloaded', timeout=120000)
            
            if not response or response.status >= 400:
                raise Exception(f"Failed to load page: {response.status if response else 'No response'}")
            
            # Wait for page to load with more robust approach
            try:
                # First try to wait for network idle with shorter timeout
                page.wait_for_load_state('networkidle', timeout=settings.BROWSER_NETWORK_IDLE_TIMEOUT)
            except Exception:
                # If network idle fails, wait for DOM content to be ready
                logger.info("Network idle timeout, waiting for DOM content instead")
                page.wait_for_load_state('domcontentloaded', timeout=settings.BROWSER_DOM_LOAD_TIMEOUT)
                
                # Additional wait for any critical elements to load
                try:
                    page.wait_for_timeout(settings.BROWSER_ADDITIONAL_WAIT)
                except Exception:
                    pass  # Ignore timeout on this additional wait
            
            # Wait for all JavaScript execution to complete and page to be fully ready
            self._wait_for_page_completion(page)
            
            # Scroll to bottom to trigger lazy loading of reviews/ratings
            if settings.BROWSER_ENABLE_SCROLLING:
                self._scroll_to_trigger_lazy_loading( page )
            
            # Get HTML content
            html_content = page.content()
            
            logger.info(f"Successfully fetched content from {url} (length: {len(html_content)})")
            return html_content
            
        except Exception as e:
            logger.error(f"Error fetching content from {url}: {e}")
            # Log additional context for debugging
            if page:
                try:
                    current_url = page.url
                    logger.error(f"Current page URL: {current_url}")
                except:
                    pass
            raise
        finally:
            if page:
                page.close()

    def _wait_for_page_completion(self, page: Page, timeout: int = None):
        """
        Wait for the page to be completely loaded and all JavaScript execution to finish.
        Universal solution that works for all sites and dynamic content.
        
        Args:
            page: Playwright page object
            timeout: Timeout in milliseconds (uses config default if None)
        """
        if timeout is None:
            timeout = settings.BROWSER_PAGE_COMPLETION_TIMEOUT
            
        try:
            logger.info("Waiting for page completion and JavaScript execution...")
            
            # Wait for ready state
            page.wait_for_function(
                "() => document.readyState === 'complete'",
                timeout=timeout
            )
            
            # Wait for network idle
            try:
                page.wait_for_load_state('networkidle', timeout=5000)
            except Exception:
                pass
            
            # Wait for JavaScript execution
            page.wait_for_function(
                """
                () => {
                    return new Promise((resolve) => {
                        // Wait for any pending JavaScript execution
                        setTimeout(() => {
                            // Simple check: ensure page is stable and no loading indicators
                            const isStable = !document.querySelector('[style*="animation"]') && 
                                           !document.querySelector('[class*="loading"]') &&
                                           !document.querySelector('[class*="spinner"]');
                            resolve(isStable);
                        }, 2000);
                    });
                }
                """,
                timeout=timeout
            )
            
            # Final wait to ensure all content is rendered
            time.sleep(2)
                
            logger.info("Page completion wait finished - all content should be loaded")
            
        except Exception as e:
            logger.warning(f"Error waiting for page completion: {e}")
            # Don't fail the entire request if page completion wait fails
            pass

    def _scroll_to_trigger_lazy_loading(self, page: Page):
        """
        Scroll to multiple positions to trigger lazy loading of content like reviews and ratings.
        Different sites trigger lazy loading at different scroll positions.
        """
        try:
            logger.info("Scrolling to multiple positions to trigger lazy loading...")
            
            # Get page height
            page_height = page.evaluate("document.body.scrollHeight")
            viewport_height = page.evaluate("window.innerHeight")
            
            # Scroll to multiple positions to trigger lazy loading
            scroll_positions = [0.25, 0.5, 0.75, 0.9, 1.0]  # 25%, 50%, 75%, 90%, 100%
            
            for position in scroll_positions:
                scroll_y = int(page_height * position)
                
                # Scroll to position with timeout
                try:
                    page.evaluate(f"""
                        window.scrollTo({{
                            top: {scroll_y},
                            behavior: 'smooth'
                        }});
                    """)
                    
                    # Wait for lazy loading to trigger
                    page.wait_for_timeout(1500)
                    
                except Exception:
                    logger.warning(f"Scroll timeout at {position * 100}% position")
                    continue
            
            # Scroll back to top
            try:
                page.evaluate("""
                    window.scrollTo({
                        top: 0,
                        behavior: 'smooth'
                    });
                """)
                
                # Wait for any triggered content to load
                page.wait_for_timeout(1000)
            except Exception:
                logger.warning("Scroll back to top timeout")
            
            logger.info("Multi-position scroll completed - lazy content should be loaded")
            
        except Exception as e:
            logger.warning(f"Error during scroll: {e}")
            # Don't fail if scroll fails
            pass
    
    def cleanup(self):
        """Clean up browser resources"""
        try:
            if self.context:
                self.context.close()
                self.context = None
            
            if self.browser:
                self.browser.close()
                self.browser = None
            
            if self.playwright:
                self.playwright.stop()
                self.playwright = None
            
            self.browser_name = None
                
            logger.info("Browser cleanup completed")
        except Exception as e:
            logger.error(f"Error during browser cleanup: {e}")
        finally:
            # Force cleanup of any remaining references
            self.context = None
            self.browser = None
            self.playwright = None
            self.browser_name = None

    def _build_proxy_config(self, proxy: str) -> Dict[str, str]:
        """Build Playwright proxy config from an authenticated proxy URL."""
        parsed = urlparse(proxy)
        if not parsed.scheme or not parsed.hostname:
            return {"server": proxy}
        
        server = f"{parsed.scheme}://{parsed.hostname}"
        if parsed.port:
            server = f"{server}:{parsed.port}"
        
        proxy_config = {"server": server}
        if parsed.username:
            proxy_config["username"] = parsed.username
        if parsed.password:
            proxy_config["password"] = parsed.password
        
        return proxy_config

    def _safe_proxy_label(self, proxy: str) -> str:
        """Return a log-safe proxy label without credentials."""
        parsed = urlparse(proxy)
        if not parsed.scheme or not parsed.hostname:
            return proxy
        
        host = parsed.hostname
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{host}{port}"

    def _should_bypass_proxy_for_url(self, url: str) -> bool:
        """Temporarily disable proxy for Otto scraping verification."""
        domain = urlparse(url).netloc.lower()
        return domain == "otto.de" or domain.endswith(".otto.de")

    def _get_browser_name_for_url(self, url: str) -> str:
        """Choose the configured browser for the URL domain."""
        domain = urlparse(url).netloc.lower()
        return settings.get_browser_for_domain(domain)

    def get_page_content_with_retry(self, url: str, proxy: Optional[str] = None, user_agent: Optional[str] = None, max_retries: int = None) -> str:
        """
        Get HTML content with retry logic for better reliability
        
        Args:
            url: URL to fetch
            proxy: Optional proxy
            user_agent: Optional user agent
            max_retries: Maximum number of retry attempts (uses config default if None)
            
        Returns:
            HTML content as string
        """
        if max_retries is None:
            max_retries = settings.BROWSER_MAX_RETRIES
            
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"Attempt {attempt + 1}/{max_retries + 1} to fetch content from {url}")
                content = self.get_page_content(url, proxy, user_agent)
                return content
                
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                
                if attempt < max_retries:
                    # Wait before retrying
                    time.sleep(2 ** attempt)  # Exponential backoff
                    
                    # Clean up and recreate browser for retry
                    try:
                        self.cleanup()
                    except:
                        pass
                else:
                    logger.error(f"All {max_retries + 1} attempts failed for {url}")
                    raise last_error



    



# Global browser manager instance
browser_manager = BrowserManager() 