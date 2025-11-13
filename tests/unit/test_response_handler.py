"""
Unit tests for response_handler module.
Tests the standard response format structure.
"""
import pytest
from services.shared.response_handler import success_response, error_response


class TestSuccessResponse:
    """Test success_response function."""
    
    def test_success_response_structure(self):
        """Verify success response has correct structure."""
        data = {"customer_id": "123", "name": "Test Corp"}
        response = success_response(data, 200)
        
        assert "data" in response
        assert "detail" in response
        assert response["data"] == data
    
    def test_success_response_detail_fields(self):
        """Verify detail section has all required fields."""
        response = success_response({}, 200)
        detail = response["detail"]
        
        assert "status_code" in detail
        assert "status_name" in detail
        assert "status_description" in detail
    
    def test_success_response_200_ok(self):
        """Verify 200 status code returns OK."""
        response = success_response({}, 200)
        
        assert response["detail"]["status_code"] == "200"
        assert response["detail"]["status_name"] == "OK"
        assert response["detail"]["status_description"] == "Success"
    
    def test_success_response_201_created(self):
        """Verify 201 status code returns Created."""
        response = success_response({"id": "123"}, 201)
        
        assert response["detail"]["status_code"] == "201"
        assert response["detail"]["status_name"] == "CREATED"
        assert response["detail"]["status_description"] == "Success"
    
    def test_success_response_empty_data(self):
        """Verify empty data dict is valid."""
        response = success_response({}, 200)
        
        assert response["data"] == {}
        assert response["detail"]["status_code"] == "200"


class TestErrorResponse:
    """Test error_response function."""
    
    def test_error_response_structure(self):
        """Verify error response has correct structure."""
        response = error_response(404, "Customer not found")
        
        assert "data" in response
        assert "detail" in response
        assert response["data"] == {}
    
    def test_error_response_404_not_found(self):
        """Verify 404 error format."""
        description = "Customer not found"
        response = error_response(404, description)
        
        assert response["detail"]["status_code"] == "404"
        assert response["detail"]["status_name"] == "NOT_FOUND"
        assert response["detail"]["status_description"] == description
    
    def test_error_response_400_bad_request(self):
        """Verify 400 error format."""
        description = "Invalid customer data"
        response = error_response(400, description)
        
        assert response["detail"]["status_code"] == "400"
        assert response["detail"]["status_name"] == "BAD_REQUEST"
        assert response["detail"]["status_description"] == description
    
    def test_error_response_500_server_error(self):
        """Verify 500 error format."""
        description = "Database connection failed"
        response = error_response(500, description)
        
        assert response["detail"]["status_code"] == "500"
        assert response["detail"]["status_name"] == "INTERNAL_SERVER_ERROR"
        assert response["detail"]["status_description"] == description
    
    def test_error_response_custom_description(self):
        """Verify custom error description is preserved."""
        custom_msg = "Custom error message with details"
        response = error_response(422, custom_msg)
        
        assert response["detail"]["status_description"] == custom_msg
