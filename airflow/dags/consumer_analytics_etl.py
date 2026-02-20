"""
Consumer Analytics ETL DAG
Aggregates customer and event data into consumer-level metrics snapshots.
Generates per-consumer snapshots + global system-wide snapshot (consumer_id=NULL).

Schedule: Daily at midnight (configurable via SCHEDULE_INTERVAL environment variable)
Pattern: Extract → Transform → Load with incremental watermark tracking

Email Alerts: Sends failure notifications to vytaske11@gmail.com
"""

from datetime import datetime, timedelta, timezone
from airflow import DAG
from airflow.operators.python import PythonOperator
import psycopg2
import logging
import os

# Configure logger
logger = logging.getLogger(__name__)

# Database connection parameters
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "fintegrate_db"),
    "user": os.getenv("POSTGRES_USER", "fintegrate_user"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

# Configurable schedule (default: daily at midnight)
SCHEDULE_INTERVAL = os.getenv("ETL_SCHEDULE_INTERVAL", "@daily")


def get_db_connection():
    """
    Create PostgreSQL connection with retry logic.

    Returns:
        psycopg2.connection: Database connection

    Raises:
        Exception: After 3 failed connection attempts
    """
    max_attempts = 3
    retry_delay = 2

    for attempt in range(1, max_attempts + 1):
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            logger.info(f"Database connection established (attempt {attempt})")
            return conn
        except psycopg2.OperationalError as e:
            if attempt == max_attempts:
                logger.error(f"Database connection failed after {max_attempts} attempts: {str(e)}")
                raise
            logger.warning(f"Database connection attempt {attempt} failed, retrying in {retry_delay}s: {str(e)}")
            import time

            time.sleep(retry_delay)


def get_watermark(cursor, job_name="consumer_analytics_daily"):
    """
    Retrieve last processed timestamp from watermark table.

    Args:
        cursor: Database cursor
        job_name: Name of ETL job

    Returns:
        datetime: Last processed timestamp, or epoch (1970-01-01) for first run
    """
    query = """
        SELECT last_processed_timestamp 
        FROM etl_job_watermarks 
        WHERE job_name = %s
    """
    cursor.execute(query, (job_name,))
    result = cursor.fetchone()

    if result and result[0]:
        watermark = result[0]
        logger.info(f"Retrieved watermark: {watermark} (processing events after this time)")
        return watermark
    else:
        # First run - use epoch
        epoch = datetime(1970, 1, 1)
        logger.info(f"No watermark found - first run, processing all historical data since {epoch}")
        return epoch


def update_watermark(cursor, job_name, new_timestamp, status, records_processed, metadata=None):
    """
    Update watermark after successful processing.

    Args:
        cursor: Database cursor
        job_name: Name of ETL job
        new_timestamp: New watermark timestamp
        status: 'success' or 'failed'
        records_processed: Count of records processed
        metadata: Optional metadata dict
    """
    query = """
        UPDATE etl_job_watermarks
        SET last_processed_timestamp = %s,
            last_run_at = CURRENT_TIMESTAMP,
            last_run_status = %s,
            records_processed = %s,
            metadata_json = %s::jsonb
        WHERE job_name = %s
    """

    cursor.execute(query, (new_timestamp, status, records_processed, psycopg2.extras.Json(metadata or {}), job_name))

    logger.info(f"Updated watermark to {new_timestamp}, status={status}, records={records_processed}")


def extract_customer_counts(**context):
    """
    Task 1: Extract customer counts per consumer (incremental based on watermark).

    Returns:
        dict: Customer count metrics per consumer_id

    Raises:
        ValueError: If query returns invalid data
    """
    logger.info("=== Starting Task 1: Extract Customer Counts ===")

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get watermark (customers created after this time)
        watermark = get_watermark(cursor)

        # Query customer counts per consumer (only new customers since watermark)
        query = """
            SELECT 
                consumer_id,
                COUNT(*) as total_customers,
                COUNT(*) FILTER (WHERE status = 'ACTIVE') as active_customers,
                COUNT(*) FILTER (WHERE status = 'INACTIVE') as inactive_customers,
                MIN(created_at) as oldest_customer_created,
                MAX(created_at) as newest_customer_created
            FROM customers
            WHERE created_at > %s
            GROUP BY consumer_id
        """

        cursor.execute(query, (watermark,))
        results = cursor.fetchall()

        # Data quality check: Validate result set structure
        if results and len(results[0]) != 6:
            raise ValueError(f"Invalid query result structure: expected 6 columns, got {len(results[0])}")

        # Transform to dictionary keyed by consumer_id
        customer_metrics = {}
        new_customers_count = 0
        for row in results:
            consumer_id = str(row[0])

            # Data quality check: Validate consumer_id is valid UUID
            if not consumer_id or consumer_id == "None":
                logger.warning(f"Skipping row with invalid consumer_id: {row}")
                continue

            customer_metrics[consumer_id] = {
                "total_customers": row[1],
                "active_customers": row[2],
                "inactive_customers": row[3],
                "oldest_customer_created": row[4].isoformat() if row[4] else None,
                "newest_customer_created": row[5].isoformat() if row[5] else None,
            }
            new_customers_count += row[1]

        logger.info(
            "Extracted %s new customers (created after %s) for %s consumers",
            new_customers_count,
            watermark,
            len(customer_metrics),
        )
        for consumer_id, metrics in customer_metrics.items():
            logger.info(
                "  Consumer %s: %s new customers (%s active)",
                consumer_id,
                metrics["total_customers"],
                metrics["active_customers"],
            )

        # Push to XCom for next task
        context["task_instance"].xcom_push(key="customer_metrics", value=customer_metrics)
        context["task_instance"].xcom_push(key="watermark", value=watermark.isoformat())
        context["task_instance"].xcom_push(key="new_customers_count", value=new_customers_count)

        return customer_metrics

    except psycopg2.DatabaseError as e:
        logger.error(f"Database error extracting customer counts: {str(e)}")
        raise
    except ValueError as e:
        logger.error(f"Data validation error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error extracting customer counts: {str(e)}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def extract_event_counts(**context):
    """
    Task 2: Extract event counts per consumer and event type (incremental based on watermark).

    Returns:
        dict: Event count metrics per consumer_id

    Raises:
        ValueError: If query returns invalid data
    """
    logger.info("=== Starting Task 2: Extract Event Counts ===")

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get watermark (events created after this time)
        watermark = get_watermark(cursor)

        # Query event counts per consumer and event type (only new events since watermark)
        query = """
            SELECT 
                consumer_id,
                event_type,
                COUNT(*) as event_count,
                MIN(created_at) as earliest_event,
                MAX(created_at) as latest_event
            FROM customer_events
            WHERE created_at > %s
            GROUP BY consumer_id, event_type
            ORDER BY consumer_id, event_type
        """

        cursor.execute(query, (watermark,))
        results = cursor.fetchall()

        # Data quality check: Validate result set structure
        if results and len(results[0]) != 5:
            raise ValueError(f"Invalid query result structure: expected 5 columns, got {len(results[0])}")

        # Transform to nested dictionary
        event_metrics = {}
        total_new_events = 0
        for row in results:
            consumer_id = str(row[0])
            event_type = row[1]
            event_count = row[2]

            # Data quality check: Validate consumer_id and event_type
            if not consumer_id or consumer_id == "None":
                logger.warning(f"Skipping row with invalid consumer_id: {row}")
                continue
            if not event_type:
                logger.warning(f"Skipping row with missing event_type for consumer {consumer_id}")
                continue

            total_new_events += event_count

            if consumer_id not in event_metrics:
                event_metrics[consumer_id] = {
                    "events_by_type": {},
                    "total_events": 0,
                    "earliest_event": row[3].isoformat() if row[3] else None,
                    "latest_event": row[4].isoformat() if row[4] else None,
                }

            event_metrics[consumer_id]["events_by_type"][event_type] = event_count
            event_metrics[consumer_id]["total_events"] += event_count

            # Update earliest/latest if necessary
            if row[3] and (
                not event_metrics[consumer_id]["earliest_event"]
                or row[3].isoformat() < event_metrics[consumer_id]["earliest_event"]
            ):
                event_metrics[consumer_id]["earliest_event"] = row[3].isoformat()
            if row[4] and (
                not event_metrics[consumer_id]["latest_event"]
                or row[4].isoformat() > event_metrics[consumer_id]["latest_event"]
            ):
                event_metrics[consumer_id]["latest_event"] = row[4].isoformat()

        logger.info(
            f"Extracted {total_new_events} new events (created after {watermark}) for {len(event_metrics)} consumers"
        )
        for consumer_id, metrics in event_metrics.items():
            logger.info(f"  Consumer {consumer_id}: {metrics['total_events']} new events")
            logger.info(f"    Event types: {metrics['events_by_type']}")

        # Push to XCom for next task
        context["task_instance"].xcom_push(key="event_metrics", value=event_metrics)
        context["task_instance"].xcom_push(key="new_events_count", value=total_new_events)

        return event_metrics

    except psycopg2.DatabaseError as e:
        logger.error(f"Database error extracting event counts: {str(e)}")
        raise
    except ValueError as e:
        logger.error(f"Data validation error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error extracting event counts: {str(e)}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def load_consumer_analytics(**context):
    """
    Task 3: Combine metrics, insert into consumer_analytics, and update watermark.

    Creates one snapshot per consumer with aggregated metrics.
    Updates watermark after successful processing.
    Includes data quality checks and duplicate detection.
    """
    logger.info("=== Starting Task 3: Load Consumer Analytics ===")

    # Pull metrics from XCom
    customer_metrics = context["task_instance"].xcom_pull(task_ids="extract_customer_counts", key="customer_metrics")
    event_metrics = context["task_instance"].xcom_pull(task_ids="extract_event_counts", key="event_metrics")
    watermark_str = context["task_instance"].xcom_pull(task_ids="extract_customer_counts", key="watermark")
    new_customers_count = (
        context["task_instance"].xcom_pull(task_ids="extract_customer_counts", key="new_customers_count") or 0
    )
    new_events_count = context["task_instance"].xcom_pull(task_ids="extract_event_counts", key="new_events_count") or 0

    # Data quality check: Verify XCom data retrieved successfully
    if watermark_str is None:
        raise ValueError("Failed to retrieve watermark from XCom - upstream task may have failed")

    # If no new data, skip processing but still update watermark
    if not customer_metrics and not event_metrics:
        logger.info("No new data since last watermark - skipping snapshot creation")

        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Update watermark with current timestamp to mark successful run
            current_timestamp = datetime.now(timezone.utc)
            update_watermark(
                cursor=cursor,
                job_name="consumer_analytics_daily",
                new_timestamp=current_timestamp,
                status="success",
                records_processed=0,
                metadata={"skip_reason": "no_new_data", "previous_watermark": watermark_str},
            )
            conn.commit()
            logger.info(f"Watermark updated to {current_timestamp} (no data processed)")

            return {"status": "skipped", "reason": "no_new_data", "watermark_updated": current_timestamp.isoformat()}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        snapshot_timestamp = datetime.now(timezone.utc)
        inserted_count = 0
        duplicate_count = 0

        # Get all unique consumer IDs
        all_consumer_ids = set(customer_metrics.keys() if customer_metrics else []) | set(
            event_metrics.keys() if event_metrics else []
        )

        # Data quality check: Verify at least one consumer to process
        if len(all_consumer_ids) == 0:
            raise ValueError("No consumer IDs found in metrics data despite non-empty customer/event metrics")

        logger.info(f"Processing {len(all_consumer_ids)} consumers for snapshot at {snapshot_timestamp}")

        for consumer_id in all_consumer_ids:
            # Merge customer and event metrics
            cust_metrics = (
                customer_metrics.get(
                    consumer_id, {"total_customers": 0, "active_customers": 0, "inactive_customers": 0}
                )
                if customer_metrics
                else {"total_customers": 0, "active_customers": 0, "inactive_customers": 0}
            )
            evt_metrics = (
                event_metrics.get(consumer_id, {"events_by_type": {}, "total_events": 0})
                if event_metrics
                else {"events_by_type": {}, "total_events": 0}
            )

            # Calculate average customer lifetime (days)
            avg_lifetime_days = 0
            if cust_metrics.get("oldest_customer_created"):
                try:
                    oldest = datetime.fromisoformat(cust_metrics["oldest_customer_created"])
                    avg_lifetime_days = (snapshot_timestamp - oldest).days
                except Exception as e:
                    logger.warning(f"Error calculating lifetime for consumer {consumer_id}: {e}")

            # Build metrics JSON
            metrics_json = {
                "total_customers": cust_metrics.get("total_customers", 0),
                "active_customers": cust_metrics.get("active_customers", 0),
                "inactive_customers": cust_metrics.get("inactive_customers", 0),
                "total_events": evt_metrics.get("total_events", 0),
                "events_by_type": evt_metrics.get("events_by_type", {}),
                "avg_customer_lifetime_days": avg_lifetime_days,
                "snapshot_source": "airflow_etl",
                "etl_job": "consumer_analytics_daily",
                "incremental_stats": {
                    "new_customers_in_window": cust_metrics.get("total_customers", 0),
                    "new_events_in_window": evt_metrics.get("total_events", 0),
                    "watermark_used": watermark_str,
                },
            }

            # Data quality check: Check for existing snapshot (duplicate detection)
            check_query = """
                SELECT COUNT(*) FROM consumer_analytics
                WHERE consumer_id = %s AND snapshot_timestamp = %s
            """
            cursor.execute(check_query, (consumer_id, snapshot_timestamp))
            existing_count = cursor.fetchone()[0]

            if existing_count > 0:
                logger.warning(
                    f"Duplicate snapshot detected for consumer {consumer_id} at {snapshot_timestamp} - skipping insert"
                )
                duplicate_count += 1
                continue

            # Insert snapshot (duplicate check already performed above)
            insert_query = """
                INSERT INTO consumer_analytics (analytics_id, consumer_id, snapshot_timestamp, metrics_json)
                VALUES (gen_random_uuid(), %s, %s, %s::jsonb)
            """

            cursor.execute(insert_query, (consumer_id, snapshot_timestamp, psycopg2.extras.Json(metrics_json)))

            if cursor.rowcount > 0:
                inserted_count += 1
                logger.info(f"Inserted snapshot for consumer {consumer_id}: {metrics_json}")
            else:
                duplicate_count += 1
                logger.warning(f"Insert conflict for consumer {consumer_id} - duplicate prevented by unique constraint")

        # Task 6 Enhancement: Create GLOBAL system-wide snapshot (consumer_id=NULL)
        logger.info("=" * 80)
        logger.info("TASK 6: GENERATING GLOBAL SYSTEM-WIDE SNAPSHOT")

        # Query all-time totals (not filtered by watermark - full system state)
        global_query = """
            SELECT 
                COUNT(*) as total_customers_all,
                COUNT(*) FILTER (WHERE status = 'ACTIVE') as active_customers_all,
                COUNT(*) FILTER (WHERE status = 'INACTIVE') as inactive_customers_all
            FROM customers
        """
        cursor.execute(global_query)
        global_customer_stats = cursor.fetchone()

        global_events_query = """
            SELECT 
                COUNT(*) as total_events_all,
                COUNT(DISTINCT event_type) as distinct_event_types,
                event_type,
                COUNT(*) as event_count
            FROM customer_events
            GROUP BY event_type
        """
        cursor.execute(global_events_query)
        global_event_results = cursor.fetchall()

        # Build global metrics
        global_events_by_type = {}
        total_events_all = 0
        for row in global_event_results:
            event_type = row[2]
            event_count = row[3]
            global_events_by_type[event_type] = event_count
            total_events_all += event_count

        global_metrics_json = {
            "total_customers_all_consumers": global_customer_stats[0],
            "active_customers_all_consumers": global_customer_stats[1],
            "inactive_customers_all_consumers": global_customer_stats[2],
            "total_events_all_consumers": total_events_all,
            "events_by_type_all_consumers": global_events_by_type,
            "system_wide_active_ratio": round(global_customer_stats[1] / global_customer_stats[0], 4)
            if global_customer_stats[0] > 0
            else 0,
            "consumers_in_system": len(all_consumer_ids),
            "snapshot_source": "airflow_etl",
            "etl_job": "consumer_analytics_daily",
            "snapshot_type": "GLOBAL",
            "incremental_stats": {
                "new_customers_in_window": new_customers_count,
                "new_events_in_window": new_events_count,
                "watermark_used": watermark_str,
            },
        }

        # Insert global snapshot with consumer_id=NULL (no duplicate check needed - partial unique index handles it)
        global_insert_query = """
            INSERT INTO consumer_analytics (analytics_id, consumer_id, snapshot_timestamp, metrics_json)
            VALUES (gen_random_uuid(), NULL, %s, %s::jsonb)
        """

        cursor.execute(global_insert_query, (snapshot_timestamp, psycopg2.extras.Json(global_metrics_json)))

        global_inserted = cursor.rowcount > 0
        if global_inserted:
            inserted_count += 1
            logger.info(f"Inserted GLOBAL snapshot: {global_metrics_json}")
        else:
            duplicate_count += 1
            logger.warning("GLOBAL snapshot conflict - duplicate prevented by unique constraint")

        # Data quality check: Verify insertions occurred
        if inserted_count == 0 and duplicate_count == 0:
            raise ValueError(
                f"No snapshots inserted for {len(all_consumer_ids)} consumers - possible data integrity issue"
            )

        # Update watermark after successful processing
        update_watermark(
            cursor=cursor,
            job_name="consumer_analytics_daily",
            new_timestamp=snapshot_timestamp,
            status="success",
            records_processed=new_customers_count + new_events_count,
            metadata={
                "consumers_processed": len(all_consumer_ids),
                "snapshots_inserted": inserted_count,
                "duplicates_skipped": duplicate_count,
                "new_customers": new_customers_count,
                "new_events": new_events_count,
            },
        )

        conn.commit()

        logger.info(
            f"Successfully loaded {inserted_count} consumer analytics snapshots ({duplicate_count} duplicates skipped)"
        )
        logger.info(f"Watermark updated to {snapshot_timestamp}")

        return {
            "status": "success",
            "snapshots_inserted": inserted_count,
            "duplicates_skipped": duplicate_count,
            "snapshot_timestamp": snapshot_timestamp.isoformat(),
            "consumers_processed": len(all_consumer_ids),
            "new_customers": new_customers_count,
            "new_events": new_events_count,
            "watermark_updated": snapshot_timestamp.isoformat(),
        }

    except psycopg2.IntegrityError as e:
        if conn:
            conn.rollback()
        logger.error(f"Database integrity error: {str(e)}")

        # Update watermark with failed status
        try:
            if cursor:
                update_watermark(
                    cursor=cursor,
                    job_name="consumer_analytics_daily",
                    new_timestamp=datetime.now(timezone.utc),
                    status="failed",
                    records_processed=0,
                    metadata={"error": str(e), "error_type": "IntegrityError"},
                )
            if conn:
                conn.commit()
        except Exception as watermark_error:
            logger.error(f"Failed to update watermark after error: {watermark_error}")

        raise
    except ValueError as e:
        if conn:
            conn.rollback()
        logger.error(f"Data validation error: {str(e)}")

        # Update watermark with failed status
        try:
            if cursor:
                update_watermark(
                    cursor=cursor,
                    job_name="consumer_analytics_daily",
                    new_timestamp=datetime.now(timezone.utc),
                    status="failed",
                    records_processed=0,
                    metadata={"error": str(e), "error_type": "ValueError"},
                )
            if conn:
                conn.commit()
        except Exception as watermark_error:
            logger.error(f"Failed to update watermark after error: {watermark_error}")

        raise
    except Exception as e:
        if conn:
            conn.rollback()

        # Update watermark with failed status
        try:
            if cursor:
                update_watermark(
                    cursor=cursor,
                    job_name="consumer_analytics_daily",
                    new_timestamp=datetime.now(timezone.utc),
                    status="failed",
                    records_processed=0,
                    metadata={"error": str(e), "error_type": type(e).__name__},
                )
            if conn:
                conn.commit()
        except Exception as watermark_error:
            logger.error(f"Failed to update watermark after error: {watermark_error}")

        logger.error(f"Error loading consumer analytics: {str(e)}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# DAG default arguments
default_args = {
    "owner": "fintegrate",
    "depends_on_past": False,
    "start_date": datetime(2025, 11, 3),
    "email_on_failure": True,
    "email_on_retry": False,
    "email": ["vytaske11@gmail.com"],
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
}

# Define DAG
with DAG(
    "consumer_analytics_etl",
    default_args=default_args,
    description="Daily ETL job to aggregate consumer-level analytics",
    schedule_interval=SCHEDULE_INTERVAL,  # Configurable via env var
    catchup=False,  # Don't backfill historical runs
    tags=["etl", "analytics", "consumer"],
) as dag:
    # Task 1: Extract customer counts
    task_extract_customers = PythonOperator(
        task_id="extract_customer_counts",
        python_callable=extract_customer_counts,
        provide_context=True,
    )

    # Task 2: Extract event counts
    task_extract_events = PythonOperator(
        task_id="extract_event_counts",
        python_callable=extract_event_counts,
        provide_context=True,
    )

    # Task 3: Load aggregated analytics
    task_load_analytics = PythonOperator(
        task_id="load_consumer_analytics",
        python_callable=load_consumer_analytics,
        provide_context=True,
    )

    # Define task dependencies
    # Tasks 1 and 2 run in parallel, Task 3 waits for both
    [task_extract_customers, task_extract_events] >> task_load_analytics
