import json
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from app.config import settings
from app.logging_config import get_logger


logger = get_logger(__name__)


class OttoCookieService:
    """Manage Otto cookies for direct HTTP scraping."""

    def __init__(self):
        self._lock = threading.Lock()

    def get_cookie_header(
        self,
        url: str,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        force_refresh: bool = False,
    ) -> str:
        """Return a Cookie header, refreshing Otto cookies when needed."""
        if not settings.OTTO_AUTO_COOKIE_REFRESH:
            return settings.OTTO_COOKIE

        with self._lock:
            if not force_refresh:
                cached_cookies = self._load_valid_cookies(proxy, user_agent)
                if cached_cookies:
                    logger.info("Using cached Otto cookies")
                    return self._format_cookie_header(cached_cookies)

            try:
                refreshed_cookies = self._refresh_cookies(url, proxy, user_agent)
                if refreshed_cookies:
                    self._save_cookies(refreshed_cookies, proxy, user_agent)
                    return self._format_cookie_header(refreshed_cookies)
            except Exception as e:
                logger.warning(f"Automatic Otto cookie refresh failed: {e}")

        if settings.OTTO_COOKIE:
            logger.info("Falling back to configured OTTO_COOKIE")
        return settings.OTTO_COOKIE

    def invalidate_cache(self) -> None:
        """Delete the cached Otto cookies so the next request refreshes them."""
        with self._lock:
            cache_path = self._cache_path()
            if cache_path.exists():
                try:
                    cache_path.unlink()
                    logger.info("Invalidated cached Otto cookies")
                except OSError as e:
                    logger.warning(f"Failed to invalidate Otto cookie cache: {e}")

    def get_page_content(
        self,
        url: str,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> str:
        """Fetch Otto HTML through the same browser session used to establish cookies."""
        with self._lock:
            html_content, cookies = self._fetch_page_content_with_browser(url, proxy, user_agent)
            valid_cookies = self._filter_valid_cookies(cookies)
            if valid_cookies:
                self._save_cookies(valid_cookies, proxy, user_agent)
            return html_content

    def _refresh_cookies(
        self,
        url: str,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> List[Dict]:
        """Open the persistent Chrome profile and collect Otto-set cookies."""
        logger.info("Refreshing Otto cookies with persistent Chrome profile")
        context = None
        page = None
        playwright = None
        timeout = settings.BROWSER_PAGE_FETCH_TIMEOUT

        try:
            playwright = sync_playwright().start()
            context = self._get_cookie_browser_context(playwright, proxy, user_agent)
            page = context.new_page()
            page.set_default_timeout(timeout)
            page.set_default_navigation_timeout(timeout)

            target_url = url or settings.OTTO_COOKIE_REFRESH_URL or "https://www.otto.de/"
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=timeout)
                self._wait_for_product_content(page)
            except Exception as e:
                logger.warning(f"Otto target URL cookie warm-up navigation failed: {e}")
                refresh_url = settings.OTTO_COOKIE_REFRESH_URL or "https://www.otto.de/"
                if target_url != refresh_url:
                    page.goto(refresh_url, wait_until="domcontentloaded", timeout=timeout)
                    page.wait_for_timeout(settings.OTTO_COOKIE_REFRESH_WAIT_MS)

            cookies = self._wait_for_required_cookies(context, page)
            otto_cookies = [cookie for cookie in cookies if self._is_otto_cookie(cookie)]
            valid_cookies = self._filter_valid_cookies(otto_cookies)
            logger.info(f"Collected {len(valid_cookies)} valid Otto cookies")
            return valid_cookies
        finally:
            self._close_existing_chrome_page(page)
            if context and not settings.OTTO_USE_EXISTING_CHROME:
                context.close()
            if playwright:
                playwright.stop()

    def _fetch_page_content_with_browser(
        self,
        url: str,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[str, List[Dict]]:
        logger.info("Fetching Otto page content with Playwright fallback")
        context = None
        page = None
        playwright = None
        timeout = settings.BROWSER_PAGE_FETCH_TIMEOUT

        try:
            playwright = sync_playwright().start()
            context = self._get_cookie_browser_context(playwright, proxy, user_agent)
            page = context.new_page()
            page.set_default_timeout(timeout)
            page.set_default_navigation_timeout(timeout)

            refresh_url = settings.OTTO_COOKIE_REFRESH_URL or "https://www.otto.de/"
            page.goto(refresh_url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_timeout(settings.OTTO_COOKIE_REFRESH_WAIT_MS)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            self._wait_for_product_content(page)

            html_content = page.content()
            cookies = self._wait_for_required_cookies(context, page)
            otto_cookies = [cookie for cookie in cookies if self._is_otto_cookie(cookie)]
            logger.info(f"Fetched Otto browser fallback content (length: {len(html_content)})")
            return html_content, otto_cookies
        finally:
            self._close_existing_chrome_page(page)
            if context and not settings.OTTO_USE_EXISTING_CHROME:
                context.close()
            if playwright:
                playwright.stop()

    def _load_valid_cookies(
        self,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> List[Dict]:
        cache_path = self._cache_path()
        if not cache_path.exists():
            return []

        try:
            with cache_path.open("r", encoding="utf-8") as cookie_file:
                payload = json.load(cookie_file)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to read Otto cookie cache: {e}")
            return []

        cookies = payload.get("cookies", []) if isinstance(payload, dict) else []
        if not self._matches_request_context(payload, proxy, user_agent):
            return []
        valid_cookies = self._filter_valid_cookies(cookies)
        if not self._has_required_cookies(valid_cookies):
            logger.info("Cached Otto cookies are missing required KPSDK cookies")
            return []
        return valid_cookies

    def _save_cookies(
        self,
        cookies: List[Dict],
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        cache_path = self._cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at": int(time.time()),
            "proxy": self._safe_proxy_label(proxy),
            "user_agent": user_agent or settings.OTTO_USER_AGENT,
            "cookies": cookies,
        }
        with cache_path.open("w", encoding="utf-8") as cookie_file:
            json.dump(payload, cookie_file, ensure_ascii=True, indent=2)
        logger.info(f"Saved {len(cookies)} Otto cookies to cache")

    def _filter_valid_cookies(self, cookies: List[Dict]) -> List[Dict]:
        now = time.time()
        min_valid_until = now + settings.OTTO_COOKIE_MIN_TTL_SECONDS
        valid_cookies = []

        for cookie in cookies:
            if not self._is_otto_cookie(cookie):
                continue

            expires = cookie.get("expires", -1)
            if expires in (None, -1):
                valid_cookies.append(cookie)
                continue

            try:
                if float(expires) > min_valid_until:
                    valid_cookies.append(cookie)
            except (TypeError, ValueError):
                continue

        return valid_cookies

    def _format_cookie_header(self, cookies: List[Dict]) -> str:
        cookie_parts = []
        for cookie in cookies:
            name = cookie.get("name")
            value = cookie.get("value")
            if name and value is not None:
                cookie_parts.append(f"{name}={value}")
        return "; ".join(cookie_parts)

    def _matches_request_context(
        self,
        payload: Dict,
        proxy: Optional[str],
        user_agent: Optional[str],
    ) -> bool:
        expected_proxy = self._safe_proxy_label(proxy)
        expected_user_agent = user_agent or settings.OTTO_USER_AGENT
        return (
            payload.get("proxy") == expected_proxy
            and payload.get("user_agent") == expected_user_agent
        )

    def _get_cookie_browser_context(
        self,
        playwright,
        proxy: Optional[str],
        user_agent: Optional[str],
    ):
        if settings.OTTO_USE_EXISTING_CHROME:
            return self._connect_existing_chrome_context(playwright)

        return self._open_persistent_chrome_context(playwright, proxy, user_agent)

    def _connect_existing_chrome_context(self, playwright):
        logger.info(
            "Connecting to existing Chrome for Otto cookies at "
            f"{settings.OTTO_EXISTING_CHROME_CDP_URL}"
        )
        browser = playwright.chromium.connect_over_cdp(settings.OTTO_EXISTING_CHROME_CDP_URL)
        if browser.contexts:
            return browser.contexts[0]

        return browser.new_context(
            viewport={
                "width": settings.PLAYWRIGHT_VIEWPORT_WIDTH,
                "height": settings.PLAYWRIGHT_VIEWPORT_HEIGHT,
            },
            ignore_https_errors=True,
            java_script_enabled=True,
            locale="de-DE",
            timezone_id="Europe/Berlin",
        )

    def _open_persistent_chrome_context(
        self,
        playwright,
        proxy: Optional[str],
        user_agent: Optional[str],
    ):
        profile_path = Path(settings.OTTO_COOKIE_PROFILE_PATH)
        profile_path.mkdir(parents=True, exist_ok=True)

        context_options = {
            "headless": settings.OTTO_COOKIE_REFRESH_HEADLESS,
            "viewport": {
                "width": settings.PLAYWRIGHT_VIEWPORT_WIDTH,
                "height": settings.PLAYWRIGHT_VIEWPORT_HEIGHT,
            },
            "user_agent": user_agent or settings.OTTO_USER_AGENT,
            "ignore_https_errors": True,
            "java_script_enabled": True,
            "locale": "de-DE",
            "timezone_id": "Europe/Berlin",
            "args": self._persistent_chrome_launch_args(),
        }

        if settings.OTTO_COOKIE_BROWSER_CHANNEL:
            context_options["channel"] = settings.OTTO_COOKIE_BROWSER_CHANNEL

        if proxy:
            context_options["proxy"] = self._build_proxy_config(proxy)

        logger.info(
            "Opening Otto cookie browser profile "
            f"at {profile_path} with channel '{settings.OTTO_COOKIE_BROWSER_CHANNEL or 'default'}'"
        )
        return playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            **context_options,
        )

    def _cache_path(self) -> Path:
        return Path(settings.OTTO_COOKIE_CACHE_PATH)

    def _is_otto_cookie(self, cookie: Dict) -> bool:
        domain = str(cookie.get("domain", "")).lstrip(".").lower()
        return domain == "otto.de" or domain.endswith(".otto.de")

    def _has_required_cookies(self, cookies: List[Dict]) -> bool:
        required_cookie_names = set(settings.OTTO_COOKIE_REQUIRED_NAMES)
        if not required_cookie_names:
            return True

        cookie_names = {cookie.get("name") for cookie in cookies}
        return required_cookie_names.issubset(cookie_names)

    def _close_existing_chrome_page(self, page) -> None:
        """Close only the tab opened for Otto cookie refresh in an existing Chrome."""
        if (
            not page
            or not settings.OTTO_USE_EXISTING_CHROME
            or not settings.OTTO_CLOSE_CHROME_TAB_AFTER_REFRESH
        ):
            return

        try:
            page.close()
            logger.info("Closed Otto Chrome tab after cookie refresh")
        except Exception as e:
            logger.debug(f"Failed to close Otto Chrome tab: {e}")

    def _block_nonessential_resources(self, route):
        resource_type = route.request.resource_type
        if resource_type in {"image", "media", "font"}:
            route.abort()
        else:
            route.continue_()

    def _wait_for_product_content(self, page) -> None:
        """Wait for Otto's client-side product content to hydrate."""
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            logger.debug("Otto fallback did not reach networkidle before timeout")

        try:
            page.wait_for_selector(
                ".pdp_short-info__main-name, "
                ".js_pdp_short-info__main-name, "
                "[data-price-cents]",
                timeout=20000,
            )
        except Exception:
            logger.debug("Otto fallback product selectors were not visible before timeout")

        page.wait_for_timeout(3000)

    def _wait_for_required_cookies(self, context, page) -> List[Dict]:
        """Wait until Chrome has created the Otto anti-bot cookies used by direct requests."""
        deadline = time.time() + (settings.OTTO_COOKIE_REQUIRED_WAIT_MS / 1000.0)
        required_cookie_names = set(settings.OTTO_COOKIE_REQUIRED_NAMES)

        while True:
            cookies = context.cookies("https://www.otto.de/")
            otto_cookies = [cookie for cookie in cookies if self._is_otto_cookie(cookie)]
            if self._has_required_cookies(otto_cookies):
                logger.info(
                    "Required Otto cookies are present: "
                    f"{', '.join(sorted(required_cookie_names)) or 'none configured'}"
                )
                return otto_cookies

            if time.time() >= deadline:
                cookie_names = sorted(
                    str(cookie.get("name"))
                    for cookie in otto_cookies
                    if cookie.get("name")
                )
                missing_cookie_names = sorted(required_cookie_names - set(cookie_names))
                raise Exception(
                    "Timed out waiting for required Otto cookies. "
                    f"Missing: {', '.join(missing_cookie_names)}. "
                    f"Present: {', '.join(cookie_names)}"
                )

            page.wait_for_timeout(1000)

    def _build_proxy_config(self, proxy: str) -> Dict[str, str]:
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

    def _safe_proxy_label(self, proxy: Optional[str]) -> Optional[str]:
        if not proxy:
            return None

        parsed = urlparse(proxy)
        if not parsed.scheme or not parsed.hostname:
            return proxy

        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{parsed.hostname}{port}"

    def _persistent_chrome_launch_args(self) -> List[str]:
        return [
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
        ]


otto_cookie_service = OttoCookieService()
