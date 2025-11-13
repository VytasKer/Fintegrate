"""
Integration tests for Customer API endpoints.
Tests full request-response flow with database.
"""
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestCustomerEndpoints:
    """Test customer CRUD endpoints."""
    
    def test_create_customer_success(self, client, test_consumer):
        """Verify POST /customer/data creates customer."""
        response = client.post(
            "/customer/data",
            headers={"X-API-Key": test_consumer.plain_api_key},
            json={"name": "Test Corp", "status": "ACTIVE"}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "data" in data
        assert "customer_id" in data["data"]
        assert data["data"]["name"] == "Test Corp"
        assert data["data"]["status"] == "ACTIVE"
    
    def test_create_customer_missing_api_key(self, client):
        """Verify request without API key returns 401."""
        response = client.post(
            "/customer/data",
            json={"name": "Test Corp", "status": "ACTIVE"}
        )
        
        assert response.status_code == 401
    
    def test_get_customer_success(self, client, test_consumer, test_db):
        """Verify GET /customer/data/{id} retrieves customer."""
        # Create customer first
        from services.customer_service import crud
        from services.customer_service.schemas import CustomerCreate
        
        customer_data = CustomerCreate(name="Get Test Corp", status="ACTIVE")
        customer = crud.create_customer(test_db, customer_data, test_consumer.consumer_id)
        test_db.commit()
        
        # Retrieve it
        response = client.get(
            f"/customer/data/{customer.customer_id}",
            headers={"X-API-Key": test_consumer.plain_api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["customer_id"] == str(customer.customer_id)
        assert data["data"]["name"] == "Get Test Corp"
    
    def test_get_customer_not_found(self, client, test_consumer):
        """Verify GET with nonexistent ID returns 404."""
        fake_id = uuid4()
        response = client.get(
            f"/customer/data/{fake_id}",
            headers={"X-API-Key": test_consumer.plain_api_key}
        )
        
        assert response.status_code == 404
        assert response.json()["detail"]["status_name"] == "NOT_FOUND"
    
    def test_delete_customer_success(self, client, test_consumer, test_db):
        """Verify DELETE /customer/data/{id} removes customer."""
        # Create customer first
        from services.customer_service import crud
        from services.customer_service.schemas import CustomerCreate
        
        customer_data = CustomerCreate(name="Delete Test Corp", status="ACTIVE")
        customer = crud.create_customer(test_db, customer_data, test_consumer.consumer_id)
        test_db.commit()
        
        # Delete it
        response = client.delete(
            f"/customer/data/{customer.customer_id}",
            headers={"X-API-Key": test_consumer.plain_api_key}
        )
        
        assert response.status_code == 200
        
        # Verify deleted
        retrieved = crud.get_customer(test_db, customer.customer_id, test_consumer.consumer_id)
        assert retrieved is None
    
    def test_consumer_isolation(self, client, test_db):
        """Verify consumer A cannot access consumer B's customers."""
        from services.customer_service import crud
        from services.customer_service.schemas import CustomerCreate
        import bcrypt
        from services.customer_service.models import Consumer, ConsumerApiKey
        from datetime import datetime
        
        # Create consumer A
        consumer_a_id = uuid4()
        api_key_a = "consumer_a_key_12345"
        hashed_key_a = bcrypt.hashpw(api_key_a.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        consumer_a = Consumer(
            consumer_id=consumer_a_id,
            name="consumer_a",
            status="active",
            created_at=datetime.utcnow()
        )
        test_db.add(consumer_a)
        test_db.add(ConsumerApiKey(
            api_key_id=uuid4(),
            consumer_id=consumer_a_id,
            api_key_hash=hashed_key_a,
            status="active",
            created_at=datetime.utcnow()
        ))
        test_db.commit()
        
        # Create consumer B
        consumer_b_id = uuid4()
        api_key_b = "consumer_b_key_67890"
        hashed_key_b = bcrypt.hashpw(api_key_b.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        consumer_b = Consumer(
            consumer_id=consumer_b_id,
            name="consumer_b",
            status="active",
            created_at=datetime.utcnow()
        )
        test_db.add(consumer_b)
        test_db.add(ConsumerApiKey(
            api_key_id=uuid4(),
            consumer_id=consumer_b_id,
            api_key_hash=hashed_key_b,
            status="active",
            created_at=datetime.utcnow()
        ))
        test_db.commit()
        
        # Create customer for consumer A
        customer_data = CustomerCreate(name="Consumer A Customer", status="ACTIVE")
        customer_a = crud.create_customer(test_db, customer_data, consumer_a_id)
        test_db.commit()
        
        # Consumer B tries to access Consumer A's customer
        response = client.get(
            f"/customer/data/{customer_a.customer_id}",
            headers={"X-API-Key": api_key_b}
        )
        
        assert response.status_code == 404  # Security: returns 404, not 403 (don't reveal existence)


@pytest.mark.integration
class TestEventPublishing:
    """Test event publishing integration."""
    
    def test_customer_creation_publishes_event(self, client, test_consumer, test_db, mock_event_publisher):
        """Verify customer creation publishes event to RabbitMQ."""
        response = client.post(
            "/customer/data",
            headers={"X-API-Key": test_consumer.plain_api_key},
            json={"name": "Event Test Corp", "status": "ACTIVE"}
        )
        
        assert response.status_code == 201
        
        # Verify event published (mocked)
        assert mock_event_publisher.publish_event.called
        call_args = mock_event_publisher.publish_event.call_args
        assert "event_type" in str(call_args) or "customer_creation" in str(call_args)
