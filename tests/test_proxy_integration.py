"""
Integration tests for proxy-based web scraping.

These tests make REAL network requests through the proxy to verify:
1. Proxy authentication works
2. HTML fetching through proxy succeeds
3. Real retailer websites can be scraped

IMPORTANT: These tests are SKIPPED in CI/CD by default.
Run locally with: pytest tests/test_proxy_integration.py -v -s

ENVIRONMENT VARIABLES REQUIRED:
- PROXY_PASSWORD: The proxy password (set before running tests)
- OPENROUTER_API_KEY: (optional, only needed for LLM tests)

Example:
    export PROXY_PASSWORD="your-password-here"
    pytest tests/test_proxy_integration.py -v -s

The -s flag ensures all logs are printed to stdout.
"""

import pytest
import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging to stdout with detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

from link_verify import fetch_html, extract_text, get_proxy_password, get_proxies


# Mark all tests in this file as integration tests (skip in CI/CD)
pytestmark = pytest.mark.integration


# Check if PROXY_PASSWORD is set before running tests
@pytest.fixture(scope="session", autouse=True)
def check_environment():
    """Verify required environment variables are set."""
    if not os.environ.get("PROXY_PASSWORD"):
        pytest.skip("PROXY_PASSWORD environment variable not set. Set it before running integration tests.")
    print(f"\nPROXY_PASSWORD environment variable is set")


class TestProxyIntegration:
    """Integration tests for proxy functionality with real websites."""
    
    def test_proxy_credentials_loaded(self):
        """Test that proxy password can be loaded from environment variable."""
        print("\n" + "="*80)
        print("TEST: Proxy Credentials Loading")
        print("="*80)
        
        try:
            password = get_proxy_password()
            assert password is not None, "Proxy password should not be None"
            assert len(password) > 0, "Proxy password should not be empty"
            print(f"Successfully loaded proxy password (length: {len(password)})")
            
            proxies = get_proxies()
            assert 'http' in proxies, "Proxies dict should contain 'http' key"
            assert 'https' in proxies, "Proxies dict should contain 'https' key"
            print(f"Proxy configuration built successfully")
            
            # Show proxy format (without password)
            proxy_url = proxies['http']
            # Extract just the format without password
            if '@' in proxy_url:
                parts = proxy_url.split('@')
                host_port = parts[1] if len(parts) > 1 else 'unknown'
                print(f"   Proxy host:port: {host_port}")
                print(f"   Proxy URL format: http://username:***@{host_port}")
            
        except Exception as e:
            pytest.fail(f"Failed to load proxy credentials: {str(e)}")
    
    def test_fetch_simple_page_through_proxy(self):
        """Test fetching a simple page (example.com) through proxy."""
        print("\n" + "="*80)
        print("TEST: Fetch Simple Page (example.com)")
        print("="*80)
        
        url = "http://example.com"
        
        print(f"\nFetching: {url}")
        html_content, error = fetch_html(url, timeout=15, max_retries=2)
        
        if error:
            print(f"Error occurred: {error}")
            pytest.fail(f"Failed to fetch {url}: {error}")
        
        assert html_content is not None, "HTML content should not be None"
        assert len(html_content) > 100, "HTML should have content"
        assert "example" in html_content.lower(), "HTML should contain 'example'"
        
        print(f"Successfully fetched simple page through proxy")
        print(f"   HTML length: {len(html_content):,} characters")
        print(f"   First 200 chars: {html_content[:200]}...")
    
    def test_fetch_john_lewis_product_page(self):
        """Test fetching John Lewis product page through proxy."""
        print("\n" + "="*80)
        print("TEST: Fetch John Lewis Product Page")
        print("="*80)
        
        # Real John Lewis product URL
        url = "https://www.johnlewis.com/john-lewis-partners-egyptian-cotton-400-thread-count-standard-pillowcase-white/p3182352"
        
        print(f"\nFetching: {url}")
        html_content, error = fetch_html(url, timeout=30, max_retries=3)
        
        if error:
            print(f"Error occurred: {error}")
            if "404" in error or "not found" in error.lower():
                pytest.skip(f"Product page not available: {url}")
            pytest.fail(f"Failed to fetch {url}: {error}")
        
        assert html_content is not None, "HTML content should not be None"
        assert len(html_content) > 1000, "HTML should be substantial (>1000 chars)"
        
        print(f"Successfully fetched product page")
        print(f"   HTML length: {len(html_content):,} characters")
        
        # Extract and show text
        text_content, extract_error = extract_text(html_content)
        if text_content:
            print(f"Text extracted: {len(text_content):,} characters")
            print(f"   First 200 chars: {text_content[:200]}...")
    
    def test_fetch_selfridges_product_page(self):
        """Test fetching Selfridges product page through proxy."""
        print("\n" + "="*80)
        print("TEST: Fetch Selfridges Product Page")
        print("="*80)
        
        # Real Selfridges product URL
        url = "https://www.selfridges.com/IT/en/product/this-old-thing-london-pre-loved-chanel-cc-small-double-flap-leather-shoulder-bag_R04574246/#colour=BLACK"
        
        print(f"\nFetching: {url}")
        html_content, error = fetch_html(url, timeout=30, max_retries=3)
        
        if error:
            print(f"Error occurred: {error}")
            if "404" in error or "not found" in error.lower():
                pytest.skip(f"Product page not available: {url}")
            pytest.fail(f"Failed to fetch {url}: {error}")
        
        assert html_content is not None, "HTML content should not be None"
        assert len(html_content) > 1000, "HTML should be substantial (>1000 chars)"
        
        print(f"Successfully fetched product page")
        print(f"   HTML length: {len(html_content):,} characters")
        
        # Extract and show text
        text_content, extract_error = extract_text(html_content)
        if text_content:
            print(f"Text extracted: {len(text_content):,} characters")
            print(f"   First 400 chars:\n{text_content[:400]}...")
    
    def test_fetch_harrods_product_page(self):
        """Test fetching Harrods product page through proxy."""
        print("\n" + "="*80)
        print("TEST: Fetch Harrods Product Page")
        print("="*80)
        
        # Real Harrods product URL
        url = "https://www.harrods.com/en-gb/p/gucci-the-alchemists-garden-the-voice-of-the-snake-eau-de-parfum-100ml-000000000006287836"
        
        print(f"\nFetching: {url}")
        html_content, error = fetch_html(url, timeout=30, max_retries=3)
        
        if error:
            print(f"Error occurred: {error}")
            if "404" in error or "not found" in error.lower():
                pytest.skip(f"Product page not available: {url}")
            pytest.fail(f"Failed to fetch {url}: {error}")
        
        assert html_content is not None, "HTML content should not be None"
        assert len(html_content) > 1000, "HTML should be substantial (>1000 chars)"
        
        print(f"Successfully fetched product page")
        print(f"   HTML length: {len(html_content):,} characters")
        
        # Extract and show text
        text_content, extract_error = extract_text(html_content)
        if text_content:
            print(f"Text extracted: {len(text_content):,} characters")
            print(f"   First 400 chars:\n{text_content[:400]}...")
    
    def test_fetch_marks_spencer_product_page(self):
        """Test fetching Marks & Spencer product page through proxy."""
        print("\n" + "="*80)
        print("TEST: Fetch Marks & Spencer Product Page")
        print("="*80)
        
        # Real M&S product URL
        url = "https://www.marksandspencer.com/pure-cotton-textured-jumper/p/clp60556367"
        
        print(f"\nFetching product page: {url}")
        
        html_content, error = fetch_html(url, timeout=30, max_retries=3)
        
        if error:
            print(f"Error occurred: {error}")
            if "404" in error or "not found" in error.lower():
                pytest.skip(f"Product page not available: {url}")
            else:
                pytest.fail(f"Failed to fetch product page: {error}")
        
        assert html_content is not None
        assert len(html_content) > 1000
        
        print(f"Successfully fetched product page")
        print(f"   HTML length: {len(html_content):,} characters")
        
        # Extract text
        text_content, extract_error = extract_text(html_content)
        
        if text_content:
            print(f"Text extracted: {len(text_content):,} characters")
            print(f"\nSample text content:\n{text_content[:500]}...")

class TestProxyErrorHandling:
    """Test error scenarios with proxy."""
    
    @pytest.mark.integration
    def test_invalid_url_with_proxy(self):
        """Test that invalid URLs fail gracefully even with proxy."""
        print("\n" + "="*80)
        print("TEST: Invalid URL Handling")
        print("="*80)
        
        url = "https://this-website-definitely-does-not-exist-12345678.com"
        
        html_content, error = fetch_html(url, timeout=15, max_retries=2)
        
        assert html_content is None, "Should return None for invalid domain"
        assert error is not None, "Should return an error message"
        
        print(f"Invalid URL handled correctly")
        print(f"   Error message: {error}")
    
    @pytest.mark.integration
    def test_timeout_handling(self):
        """Test timeout handling with very short timeout."""
        print("\n" + "="*80)
        print("TEST: Timeout Handling")
        print("="*80)
        
        url = "https://www.johnlewis.com/john-lewis-partners-egyptian-cotton-400-thread-count-standard-pillowcase-white/p3182352"
        
        # Use very short timeout to force timeout
        html_content, error = fetch_html(url, timeout=1, max_retries=1)
        
        # Could succeed or timeout depending on network speed
        if html_content:
            print(f"Request succeeded despite short timeout (fast network)")
        else:
            assert "timeout" in error.lower() or "failed" in error.lower()
            print(f"Timeout handled correctly")
            print(f"   Error message: {error}")


if __name__ == "__main__":
    """
    Run tests directly with: python tests/test_proxy_integration.py
    Or with pytest: pytest tests/test_proxy_integration.py -v -s
    
    IMPORTANT: Set PROXY_PASSWORD environment variable before running:
        export PROXY_PASSWORD="your-password-here"
        pytest tests/test_proxy_integration.py -v -s
    """
    print("\n" + "="*80)
    print("PROXY INTEGRATION TESTS")
    print("="*80)
    print("\nThese tests make REAL requests through the proxy.")
    
    if not os.environ.get("PROXY_PASSWORD"):
        print("\nERROR: PROXY_PASSWORD environment variable is not set!")
        print("\nPlease set it before running tests:")
        print("    export PROXY_PASSWORD='your-password-here'")
        print("    pytest tests/test_proxy_integration.py -v -s")
        sys.exit(1)
    
    print("PROXY_PASSWORD environment variable is set")
    print("\nRunning tests...\n")
    
    pytest.main([__file__, "-v", "-s", "--tb=short"])
