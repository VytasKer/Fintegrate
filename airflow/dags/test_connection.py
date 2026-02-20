"""
Test DAG to verify Airflow setup and database connectivity.
This DAG runs a simple test every day at midnight.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import logging
import os

# Configure logger
logger = logging.getLogger(__name__)


def test_airflow_setup():
    """Verify Airflow is working correctly."""
    logger.info("=== Airflow Test DAG Execution ===")
    logger.info(f"Execution timestamp: {datetime.now().isoformat()}")
    logger.info("Airflow setup successful!")
    return "SUCCESS"


def test_database_connection():
    """Test connection to fintegrate_db PostgreSQL database."""
    import psycopg2

    try:
        db_host = os.getenv("POSTGRES_HOST", "postgres")
        db_port = int(os.getenv("POSTGRES_PORT", "5432"))
        db_name = os.getenv("POSTGRES_DB", "fintegrate_db")
        db_user = os.getenv("POSTGRES_USER", "fintegrate_user")
        db_password = os.getenv("POSTGRES_PASSWORD")

        # Connect to fintegrate database
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password,
        )
        cursor = conn.cursor()

        # Test query: Count customers
        cursor.execute("SELECT COUNT(*) FROM customers")
        customer_count = cursor.fetchone()[0]

        # Test query: Count consumers
        cursor.execute("SELECT COUNT(*) FROM consumers")
        consumer_count = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        logger.info("✅ Database connection successful!")
        logger.info(f"   Total customers: {customer_count}")
        logger.info(f"   Total consumers: {consumer_count}")

        return {"status": "SUCCESS", "customer_count": customer_count, "consumer_count": consumer_count}

    except Exception as e:
        logger.error(f"❌ Database connection failed: {str(e)}")
        raise


# DAG default arguments
default_args = {
    "owner": "fintegrate",
    "depends_on_past": False,
    "start_date": datetime(2025, 11, 2),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# Define DAG
with DAG(
    "test_connection",
    default_args=default_args,
    description="Test Airflow setup and database connectivity",
    schedule_interval="@daily",  # Runs at midnight every day
    catchup=False,  # Don't backfill historical runs
    tags=["test", "connectivity"],
) as dag:
    # Task 1: Test Airflow setup
    test_setup = PythonOperator(
        task_id="test_airflow_setup",
        python_callable=test_airflow_setup,
    )

    # Task 2: Test database connection
    test_db = PythonOperator(
        task_id="test_database_connection",
        python_callable=test_database_connection,
    )

    # Task dependencies: test_setup runs first, then test_db
    test_setup >> test_db
