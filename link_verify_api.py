"""
Link Verification API - Validates product links and extracts product information.

This FastAPI service accepts links and product information, verifies that the product
can be found on the webpage, and returns JSON with validation status, product title, and price.

Port: 5000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from typing import Optional, List, Dict, Any
from datetime import datetime

# Import functions from link_verify
from link_verify import fetch_html, extract_text, find_product_info

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

# OpenRouter API key for product verification
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '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')


# =============================================================================
# PYDANTIC MODELS

class VerifyRequest(BaseModel):
    url: str
    productTitle: str
    productBrand: Optional[str] = None
    productPrice: Optional[str] = None


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
    message: Optional[str] = None


class BatchLinkItem(BaseModel):
    url: str
    productTitle: str


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

async def verify_single_link(url: str, product_title: str) -> Dict[str, Any]:
    """
    Verify a single product link.
    
    Args:
        url: The product URL to verify
        product_title: The product title to search for
        
    Returns:
        Dict with verification result
    """
    try:
        print(f"Verifying: {url}")
        
        # Fetch HTML
        html_content = fetch_html(url)
        if not html_content:
            return {
                'valid': False,
                'error': 'Failed to fetch URL',
                'url': url,
                'productTitle': product_title
            }
        
        # Extract text content
        text_content = extract_text(html_content)
        if not text_content:
            return {
                'valid': False,
                'error': 'Failed to extract content from page',
                'url': url,
                'productTitle': product_title
            }
        
        # Search for the product using LLM
        product_info = find_product_info(text_content, product_title, OPENROUTER_API_KEY)
        
        if not product_info:
            return {
                'valid': False,
                'productTitle': product_title,
                'url': url,
                'message': 'Product not found on this page'
            }
        
        # Product found - extract relevant info
        response = {
            'valid': True,
            'url': url,
            'productTitle': product_info.get('title', product_title),
            'price': product_info.get('price', 'Not listed'),
            'brand': product_info.get('brand', 'N/A'),
            'description': product_info.get('description', ''),
            'availability': product_info.get('availability', 'Not specified'),
            'confidence': 'high' if product_info.get('price', '').lower() != 'not listed' else 'medium',
            'verifiedAt': datetime.utcnow().isoformat() + 'Z'
        }
        
        print(f"Verified: {response['productTitle'][:40]} - {response['price']}")
        return response
        
    except Exception as e:
        print(f"Error verifying {url}: {str(e)}")
        return {
            'valid': False,
            'error': f'Internal error: {str(e)}',
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
    Verify if a product can be found on a given URL.
    
    - **url**: The product page URL to verify
    - **productTitle**: The product title to search for
    - **productBrand**: Optional brand name
    - **productPrice**: Optional expected price
    """
    if not request.url or not request.productTitle:
        raise HTTPException(status_code=400, detail="Missing required fields: url and productTitle")
    
    result = await verify_single_link(request.url, request.productTitle)
    return result


@app.post("/verify-batch", response_model=BatchVerifyResponse)
async def verify_batch(request: BatchVerifyRequest):
    """
    Verify multiple links in one request.
    
    - **links**: Array of objects with url and productTitle
    """
    if not request.links:
        raise HTTPException(status_code=400, detail="No links provided")
    
    results = []
    
    for link in request.links:
        if not link.url or not link.productTitle:
            results.append({
                'valid': False,
                'error': 'Missing url or productTitle',
                'url': link.url
            })
            continue
        
        result = await verify_single_link(link.url, link.productTitle)
        results.append(result)
    
    valid_count = sum(1 for r in results if r.get('valid', False))
    
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
