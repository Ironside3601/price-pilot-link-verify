"""
Unit tests for Link Verify API - Core functionality tests.

Tests the main endpoints and error handling.
"""

import pytest
from fastapi.testclient import TestClient
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock the Secret Manager before importing link_verify
with patch('google.cloud.secretmanager.SecretManagerServiceClient') as mock_client:
    mock_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.payload.data.decode.return_value = 'fake-secret-value'
    mock_instance.access_secret_version.return_value = mock_response
    mock_client.return_value = mock_instance
    
    from link_verify_api import app
    import link_verify
    import link_verify_api

client = TestClient(app)


# Mock external API calls - patch in link_verify_api where functions are imported
@pytest.fixture(autouse=True)
def mock_external_calls():
    """Mock link_verify functions to avoid real API calls and return tuples."""
    with patch.object(link_verify_api, 'fetch_html') as mock_fetch, \
         patch.object(link_verify_api, 'extract_text') as mock_extract, \
         patch.object(link_verify_api, 'find_product_info') as mock_find:
        
        # Mock fetch_html to return tuple (html_content, error_message)
        mock_fetch.return_value = ('''
        <html>
        <head><title>Test Product Page</title></head>
        <body>
            <h1>Dell XPS 13 Laptop</h1>
            <p class="price">£999.99</p>
            <p class="brand">Dell</p>
            <p>In Stock</p>
        </body>
        </html>
        ''', None)
        
        # Mock extract_text to return tuple (text_content, error_message)
        mock_extract.return_value = (
            'Dell XPS 13 Laptop £999.99 Dell In Stock',
            None
        )
        
        # Mock find_product_info to return tuple (product_info, error_message)
        mock_find.return_value = ({
            'title': 'Dell XPS 13 Laptop',
            'brand': 'Dell',
            'price': '£999.99',
            'description': 'High-performance laptop',
            'availability': 'In Stock'
        }, None)
        
        yield mock_fetch, mock_extract, mock_find


class TestHealthCheck:
    """Test health check endpoint."""
    
    def test_health_check(self):
        """Health check should return 200 with status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "message" in data


class TestVerifyEndpoint:
    """Test verify endpoint core functionality."""
    
    def test_verify_with_valid_input(self):
        """Verify with valid input should return 200."""
        payload = {
            "url": "https://example.com/product",
            "productTitle": "Dell XPS 13"
        }
        response = client.post("/verify", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "valid" in data
    
    def test_verify_missing_url(self):
        """Verify without url should fail."""
        payload = {
            "productTitle": "Dell XPS 13"
        }
        response = client.post("/verify", json=payload)
        assert response.status_code == 422
    
    def test_verify_missing_product_title(self):
        """Verify without productTitle should fail."""
        payload = {
            "url": "https://example.com/product"
        }
        response = client.post("/verify", json=payload)
        assert response.status_code == 422
    
    def test_verify_with_optional_fields(self):
        """Verify with optional fields should work."""
        payload = {
            "url": "https://example.com/product",
            "productTitle": "Dell XPS 13",
            "productBrand": "Dell",
            "productPrice": "£999.99"
        }
        response = client.post("/verify", json=payload)
        assert response.status_code == 200
    
    def test_verify_with_special_characters(self):
        """Verify with special characters should work."""
        payload = {
            "url": "https://example.com/product?id=123&ref=test",
            "productTitle": 'Dell XPS 13" @ £999'
        }
        response = client.post("/verify", json=payload)
        assert response.status_code == 200
    
    def test_verify_with_unicode(self):
        """Verify with unicode characters should work."""
        payload = {
            "url": "https://example.com/product",
            "productTitle": "笔记本电脑"
        }
        response = client.post("/verify", json=payload)
        assert response.status_code == 200


class TestBatchVerifyEndpoint:
    """Test batch verify endpoint."""
    
    def test_batch_verify_with_valid_input(self):
        """Batch verify with valid input should return 200."""
        payload = {
            "links": [
                {"url": "https://example.com/product1", "productTitle": "Product 1"},
                {"url": "https://example.com/product2", "productTitle": "Product 2"}
            ]
        }
        response = client.post("/verify-batch", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "validCount" in data
        assert "totalCount" in data
        assert data["totalCount"] == 2
    
    def test_batch_verify_empty_links(self):
        """Batch verify with empty links should fail."""
        payload = {
            "links": []
        }
        response = client.post("/verify-batch", json=payload)
        assert response.status_code == 400
    
    def test_batch_verify_single_link(self):
        """Batch verify with single link should work."""
        payload = {
            "links": [
                {"url": "https://example.com/product", "productTitle": "Test Product"}
            ]
        }
        response = client.post("/verify-batch", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["totalCount"] == 1


class TestErrorHandling:
    """Test error cases."""
    
    def test_invalid_endpoint(self):
        """Invalid endpoint should return 404."""
        response = client.get("/invalid-endpoint")
        assert response.status_code == 404
    
    def test_verify_method_not_allowed(self):
        """GET on /verify should return 405."""
        response = client.get("/verify")
        assert response.status_code == 405
    
    def test_batch_verify_method_not_allowed(self):
        """GET on /verify-batch should return 405."""
        response = client.get("/verify-batch")
        assert response.status_code == 405


class TestFetchErrors:
    """Test fetch error scenarios."""
    
    def test_fetch_error_returns_error_type(self, mock_external_calls):
        """When fetch fails, should return errorType."""
        mock_fetch, mock_extract, mock_find = mock_external_calls
        # Override the default mock to return an error
        mock_fetch.return_value = (None, 'HTTP 403 Forbidden - Site blocked request')
        
        payload = {
            "url": "https://example.com/product",
            "productTitle": "Test Product"
        }
        response = client.post("/verify", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == False
        assert data["errorType"] == "fetch_error"
        assert "403" in data["error"]
    
    def test_extract_error_returns_error_type(self, mock_external_calls):
        """When extract fails, should return errorType."""
        mock_fetch, mock_extract, mock_find = mock_external_calls
        # Override mocks - fetch succeeds but extract fails
        mock_fetch.return_value = ('<html></html>', None)
        mock_extract.return_value = (None, 'Failed to parse HTML - Empty document')
        
        payload = {
            "url": "https://example.com/product",
            "productTitle": "Test Product"
        }
        response = client.post("/verify", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == False
        assert data["errorType"] == "extract_error"
    
    def test_product_not_found_returns_error_type(self, mock_external_calls):
        """When product not found, should return errorType."""
        mock_fetch, mock_extract, mock_find = mock_external_calls
        # Override mocks - fetch and extract succeed but product not found
        mock_fetch.return_value = ('<html>Content</html>', None)
        mock_extract.return_value = ('Some text content', None)
        mock_find.return_value = (None, 'Product not found on page')
        
        payload = {
            "url": "https://example.com/product",
            "productTitle": "Test Product"
        }
        response = client.post("/verify", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == False
        assert data["errorType"] == "product_not_found"
