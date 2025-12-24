"""
Link Verification Module - Simple functions for fetching HTML and finding products.
Uses Google Secret Manager for secure credential storage.
Routes retailer requests through proxy for better reliability.
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import time
import logging
from typing import Optional, Dict, Tuple
from google.cloud import secretmanager

# =============================================================================
# LOGGING CONFIGURATION (visible in Cloud Run)
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# =============================================================================
# PROXY CONFIGURATION
# =============================================================================

# Proxy config - password loaded from Google Secret Manager
PROXY_HOST = 'proxy-jet.io'
PROXY_PORT = '1010'
PROXY_USERNAME = '250724Wn6DD'

_proxy_password_cache = None

def get_proxy_password() -> str:
    """Load proxy password from Google Secret Manager."""
    global _proxy_password_cache
    
    if _proxy_password_cache is not None:
        return _proxy_password_cache
    
    try:
        _proxy_password_cache = get_secret('PROXY_PASSWORD')
        logger.info("✅ Proxy password loaded from Secret Manager")
        return _proxy_password_cache
    except Exception as e:
        logger.error(f"Failed to load proxy password from Secret Manager: {str(e)}")
        raise

def get_proxy_url() -> str:
    """Build the proxy URL with authentication."""
    password = get_proxy_password()
    return f"http://{PROXY_USERNAME}:{password}@{PROXY_HOST}:{PROXY_PORT}"

def get_proxies() -> Dict[str, str]:
    """Get proxy configuration for requests library."""
    proxy_url = get_proxy_url()
    return {
        'http': proxy_url,
        'https': proxy_url
    }

# =============================================================================
# USER AGENTS (rotate for better anti-bot evasion)
# =============================================================================

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
]

import random

def get_random_user_agent() -> str:
    """Get a random user agent for requests."""
    return random.choice(USER_AGENTS)

# =============================================================================
# SECRETS MANAGEMENT
# =============================================================================

# Initialize Secret Manager client
_secrets_cache = {}

def get_secret(secret_name: str) -> str:
    """
    Retrieve a secret from Google Secret Manager.
    Uses caching to avoid repeated API calls.
    
    Args:
        secret_name: Name of the secret (e.g., 'OPENROUTER_API_KEY')
        
    Returns:
        The secret value as a string
    """
    # Return cached value if available
    if secret_name in _secrets_cache:
        return _secrets_cache[secret_name]
    
    try:
        project_id = "price-pilot-1765213055260"
        
        client = secretmanager.SecretManagerServiceClient()
        resource_name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        
        response = client.access_secret_version(request={"name": resource_name})
        secret_value = response.payload.data.decode("UTF-8")
        
        # Cache the secret
        _secrets_cache[secret_name] = secret_value
        
        return secret_value
        
    except Exception as e:
        logger.error(f"Error retrieving secret '{secret_name}': {str(e)}")
        raise


def fetch_html(url: str, timeout: int = 15, max_retries: int = 3) -> Tuple[Optional[str], Optional[str]]:
    """
    Fetch HTML content from a URL through proxy with retry logic.
    
    Args:
        url: The website URL to fetch
        timeout: Request timeout in seconds
        max_retries: Number of retry attempts
        
    Returns:
        Tuple of (HTML content or None, error message or None)
    """
    proxies = get_proxies()
    user_agent = get_random_user_agent()
    
    headers = {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'DNT': '1',
        'Upgrade-Insecure-Requests': '1',
    }
    
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[Attempt {attempt}/{max_retries}] Fetching URL: {url}")
            logger.info(f"Using proxy: {PROXY_HOST}:{PROXY_PORT}")
            
            start_time = time.time()
            response = requests.get(
                url, 
                headers=headers, 
                timeout=timeout,
                proxies=proxies,
                verify=True
            )
            elapsed_time = time.time() - start_time
            
            logger.info(f"Response received: HTTP {response.status_code} in {elapsed_time:.2f}s")
            
            # Check for blocking responses
            if response.status_code == 403:
                last_error = f"HTTP 403 Forbidden - Site may be blocking requests"
                logger.warning(f"[Attempt {attempt}] {last_error}")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                return None, last_error
            
            if response.status_code == 429:
                last_error = f"HTTP 429 Too Many Requests - Rate limited"
                logger.warning(f"[Attempt {attempt}] {last_error}")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                return None, last_error
            
            if response.status_code == 503:
                last_error = f"HTTP 503 Service Unavailable - Site may be down"
                logger.warning(f"[Attempt {attempt}] {last_error}")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                return None, last_error
            
            response.raise_for_status()
            
            # Check if response looks like valid HTML
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                logger.warning(f"Unexpected content type: {content_type}")
            
            html_length = len(response.text)
            logger.info(f"Successfully fetched {html_length} characters of HTML")
            
            return response.text, None
            
        except requests.exceptions.ProxyError as e:
            last_error = f"Proxy connection failed: {str(e)}"
            logger.error(f"[Attempt {attempt}] {last_error}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
                
        except requests.exceptions.SSLError as e:
            last_error = f"SSL/TLS error: {str(e)}"
            logger.error(f"[Attempt {attempt}] {last_error}")
            if attempt < max_retries:
                time.sleep(1)
                continue
                
        except requests.exceptions.MissingSchema:
            last_error = f"Invalid URL format - missing http:// or https://"
            logger.error(f"{last_error}: {url}")
            return None, last_error
            
        except requests.exceptions.ConnectionError as e:
            last_error = f"Connection failed: {str(e)}"
            logger.error(f"[Attempt {attempt}] {last_error}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
                
        except requests.exceptions.Timeout:
            last_error = f"Request timed out after {timeout}s"
            logger.error(f"[Attempt {attempt}] {last_error}")
            if attempt < max_retries:
                time.sleep(1)
                continue
                
        except requests.exceptions.HTTPError as e:
            last_error = f"HTTP error: {str(e)}"
            logger.error(f"[Attempt {attempt}] {last_error}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
                
        except requests.exceptions.RequestException as e:
            last_error = f"Request failed: {str(e)}"
            logger.error(f"[Attempt {attempt}] {last_error}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
    
    logger.error(f"All {max_retries} attempts failed for URL: {url}")
    return None, last_error


def extract_text(html_content: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract text content from HTML.
    
    Args:
        html_content: Raw HTML string
        
    Returns:
        Tuple of (Cleaned text content or None, error message or None)
    """
    if not html_content:
        return None, "No HTML content provided"
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        if not text or len(text) < 100:
            logger.warning(f"Extracted text is very short ({len(text) if text else 0} chars)")
            return text, "Page content appears to be empty or very short"
        
        logger.info(f"Extracted {len(text)} characters of text content")
        return text, None
        
    except Exception as e:
        error_msg = f"Failed to parse HTML: {str(e)}"
        logger.error(error_msg)
        return None, error_msg


def find_product_info(
    page_content: str, 
    product_query: str, 
    api_key: str = None
) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """
    Search for a product in page content using OpenRouter LLM.
    Uses fuzzy matching based on brand, product type, and characteristics.
    NOTE: LLM API calls do NOT go through proxy.
    
    Args:
        page_content: The text content to search in
        product_query: The product title/query to search for
        api_key: OpenRouter API key (optional, uses Secret Manager if not provided)
        
    Returns:
        Tuple of (Dictionary with product info or None, error message or None)
    """
    # Fetch API key from Secret Manager if not provided
    if not api_key:
        try:
            api_key = get_secret('OPENROUTER_API_KEY')
        except Exception as e:
            error_msg = f"Failed to retrieve API key from Secret Manager: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    base_url = "https://openrouter.ai/api/v1/chat/completions"
    model = "openai/gpt-4o"
    
    prompt = f"""You are a product search and extraction assistant. I have text content from a website and need to find a specific product.

PRODUCT TO FIND: "{product_query}"

INSTRUCTIONS:
1. Search through the provided text content for products that match the query
2. Use FUZZY MATCHING: Match based on:
   - Brand name (must match if mentioned in query)
   - Product type (e.g., "laptop", "shoes", "watch")
   - Key characteristics from the product title (color, size, model, features)
   - The product title in the text does NOT need to match exactly
3. Extract all available information about the matching product:
   - Product Title (exact from text)
   - Brand (if found)
   - Price (format: £29.99, $19.99, etc. - include currency symbol)
   - Product Description or key features
   - Availability status (in stock, out of stock, etc.)
   - Any other relevant info (SKU, model number, etc.)
4. Format your response as key-value pairs, one per line:
   title: [product title from text]
   brand: [brand name or N/A]
   price: [price with currency or "Not listed"]
   description: [brief description or key features]
   availability: [in stock/out of stock/etc. or "Not specified"]
   extras: [any other important info or "None"]

If no matching product found, respond with only:
NOT_FOUND

PAGE CONTENT (first 15000 characters):
{page_content[:15000]}
"""
    
    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'HTTP-Referer': 'https://github.com/scrappers',
            'X-Title': 'Product Scraper',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}]
        }
        
        logger.info(f"Querying LLM for product: '{product_query[:50]}...'")
        logger.info(f"Using model: {model} (no proxy)")
        
        start_time = time.time()
        
        # NOTE: No proxy for LLM API calls
        response = requests.post(
            base_url,
            headers=headers,
            json=payload,
            timeout=60
        )
        
        elapsed_time = time.time() - start_time
        logger.info(f"LLM response received in {elapsed_time:.2f}s - HTTP {response.status_code}")
        
        if response.status_code == 401:
            error_msg = "LLM API authentication failed - invalid API key"
            logger.error(error_msg)
            return None, error_msg
        
        if response.status_code == 429:
            error_msg = "LLM API rate limit exceeded"
            logger.error(error_msg)
            return None, error_msg
        
        response.raise_for_status()
        result = response.json()
        
        # Extract content from response
        if 'choices' not in result or len(result['choices']) == 0:
            error_msg = "LLM returned unexpected response format"
            logger.error(error_msg)
            return None, error_msg
        
        content = result['choices'][0]['message'].get('content', '').strip()
        
        if not content:
            error_msg = "LLM returned empty response"
            logger.warning(error_msg)
            return None, error_msg
        
        if "NOT_FOUND" in content.upper():
            logger.info("Product not found by LLM analysis")
            return None, "Product not found on page"
        
        # Parse response into dictionary
        product_info = {}
        for line in content.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                product_info[key.strip()] = value.strip()
        
        if product_info:
            logger.info(f"✅ Product found: {product_info.get('title', 'Unknown')[:50]}")
            return product_info, None
        
        error_msg = "Failed to parse product info from LLM response"
        logger.warning(error_msg)
        return None, error_msg
        
    except requests.exceptions.Timeout:
        error_msg = "LLM API request timed out after 60s"
        logger.error(error_msg)
        return None, error_msg
    except requests.exceptions.RequestException as e:
        error_msg = f"LLM API request failed: {str(e)}"
        logger.error(error_msg)
        return None, error_msg
    except Exception as e:
        error_msg = f"Error processing LLM response: {str(e)}"
        logger.error(error_msg)
        return None, error_msg
