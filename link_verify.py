"""
Link Verification Module - Simple functions for fetching HTML and finding products.
Uses Google Secret Manager for secure credential storage.
"""

import requests
from bs4 import BeautifulSoup
import json
import os
from typing import Optional, Dict
from google.cloud import secretmanager

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
        print(f"Error retrieving secret '{secret_name}': {str(e)}")
        raise


def fetch_html(url: str, timeout: int = 10) -> Optional[str]:
    """
    Fetch HTML content from a URL.
    
    Args:
        url: The website URL to fetch
        timeout: Request timeout in seconds
        
    Returns:
        HTML content as string, or None if failed
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        return response.text
        
    except requests.exceptions.MissingSchema:
        print(f"Error: Invalid URL format - {url}")
        return None
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to {url}")
        return None
    except requests.exceptions.Timeout:
        print(f"Error: Request timed out for {url}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {str(e)}")
        return None


def extract_text(html_content: str) -> Optional[str]:
    """
    Extract text content from HTML.
    
    Args:
        html_content: Raw HTML string
        
    Returns:
        Cleaned text content, or None if failed
    """
    if not html_content:
        return None
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text
    except Exception as e:
        print(f"Error extracting text: {str(e)}")
        return None


def find_product_info(
    page_content: str, 
    product_query: str, 
    api_key: str = None
) -> Optional[Dict[str, str]]:
    """
    Search for a product in page content using OpenRouter LLM.
    Uses fuzzy matching based on brand, product type, and characteristics.
    
    Args:
        page_content: The text content to search in
        product_query: The product title/query to search for
        api_key: OpenRouter API key (optional, uses env var if not provided)
        
    Returns:
        Dictionary with product info (title, price, brand, etc.) or None
    """
    # Fetch API key from Secret Manager if not provided
    if not api_key:
        try:
            api_key = get_secret('OPENROUTER_API_KEY')
        except Exception as e:
            print(f"Failed to retrieve API key from Secret Manager: {str(e)}")
            return None
    
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
        }
        
        payload = {
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}]
        }
        
        print(f"Querying LLM for product: '{product_query[:50]}...'")
        
        response = requests.post(
            base_url,
            headers=headers,
            data=json.dumps(payload),
            timeout=60
        )
        
        response.raise_for_status()
        result = response.json()
        
        # Extract content from response
        if 'choices' not in result or len(result['choices']) == 0:
            print("Error: Unexpected API response format")
            return None
        
        content = result['choices'][0]['message'].get('content', '').strip()
        
        if not content:
            print("Warning: LLM returned empty content")
            return None
        
        if "NOT_FOUND" in content.upper():
            print("Product not found by LLM")
            return None
        
        # Parse response into dictionary
        product_info = {}
        for line in content.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                product_info[key.strip()] = value.strip()
        
        if product_info:
            print(f"Product found: {product_info.get('title', 'Unknown')[:50]}")
            return product_info
        
        print("Failed to parse product info from LLM response")
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"API Error: {str(e)}")
        return None
    except Exception as e:
        print(f"Error processing response: {str(e)}")
        return None
