import json
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional
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

    def _refresh_cookies(
        self,
        url: str,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> List[Dict]:
        """Open a short-lived browser session and collect Otto-set cookies."""
        logger.info("Refreshing Otto cookies with Playwright")
        browser = None
        playwright = None
        timeout = settings.BROWSER_PAGE_FETCH_TIMEOUT
        otto_user_agent = user_agent or settings.OTTO_USER_AGENT

        try:
            playwright = sync_playwright().start()
            launch_options = {
                "headless": settings.PLAYWRIGHT_HEADLESS,
                "args": self._chrome_launch_args(),
            }
            if proxy:
                launch_options["proxy"] = self._build_proxy_config(proxy)

            browser = playwright.chromium.launch(**launch_options)
            context = browser.new_context(
                viewport={
                    "width": settings.PLAYWRIGHT_VIEWPORT_WIDTH,
                    "height": settings.PLAYWRIGHT_VIEWPORT_HEIGHT,
                },
                user_agent=otto_user_agent,
                ignore_https_errors=True,
                java_script_enabled=True,
                locale="de-DE",
                timezone_id="Europe/Berlin",
            )
            page = context.new_page()
            page.set_default_timeout(timeout)
            page.set_default_navigation_timeout(timeout)
            page.route("**/*", self._block_nonessential_resources)

            refresh_url = settings.OTTO_COOKIE_REFRESH_URL or "https://www.otto.de/"
            page.goto(refresh_url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_timeout(2000)

            if url and url != refresh_url:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                    page.wait_for_timeout(2000)
                except Exception as e:
                    logger.warning(f"Otto product cookie warm-up navigation failed: {e}")

            cookies = context.cookies("https://www.otto.de/")
            otto_cookies = [cookie for cookie in cookies if self._is_otto_cookie(cookie)]
            valid_cookies = self._filter_valid_cookies(otto_cookies)
            logger.info(f"Collected {len(valid_cookies)} valid Otto cookies")
            return valid_cookies
        finally:
            if browser:
                browser.close()
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
        return self._filter_valid_cookies(cookies)

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

    def _cache_path(self) -> Path:
        return Path(settings.OTTO_COOKIE_CACHE_PATH)

    def _is_otto_cookie(self, cookie: Dict) -> bool:
        domain = str(cookie.get("domain", "")).lstrip(".").lower()
        return domain == "otto.de" or domain.endswith(".otto.de")

    def _block_nonessential_resources(self, route):
        resource_type = route.request.resource_type
        if resource_type in {"image", "media", "font"}:
            route.abort()
        else:
            route.continue_()

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

    def _chrome_launch_args(self) -> List[str]:
        browser_config = settings.get_browser_config("chrome")
        return browser_config.get("args", [])


otto_cookie_service = OttoCookieService()
