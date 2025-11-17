"""
Configuration for AML service.
"""

import os

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://fintegrate_user:fintegrate_pass@localhost:5435/fintegrate_db")

# RabbitMQ configuration
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "fintegrate_user")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "fintegrate_pass")

# Sanctions configuration
SANCTIONS_DATA_DIR = os.getenv("SANCTIONS_DATA_DIR", "/app/data/sanctions")
SANCTIONS_FILE_PATH = os.path.join(SANCTIONS_DATA_DIR, "eu-list.json")
SANCTIONS_SOURCE_URL = (
    "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw"
)

# Service configuration
SERVICE_NAME = "aml_service"
AML_QUEUE_NAME = "customer_aml_check"
AML_EXCHANGE_NAME = "customer_events"
AML_ROUTING_KEY = "customer.creation.*"
