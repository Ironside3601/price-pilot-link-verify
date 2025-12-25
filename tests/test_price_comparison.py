"""
Unit tests for price comparison logic in Link Verify API.

Tests the price parsing and comparison functionality.
"""

import pytest
from fastapi.testclient import TestClient
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock the Secret Manager before importing link_verify
with patch('google.cloud.secretmanager.SecretManagerServiceClient') as mock_client:
    mock_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.payload.data.decode.return_value = 'fake-secret-value'
    mock_instance.access_secret_version.return_value = mock_response
    mock_client.return_value = mock_instance
    
    from link_verify_api import app, parse_price, compare_prices
    import link_verify
    import link_verify_api

client = TestClient(app)


class TestPriceParser:
    """Test price parsing functionality."""
    
    def test_parse_gbp_price(self):
        """Parse GBP price with pound symbol."""
        assert parse_price("£10.99") == 10.99
        assert parse_price("£100") == 100.0
        assert parse_price("£1,299.99") == 1299.99
    
    def test_parse_usd_price(self):
        """Parse USD price with dollar symbol."""
        assert parse_price("$10.99") == 10.99
        assert parse_price("$100") == 100.0
    
    def test_parse_eur_price(self):
        """Parse EUR price with euro symbol."""
        assert parse_price("€10.99") == 10.99
        assert parse_price("€100") == 100.0
    
    def test_parse_plain_number(self):
        """Parse plain number without currency symbol."""
        assert parse_price("10.99") == 10.99
        assert parse_price("100") == 100.0
    
    def test_parse_with_whitespace(self):
        """Parse price with extra whitespace."""
        assert parse_price("  £10.99  ") == 10.99
        assert parse_price(" 100 ") == 100.0
    
    def test_parse_not_listed(self):
        """Parse 'Not listed' should return None."""
        assert parse_price("Not listed") is None
        assert parse_price("N/A") is None
        assert parse_price("Not available") is None
    
    def test_parse_invalid_input(self):
        """Parse invalid input should return None."""
        assert parse_price("") is None
        assert parse_price(None) is None
        assert parse_price("free") is None
        assert parse_price("abc") is None


class TestPriceComparison:
    """Test price comparison logic."""
    
    def test_compare_lower_price(self):
        """Scraped price lower than Amazon should return 'lower'."""
        result = compare_prices("£10.99", "£15.99")
        assert result['priceComparison'] == 'lower'
        assert result['savings'] == "£5.00"
    
    def test_compare_higher_price(self):
        """Scraped price higher than Amazon should return 'higher'."""
        result = compare_prices("£20.99", "£15.99")
        assert result['priceComparison'] == 'higher'
        assert result['savings'] is None
    
    def test_compare_same_price(self):
        """Scraped price same as Amazon should return 'same'."""
        result = compare_prices("£15.99", "£15.99")
        assert result['priceComparison'] == 'same'
        assert result['savings'] is None
    
    def test_compare_no_amazon_price(self):
        """No Amazon price should return 'unable_to_compare'."""
        result = compare_prices("£10.99", None)
        assert result['priceComparison'] == 'unable_to_compare'
        assert result['savings'] is None
    
    def test_compare_no_scraped_price(self):
        """No scraped price should return 'unable_to_compare'."""
        result = compare_prices("Not listed", "£15.99")
        assert result['priceComparison'] == 'unable_to_compare'
        assert result['savings'] is None
    
    def test_compare_different_currencies(self):
        """Compare different currency formats."""
        result = compare_prices("$10.99", "£15.99")
        assert result['priceComparison'] == 'lower'


class TestVerifyWithPriceComparison:
    """Test verify endpoint with price comparison."""
    
    @pytest.fixture(autouse=True)
    def mock_external_calls(self):
        """Mock link_verify functions to avoid real API calls."""
        with patch.object(link_verify_api, 'fetch_html') as mock_fetch, \
             patch.object(link_verify_api, 'extract_text') as mock_extract, \
             patch.object(link_verify_api, 'find_product_info') as mock_find:
            
            # Mock successful fetch
            mock_fetch.return_value = ('<html>Product page</html>', None)
            mock_extract.return_value = ('Product text content', None)
            mock_find.return_value = ({
                'title': 'Dell XPS 13 Laptop',
                'brand': 'Dell',
                'price': '£899.99',
                'description': 'High-performance laptop',
                'availability': 'In Stock'
            }, None)
            
            yield mock_fetch, mock_extract, mock_find
    
    def test_verify_with_lower_price_is_valid(self):
        """Link with lower price than Amazon should be valid."""
        payload = {
            "url": "https://example.com/product",
            "productTitle": "Dell XPS 13",
            "amazonPrice": "£999.99"
        }
        response = client.post("/verify", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == True
        assert data["priceComparison"] == "lower"
        assert data["savings"] == "£100.00"
        assert data["price"] == "£899.99"
        assert data["amazonPrice"] == "£999.99"
    
    def test_verify_with_higher_price_is_invalid(self, mock_external_calls):
        """Link with higher price than Amazon should be invalid."""
        mock_fetch, mock_extract, mock_find = mock_external_calls
        
        # Override mock to return higher price
        mock_find.return_value = ({
            'title': 'Dell XPS 13 Laptop',
            'brand': 'Dell',
            'price': '£1099.99',
            'description': 'High-performance laptop',
            'availability': 'In Stock'
        }, None)
        
        payload = {
            "url": "https://example.com/product",
            "productTitle": "Dell XPS 13",
            "amazonPrice": "£999.99"
        }
        response = client.post("/verify", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == False
        assert data["priceComparison"] == "higher"
        assert data["savings"] is None
    
    def test_verify_with_same_price_is_invalid(self, mock_external_calls):
        """Link with same price as Amazon should be invalid."""
        mock_fetch, mock_extract, mock_find = mock_external_calls
        
        # Override mock to return same price
        mock_find.return_value = ({
            'title': 'Dell XPS 13 Laptop',
            'brand': 'Dell',
            'price': '£999.99',
            'description': 'High-performance laptop',
            'availability': 'In Stock'
        }, None)
        
        payload = {
            "url": "https://example.com/product",
            "productTitle": "Dell XPS 13",
            "amazonPrice": "£999.99"
        }
        response = client.post("/verify", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == False
        assert data["priceComparison"] == "same"
    
    def test_verify_without_amazon_price_is_valid(self):
        """Link without Amazon price should be valid (can't compare)."""
        payload = {
            "url": "https://example.com/product",
            "productTitle": "Dell XPS 13"
        }
        response = client.post("/verify", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == True
        assert data["priceComparison"] == "unable_to_compare"
        assert data["savings"] is None
    
    def test_verify_with_unparseable_price_is_valid(self, mock_external_calls):
        """Link with unparseable price should be valid (can't compare)."""
        mock_fetch, mock_extract, mock_find = mock_external_calls
        
        # Override mock to return unparseable price
        mock_find.return_value = ({
            'title': 'Dell XPS 13 Laptop',
            'brand': 'Dell',
            'price': 'Not listed',
            'description': 'High-performance laptop',
            'availability': 'In Stock'
        }, None)
        
        payload = {
            "url": "https://example.com/product",
            "productTitle": "Dell XPS 13",
            "amazonPrice": "£999.99"
        }
        response = client.post("/verify", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == True
        assert data["priceComparison"] == "unable_to_compare"
        assert data["savings"] is None
    
    def test_verify_with_backwards_compatible_product_price(self):
        """Test backwards compatibility with productPrice field."""
        payload = {
            "url": "https://example.com/product",
            "productTitle": "Dell XPS 13",
            "productPrice": "£999.99"  # Old field name
        }
        response = client.post("/verify", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == True
        assert data["amazonPrice"] == "£999.99"


class TestBatchVerifyWithPriceComparison:
    """Test batch verify endpoint with price comparison."""
    
    @pytest.fixture(autouse=True)
    def mock_external_calls(self):
        """Mock link_verify functions to avoid real API calls."""
        with patch.object(link_verify_api, 'fetch_html') as mock_fetch, \
             patch.object(link_verify_api, 'extract_text') as mock_extract, \
             patch.object(link_verify_api, 'find_product_info') as mock_find:
            
            # Mock successful fetch
            mock_fetch.return_value = ('<html>Product page</html>', None)
            mock_extract.return_value = ('Product text content', None)
            
            # This will be called multiple times, return different prices
            def find_side_effect(text, title, api_key):
                if "Product 1" in title:
                    return ({
                        'title': 'Product 1',
                        'price': '£50.00',
                        'brand': 'Brand A',
                        'availability': 'In Stock'
                    }, None)
                else:
                    return ({
                        'title': 'Product 2',
                        'price': '£150.00',
                        'brand': 'Brand B',
                        'availability': 'In Stock'
                    }, None)
            
            mock_find.side_effect = find_side_effect
            
            yield mock_fetch, mock_extract, mock_find
    
    def test_batch_verify_with_mixed_prices(self):
        """Batch verify with some valid (lower) and some invalid (higher) prices."""
        payload = {
            "links": [
                {"url": "https://example.com/product1", "productTitle": "Product 1", "amazonPrice": "£100.00"},
                {"url": "https://example.com/product2", "productTitle": "Product 2", "amazonPrice": "£100.00"}
            ]
        }
        response = client.post("/verify-batch", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["totalCount"] == 2
        assert data["validCount"] == 1  # Only Product 1 should be valid (£50 < £100)
        
        # Product 1 should be valid (lower price)
        assert data["results"][0]["valid"] == True
        assert data["results"][0]["priceComparison"] == "lower"
        
        # Product 2 should be invalid (higher price)
        assert data["results"][1]["valid"] == False
        assert data["results"][1]["priceComparison"] == "higher"
