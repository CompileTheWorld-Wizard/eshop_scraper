from typing import Optional, List, Dict, Any
from app.extractors.base import BaseExtractor
from app.models import ProductInfo
from app.utils import (
    sanitize_text, 
    extract_price_value, 
    parse_url_domain, 
    map_currency_symbol_to_code
)
from bs4 import BeautifulSoup
import json
import re
from app.logging_config import get_logger


class OttoExtractor(BaseExtractor):
    """Otto.de product information extractor"""

    def _get_product_schema(self) -> Dict[str, Any]:
        """Return Otto's server-rendered schema.org Product JSON-LD data."""
        if hasattr(self, "_product_schema"):
            return self._product_schema

        self._product_schema = {}
        schema_scripts = self.soup.select('script[type="application/ld+json"]')

        for script in schema_scripts:
            try:
                raw_json = script.string or script.get_text()
                if not raw_json:
                    continue

                data = json.loads(raw_json.strip())
                candidates = data if isinstance(data, list) else [data]

                for candidate in candidates:
                    if isinstance(candidate, dict) and candidate.get("@type") == "Product":
                        self._product_schema = candidate
                        return self._product_schema
            except Exception as e:
                logger.debug(f"Failed to parse Otto JSON-LD product data: {e}")

        return self._product_schema

    def _parse_number(self, value: Any) -> Optional[float]:
        """Parse Otto numeric values from JSON-LD or visible text."""
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        domain = parse_url_domain(self.url)
        parsed_value = extract_price_value(str(value), domain)
        if parsed_value is not None:
            return parsed_value

        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return None

    def _normalize_image_url(self, image_url: str) -> Optional[str]:
        """Normalize Otto image URLs from JSON-LD or HTML attributes."""
        if not image_url:
            return None

        image_url = image_url.strip()
        if image_url.startswith("//"):
            return "https:" + image_url
        if image_url.startswith("/"):
            return "https://www.otto.de" + image_url
        return image_url
    
    def extract_title(self) -> Optional[str]:
        """Extract product title"""
        product_schema = self._get_product_schema()
        schema_title = product_schema.get("name")
        if schema_title and len(schema_title.strip()) > 5:
            return schema_title.strip()

        title_selectors = [
            '.pdp_short-info__main-name',
            '.js_pdp_short-info__main-name',
            'meta[property="og:title"]',
            'title',
        ]
        
        for selector in title_selectors:
            if selector.startswith("meta"):
                element = self.soup.select_one(selector)
                title = element.get("content") if element else None
            else:
                title = self.find_element_text(selector)
            if title and len(title.strip()) > 5:
                return title.strip()
        return None
    
    def extract_price(self) -> Optional[float]:
        """Extract product price"""
        price_cents_element = self.soup.select_one('.js_pdp_price__tag[data-price-cents]')
        if price_cents_element and price_cents_element.get("data-price-cents"):
            try:
                return int(price_cents_element["data-price-cents"]) / 100
            except (ValueError, TypeError):
                pass

        price_selectors = [
            '.pdp_price__price-parts',
            '.js_pdp_price__retail-price__value_original',
        ]
        
        for selector in price_selectors:
            price = self.extract_price_value(selector)
            if price:
                return price

        product_schema = self._get_product_schema()
        offers = product_schema.get("offers") if product_schema else {}
        if isinstance(offers, dict):
            schema_price = self._parse_number(offers.get("price"))
            if schema_price:
                return schema_price
        return None
    
    def extract_currency(self) -> Optional[str]:
        """Extract product currency"""
        product_schema = self._get_product_schema()
        offers = product_schema.get("offers") if product_schema else {}
        if isinstance(offers, dict) and offers.get("priceCurrency"):
            return offers["priceCurrency"]

        currency_selectors = [
            '.pdp_price__price-parts',
        ]
        
        for selector in currency_selectors:
            currency_text = self.find_element_text(selector)
            if currency_text:
                # Handle Unicode escape sequences
                if r'\u20ac' in currency_text:
                    currency_text = currency_text.replace(r'\u20ac', '€')
                
                # Use the existing utility function to map currency symbol to code
                currency = map_currency_symbol_to_code(currency_text, parse_url_domain(self.url))
                if currency:
                    return currency
        
        # If no currency found, default to EUR for Otto.de
        return "EUR"
    
    def extract_description(self) -> Optional[str]:
        """Extract product description"""
        product_schema = self._get_product_schema()
        schema_description = product_schema.get("description")
        if schema_description:
            description = BeautifulSoup(schema_description, "html.parser").get_text(" ", strip=True)
            if description and len(description) > 10:
                return sanitize_text(description)

        description_parts = []
        
        # Get main description
        description_selectors = [
            '.js_pdp_description',
            '.pdp_description',
            '.product-description'
        ]
        
        for selector in description_selectors:
            desc = self.find_element_text(selector)
            if desc and len(desc.strip()) > 10:
                description_parts.append(desc.strip())
                break
        
        # Get selling points
        selling_points_selectors = [
            '.pdp_selling-points',
            '.js_pdp_selling-points',
        ]
        
        for selector in selling_points_selectors:
            selling_points = self.find_element_text(selector)
            if selling_points and len(selling_points.strip()) > 10:
                description_parts.append(selling_points.strip())
                break
        
        # Merge all description parts
        if description_parts:
            return '\n\n'.join(description_parts)
        
        return None
    
    def extract_images(self) -> List[str]:
        """Extract product images"""
        product_schema = self._get_product_schema()
        schema_images = product_schema.get("image")
        if isinstance(schema_images, str):
            schema_images = [schema_images]

        images = []
        if isinstance(schema_images, list):
            for image_url in schema_images:
                normalized_url = self._normalize_image_url(str(image_url))
                if normalized_url and normalized_url not in images:
                    images.append(normalized_url)

        if images:
            return images

        image_selectors = [
            'div.js_pdp_main-image__slide',
            'li.js_pdp_alternate-images__thumbnail',
            'meta[property="og:image"]',
            'meta[name="twitter:image"]',
        ]
        
        for selector in image_selectors:
            image_elements = self.soup.select(selector)
            
            for element in image_elements:
                if selector.startswith("meta"):
                    image_src = self._normalize_image_url(element.get("content"))
                    if image_src and image_src not in images:
                        images.append(image_src)
                    continue

                # Try to get image from data-image-id attribute first
                image_id = element.get('data-image-id')
                if image_id:
                    image_src = f"https://i.otto.de/i/otto/{image_id}"
                    if image_src not in images:
                        images.append(image_src)
                    continue
                
                # Try to get image from src attribute
                image_src = self._normalize_image_url(element.get('src'))
                if image_src:
                    if image_src not in images:
                        images.append(image_src)
                
                # Try to get image from data-src attribute (lazy loading)
                data_src = self._normalize_image_url(element.get('data-src'))
                if data_src:
                    if data_src not in images:
                        images.append(data_src)
        
        return images
    
    def extract_rating(self) -> Optional[float]:
        """Extract product rating"""
        product_schema = self._get_product_schema()
        aggregate_rating = product_schema.get("aggregateRating") if product_schema else {}
        if isinstance(aggregate_rating, dict):
            schema_rating = self._parse_number(aggregate_rating.get("ratingValue"))
            if schema_rating:
                return schema_rating

        rating_selectors = [
            '.pdp_cr-rating-score',
            '.js_pdp_cr-rating-score',
        ]
        
        for selector in rating_selectors:
            rating = self.extract_rating_from_element(selector)
            if rating:
                return rating
        return None
    
    def extract_review_count(self) -> Optional[int]:
        """Extract review count"""
        product_schema = self._get_product_schema()
        aggregate_rating = product_schema.get("aggregateRating") if product_schema else {}
        if isinstance(aggregate_rating, dict):
            schema_review_count = self._parse_number(aggregate_rating.get("reviewCount"))
            if schema_review_count is not None:
                return int(schema_review_count)

        review_selectors = [
            '.js_pdp_cr-rating--review-count',
        ]
        
        for selector in review_selectors:
            review_text = self.find_element_text(selector)
            if review_text:
                # Extract number from text like "123 Bewertungen" or "123 reviews"
                review_count = self.extract_number_from_text(review_text)
                if review_count:
                    return review_count
        return None
    
    def extract_specifications(self) -> Dict[str, Any]:
        """Extract product specifications"""
        specs = {}
        product_schema = self._get_product_schema()

        if product_schema:
            schema_fields = {
                "Brand": product_schema.get("brand", {}).get("name") if isinstance(product_schema.get("brand"), dict) else product_schema.get("brand"),
                "SKU": product_schema.get("sku"),
                "GTIN13": product_schema.get("gtin13"),
            }

            offers = product_schema.get("offers")
            if isinstance(offers, dict):
                schema_fields["Availability"] = offers.get("availability")

            for key, value in schema_fields.items():
                if value:
                    specs[key] = sanitize_text(str(value))
        
        # Find all tables within the characteristics container
        spec_tables = self.soup.select('.pdp_details__characteristics-html table')
        
        for table in spec_tables:
            # Get all rows from each table
            rows = table.select('tr')
            
            for row in rows:
                # Key is in td with .left class, value is in regular td
                key_elem = row.select_one('td.left')
                cells = row.select('td')
                value_elem = row.select_one('td:not(.left)')
                if key_elem and value_elem == key_elem and len(cells) > 1:
                    value_elem = cells[1]
                
                if key_elem and value_elem:
                    key = sanitize_text(key_elem.get_text())
                    value = sanitize_text(value_elem.get_text())
                    if key and value:
                        specs[key] = value
                elif row.name == 'li':
                    # Handle list items as features
                    text = sanitize_text(row.get_text())
                    if text and len(text) > 3:
                        specs[f"Feature {len(specs) + 1}"] = text
        
        return specs 