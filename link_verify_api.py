"""
Link Verification API - Validates product links and extracts product information.

This FastAPI service accepts links and product information, verifies that the product
can be found on the webpage, and returns JSON with validation status, product title, and price.

Port: 8080
"""

import logging
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from google.cloud import secretmanager

# Import functions from link_verify
from link_verify import fetch_html, extract_text, find_product_info

# =============================================================================
# LOGGING CONFIGURATION (outputs to stdout for Cloud Run)
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION & SECRETS
# =============================================================================

_secrets_cache = {}

def get_secret(secret_name: str) -> str:
    """Retrieve a secret from Google Secret Manager."""
    if secret_name in _secrets_cache:
        return _secrets_cache[secret_name]
    
    try:
        project_id = "price-pilot-1765213055260"
        client = secretmanager.SecretManagerServiceClient()
        resource_name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": resource_name})
        secret_value = response.payload.data.decode("UTF-8")
        _secrets_cache[secret_name] = secret_value
        logger.info(f"Secret '{secret_name}' loaded successfully")
        return secret_value
    except Exception as e:
        logger.error(f"Error retrieving secret '{secret_name}': {str(e)}")
        raise

# Fetch credentials from Secret Manager
try:
    OPENROUTER_API_KEY = get_secret('OPENROUTER_API_KEY')
    logger.info("All secrets loaded from Google Secret Manager")
except Exception as e:
    logger.error(f"Failed to load secrets: {str(e)}")
    raise SystemExit(1)

# =============================================================================
# FASTAPI APP SETUP

app = FastAPI(
    title="Price Pilot Link Verification API",
    description="Validates product links and extracts product information using AI",
    version="1.0.0"
)

# Enable CORS for Chrome extension requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# PYDANTIC MODELS

class VerifyRequest(BaseModel):
    url: str
    productTitle: str
    productBrand: Optional[str] = None
    productPrice: Optional[str] = None  # Deprecated: use amazonPrice instead
    amazonPrice: Optional[str] = None  # Price from Amazon to compare against


class VerifyResponse(BaseModel):
    valid: bool
    url: Optional[str] = None
    productTitle: Optional[str] = None
    price: Optional[str] = None
    brand: Optional[str] = None
    description: Optional[str] = None
    availability: Optional[str] = None
    confidence: Optional[str] = None
    verifiedAt: Optional[str] = None
    error: Optional[str] = None
    errorType: Optional[str] = None  # More specific error categorization
    message: Optional[str] = None
    amazonPrice: Optional[str] = None  # Original Amazon price for comparison
    priceComparison: Optional[str] = None  # 'lower', 'higher', 'same', or 'unable_to_compare'
    savings: Optional[str] = None  # Amount saved if price is lower


class BatchLinkItem(BaseModel):
    url: str
    productTitle: str
    amazonPrice: Optional[str] = None  # Price from Amazon to compare against


class BatchVerifyRequest(BaseModel):
    links: List[BatchLinkItem]


class BatchVerifyResponse(BaseModel):
    results: List[VerifyResponse]
    validCount: int
    totalCount: int


class HealthResponse(BaseModel):
    status: str
    message: str


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def parse_price(price_str: str) -> Optional[float]:
    """
    Parse a price string and return a float value.
    Handles various formats: £10.99, $10.99, 10.99, £10, €10.99, etc.
    
    Args:
        price_str: Price string to parse
        
    Returns:
        Float price value or None if unable to parse
    """
    if not price_str or not isinstance(price_str, str):
        return None
    
    # Remove common currency symbols and whitespace
    cleaned = price_str.strip().replace('£', '').replace('$', '').replace('€', '').replace(',', '')
    
    # Handle cases like "Not listed", "N/A", etc.
    if cleaned.lower() in ['not listed', 'n/a', 'na', 'not available', 'not specified']:
        return None
    
    try:
        # Extract first number that looks like a price
        import re
        match = re.search(r'\d+\.?\d*', cleaned)
        if match:
            return float(match.group())
    except (ValueError, AttributeError):
        pass
    
    return None


def compare_prices(scraped_price_str: str, amazon_price_str: Optional[str]) -> Dict[str, Any]:
    """
    Compare scraped price with Amazon price.
    
    Args:
        scraped_price_str: Price found on the scraped page
        amazon_price_str: Original Amazon price
        
    Returns:
        Dict with comparison results: priceComparison, savings
    """
    scraped_price = parse_price(scraped_price_str)
    amazon_price = parse_price(amazon_price_str) if amazon_price_str else None
    
    result = {
        'priceComparison': 'unable_to_compare',
        'savings': None
    }
    
    # If no Amazon price provided or no scraped price found, can't compare
    if amazon_price is None or scraped_price is None:
        logger.info(f"Unable to compare prices - Amazon: {amazon_price}, Scraped: {scraped_price}")
        return result
    
    # Compare prices
    if scraped_price < amazon_price:
        savings = amazon_price - scraped_price
        result['priceComparison'] = 'lower'
        result['savings'] = f"£{savings:.2f}"
        logger.info(f"Price is lower: Amazon £{amazon_price:.2f} vs Scraped £{scraped_price:.2f} (Saves £{savings:.2f})")
    elif scraped_price > amazon_price:
        result['priceComparison'] = 'higher'
        logger.info(f"Price is higher: Amazon £{amazon_price:.2f} vs Scraped £{scraped_price:.2f}")
    else:
        result['priceComparison'] = 'same'
        logger.info(f"Prices are the same: £{amazon_price:.2f}")
    
    return result


async def verify_single_link(url: str, product_title: str, amazon_price: Optional[str] = None) -> Dict[str, Any]:
    """
    Verify a single product link.
    
    Args:
        url: The product URL to verify
        product_title: The product title to search for
        
    Returns:
        Dict with verification result
    """
    try:
        logger.info(f"Starting verification for: {url}")
        logger.info(f"Looking for product: {product_title[:50]}...")
        
        # Fetch HTML (returns tuple: html_content, error_message)
        html_content, fetch_error = fetch_html(url)
        if not html_content:
            error_msg = fetch_error or 'Failed to fetch URL'
            logger.warning(f"Fetch failed for {url}: {error_msg}")
            return {
                'valid': False,
                'error': error_msg,
                'errorType': 'fetch_error',
                'url': url,
                'productTitle': product_title
            }
        
        logger.info(f"Successfully fetched HTML ({len(html_content)} bytes)")
        
        # Extract text content (returns tuple: text_content, error_message)
        text_content, extract_error = extract_text(html_content)
        if not text_content:
            error_msg = extract_error or 'Failed to extract content from page'
            logger.warning(f"Extract failed for {url}: {error_msg}")
            return {
                'valid': False,
                'error': error_msg,
                'errorType': 'extract_error',
                'url': url,
                'productTitle': product_title
            }
        
        logger.info(f"Extracted text content ({len(text_content)} chars)")
        
        # Search for the product using LLM (returns tuple: product_info, error_message)
        product_info, llm_error = find_product_info(text_content, product_title, OPENROUTER_API_KEY)
        
        if not product_info:
            error_msg = llm_error or 'Product not found on this page'
            logger.warning(f"Product search failed for {url}: {error_msg}")
            return {
                'valid': False,
                'productTitle': product_title,
                'url': url,
                'message': error_msg,
                'errorType': 'product_not_found'
            }
        
        # Product found - extract relevant info
        scraped_price = product_info.get('price', 'Not listed')
        
        # Compare prices if Amazon price is provided
        price_comparison = compare_prices(scraped_price, amazon_price)
        
        # Determine if link is valid based on price comparison
        # Valid if: 1) No Amazon price provided (can't compare), OR 2) Scraped price is lower
        is_valid = True
        if amazon_price and price_comparison['priceComparison'] != 'unable_to_compare':
            # Only valid if scraped price is lower than Amazon price
            is_valid = price_comparison['priceComparison'] == 'lower'
            
            if not is_valid:
                logger.info(f"Link marked as invalid - price is not lower than Amazon ({price_comparison['priceComparison']})")
        else:
            # No price comparison possible - mark as valid but note it in the response
            logger.info("No price comparison performed - marking as valid based on product match only")
        
        response = {
            'valid': is_valid,
            'url': url,
            'productTitle': product_info.get('title', product_title),
            'price': scraped_price,
            'brand': product_info.get('brand', 'N/A'),
            'description': product_info.get('description', ''),
            'availability': product_info.get('availability', 'Not specified'),
            'confidence': 'high' if product_info.get('price', '').lower() != 'not listed' else 'medium',
            'verifiedAt': datetime.utcnow().isoformat() + 'Z',
            'amazonPrice': amazon_price,
            'priceComparison': price_comparison['priceComparison'],
            'savings': price_comparison['savings']
        }
        
        logger.info(f"Product verified: {response['productTitle'][:40]} - {response['price']} (Valid: {is_valid})")
        return response
        
    except Exception as e:
        logger.exception(f"Unexpected error verifying {url}: {str(e)}")
        return {
            'valid': False,
            'error': f'Internal error: {str(e)}',
            'errorType': 'internal_error',
            'url': url
        }


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return {
        'status': 'ok',
        'message': 'Link Verification API is running'
    }


@app.post("/verify", response_model=VerifyResponse)
async def verify_link(request: VerifyRequest):
    """
    Verify if a product can be found on a given URL and if the price is lower than Amazon.
    
    - **url**: The product page URL to verify
    - **productTitle**: The product title to search for
    - **productBrand**: Optional brand name
    - **amazonPrice**: Optional Amazon price to compare against (link only valid if scraped price is lower)
    """
    if not request.url or not request.productTitle:
        raise HTTPException(status_code=400, detail="Missing required fields: url and productTitle")
    
    # Use amazonPrice if provided, fallback to productPrice for backwards compatibility
    amazon_price = request.amazonPrice or request.productPrice
    
    result = await verify_single_link(request.url, request.productTitle, amazon_price)
    return result


@app.post("/verify-batch", response_model=BatchVerifyResponse)
async def verify_batch(request: BatchVerifyRequest):
    """
    Verify multiple links concurrently (up to 10 at a time).
    
    - **links**: Array of objects with url and productTitle
    """
    if not request.links:
        raise HTTPException(status_code=400, detail="No links provided")
    
    logger.info(f"Starting batch verification for {len(request.links)} links (concurrent processing)")
    
    # Limit to 10 concurrent requests
    semaphore = asyncio.Semaphore(10)
    
    async def process_link(link: BatchLinkItem):
        async with semaphore:
            if not link.url or not link.productTitle:
                return {
                    'valid': False,
                    'error': 'Missing url or productTitle',
                    'errorType': 'validation_error',
                    'url': link.url
                }
            return await verify_single_link(link.url, link.productTitle, link.amazonPrice)
    
    # Run all links concurrently
    results = await asyncio.gather(*[process_link(link) for link in request.links])
    
    valid_count = sum(1 for r in results if r.get('valid', False))
    logger.info(f"Batch complete: {valid_count}/{len(results)} links valid")
    
    return {
        'results': results,
        'validCount': valid_count,
        'totalCount': len(results)
    }


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    import uvicorn
    port = int(os.getenv('PORT', 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
