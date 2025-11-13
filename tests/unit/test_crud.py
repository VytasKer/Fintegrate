"""
Unit tests for CRUD functions.
Tests core database operations with mocked dependencies.
"""
import pytest
from uuid import uuid4, UUID
from datetime import datetime
from services.customer_service import crud
from services.customer_service.schemas import CustomerCreate


class TestCreateCustomer:
    """Test create_customer function."""
    
    @pytest.mark.unit
    def test_create_customer_returns_customer_object(self, test_db):
        """Verify create_customer returns Customer instance."""
        consumer_id = uuid4()
        customer_data = CustomerCreate(name="Test Corp", status="ACTIVE")
        
        customer = crud.create_customer(test_db, customer_data, consumer_id)
        
        assert customer is not None
        assert customer.name == "Test Corp"
        assert customer.status == "ACTIVE"
        assert customer.consumer_id == consumer_id
    
    @pytest.mark.unit
    def test_create_customer_generates_uuid(self, test_db):
        """Verify customer_id is valid UUID."""
        consumer_id = uuid4()
        customer_data = CustomerCreate(name="Test Corp", status="ACTIVE")
        
        customer = crud.create_customer(test_db, customer_data, consumer_id)
        
        assert isinstance(customer.customer_id, UUID)
    
    @pytest.mark.unit
    def test_create_customer_persists_to_database(self, test_db):
        """Verify customer is actually saved in database."""
        consumer_id = uuid4()
        customer_data = CustomerCreate(name="Persistence Test", status="ACTIVE")
        
        customer = crud.create_customer(test_db, customer_data, consumer_id)
        
        # Retrieve from database
        retrieved = crud.get_customer(test_db, customer.customer_id, consumer_id)
        assert retrieved is not None
        assert retrieved.customer_id == customer.customer_id


class TestGetCustomer:
    """Test get_customer function."""
    
    @pytest.mark.unit
    def test_get_customer_returns_existing_customer(self, test_db):
        """Verify get_customer retrieves existing customer."""
        consumer_id = uuid4()
        customer_data = CustomerCreate(name="Existing Corp", status="ACTIVE")
        created = crud.create_customer(test_db, customer_data, consumer_id)
        
        retrieved = crud.get_customer(test_db, created.customer_id, consumer_id)
        
        assert retrieved is not None
        assert retrieved.customer_id == created.customer_id
        assert retrieved.name == "Existing Corp"
    
    @pytest.mark.unit
    def test_get_customer_returns_none_for_nonexistent(self, test_db):
        """Verify get_customer returns None for nonexistent ID."""
        consumer_id = uuid4()
        fake_id = uuid4()
        
        result = crud.get_customer(test_db, fake_id, consumer_id)
        
        assert result is None
    
    @pytest.mark.unit
    def test_get_customer_enforces_consumer_isolation(self, test_db):
        """Verify consumer can't access other consumer's customers."""
        consumer_a = uuid4()
        consumer_b = uuid4()
        
        customer_data = CustomerCreate(name="Consumer A Customer", status="ACTIVE")
        customer = crud.create_customer(test_db, customer_data, consumer_a)
        
        # Consumer B tries to access Consumer A's customer
        result = crud.get_customer(test_db, customer.customer_id, consumer_b)
        
        assert result is None


class TestDeleteCustomer:
    """Test delete_customer function."""
    
    @pytest.mark.unit
    def test_delete_customer_removes_from_database(self, test_db):
        """Verify delete_customer actually removes record."""
        consumer_id = uuid4()
        customer_data = CustomerCreate(name="To Delete", status="ACTIVE")
        customer = crud.create_customer(test_db, customer_data, consumer_id)
        
        result = crud.delete_customer(test_db, customer.customer_id, consumer_id)
        
        assert result is True
        assert crud.get_customer(test_db, customer.customer_id, consumer_id) is None
    
    @pytest.mark.unit
    def test_delete_customer_returns_false_for_nonexistent(self, test_db):
        """Verify delete_customer returns False for nonexistent ID."""
        consumer_id = uuid4()
        fake_id = uuid4()
        
        result = crud.delete_customer(test_db, fake_id, consumer_id)
        
        assert result is False
    
    @pytest.mark.unit
    def test_delete_customer_enforces_consumer_isolation(self, test_db):
        """Verify consumer can't delete other consumer's customers."""
        consumer_a = uuid4()
        consumer_b = uuid4()
        
        customer_data = CustomerCreate(name="Protected Customer", status="ACTIVE")
        customer = crud.create_customer(test_db, customer_data, consumer_a)
        
        # Consumer B tries to delete Consumer A's customer
        result = crud.delete_customer(test_db, customer.customer_id, consumer_b)
        
        assert result is False
        # Verify customer still exists
        assert crud.get_customer(test_db, customer.customer_id, consumer_a) is not None


class TestUpdateCustomerStatus:
    """Test update_customer_status function."""
    
    @pytest.mark.unit
    def test_update_customer_status_changes_value(self, test_db):
        """Verify status update persists."""
        consumer_id = uuid4()
        customer_data = CustomerCreate(name="Status Test", status="ACTIVE")
        customer = crud.create_customer(test_db, customer_data, consumer_id)
        
        updated = crud.update_customer_status(test_db, customer.customer_id, "SUSPENDED", consumer_id)
        
        assert updated is not None
        assert updated.status == "SUSPENDED"
    
    @pytest.mark.unit
    def test_update_customer_status_enforces_consumer_isolation(self, test_db):
        """Verify consumer can't update other consumer's customers."""
        consumer_a = uuid4()
        consumer_b = uuid4()
        
        customer_data = CustomerCreate(name="Isolated Status Test", status="ACTIVE")
        customer = crud.create_customer(test_db, customer_data, consumer_a)
        
        # Consumer B tries to update Consumer A's customer
        result = crud.update_customer_status(test_db, customer.customer_id, "SUSPENDED", consumer_b)
        
        assert result is None
        # Verify status unchanged
        original = crud.get_customer(test_db, customer.customer_id, consumer_a)
        assert original.status == "ACTIVE"


class TestGenerateApiKey:
    """Test API key generation."""
    
    @pytest.mark.unit
    def test_generate_api_key_returns_string(self):
        """Verify API key is a string."""
        key = crud.generate_api_key()
        
        assert isinstance(key, str)
        assert len(key) > 0
    
    @pytest.mark.unit
    def test_generate_api_key_is_unique(self):
        """Verify multiple calls generate different keys."""
        key1 = crud.generate_api_key()
        key2 = crud.generate_api_key()
        
        assert key1 != key2


class TestHashApiKey:
    """Test API key hashing."""
    
    @pytest.mark.unit
    def test_hash_api_key_returns_consistent_hash(self):
        """Verify same key produces same hash."""
        key = "test_api_key_12345"
        
        hash1 = crud.hash_api_key(key)
        hash2 = crud.hash_api_key(key)
        
        assert hash1 == hash2
    
    @pytest.mark.unit
    def test_hash_api_key_different_keys_different_hashes(self):
        """Verify different keys produce different hashes."""
        key1 = "test_api_key_12345"
        key2 = "test_api_key_67890"
        
        hash1 = crud.hash_api_key(key1)
        hash2 = crud.hash_api_key(key2)
        
        assert hash1 != hash2
