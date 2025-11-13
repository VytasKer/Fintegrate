"""
Pytest configuration and shared fixtures.
"""
import pytest
from sqlalchemy import create_engine, TypeDecorator, CHAR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
import uuid
from datetime import datetime
import os

# Disable PostgreSQL connection during test imports
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from services.customer_service.database import Base
from services.customer_service.models import Consumer, ConsumerApiKey
from services.customer_service.database import get_db
import bcrypt


# UUID type that works with SQLite
class UUID(TypeDecorator):
    """Platform-independent UUID type - uses CHAR(32) for SQLite."""
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PG_UUID())
        else:
            return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return "%.32x" % uuid.UUID(value).int
            else:
                return "%.32x" % value.int

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                value = uuid.UUID(value)
            return value


# Monkey-patch models to use SQLite-compatible UUID
from sqlalchemy.dialects.postgresql import UUID as PG_UUID_Original
import services.customer_service.models as models_module
models_module.UUID = UUID


# Test database URL (use SQLite for speed)
TEST_DATABASE_URL = "sqlite:///./test.db"


@pytest.fixture(scope="function")
def test_engine():
    """Create test database engine."""
    engine = create_engine(
        TEST_DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_db(test_engine):
    """Create test database session."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, 
        autoflush=False, 
        bind=test_engine
    )
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def test_consumer(test_db):
    """Create test consumer with API key."""
    consumer_id = uuid.uuid4()
    api_key = "test_api_key_12345"
    hashed_key = bcrypt.hashpw(api_key.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    consumer = Consumer(
        consumer_id=consumer_id,
        name="test_consumer",
        description="Test consumer for pytest",
        status="active",
        created_at=datetime.utcnow()
    )
    test_db.add(consumer)
    test_db.commit()
    
    api_key_record = ConsumerApiKey(
        api_key_id=uuid.uuid4(),
        consumer_id=consumer_id,
        api_key_hash=hashed_key,
        status="active",
        created_at=datetime.utcnow()
    )
    test_db.add(api_key_record)
    test_db.commit()
    
    # Attach plain API key for test usage
    consumer.plain_api_key = api_key
    return consumer


@pytest.fixture(scope="function")
def client(test_db):
    """Create FastAPI test client with test database."""
    # Import app here to avoid circular dependency
    from services.customer_service.main import app
    
    def override_get_db():
        try:
            yield test_db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture
def mock_event_publisher(mocker):
    """Mock event publisher to avoid RabbitMQ dependency."""
    mock_publisher = mocker.patch('services.shared.event_publisher.EventPublisher')
    mock_instance = mock_publisher.return_value
    mock_instance.publish_event.return_value = True
    return mock_instance
