"""
Consumer Analytics ETL DAG
Aggregates customer and event data into consumer-level metrics snapshots.

Schedule: Daily at midnight (configurable via SCHEDULE_INTERVAL environment variable)
Pattern: Extract → Transform → Load with incremental watermark tracking
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import psycopg2
import logging
import os

# Configure logger
logger = logging.getLogger(__name__)

# Database connection parameters
DB_CONFIG = {
    'host': 'postgres',
    'port': 5432,
    'database': 'fintegrate_db',
    'user': 'fintegrate_user',
    'password': 'fintegrate_pass'
}

# Configurable schedule (default: daily at midnight)
SCHEDULE_INTERVAL = os.getenv('ETL_SCHEDULE_INTERVAL', '@daily')


def get_db_connection():
    """Create PostgreSQL connection."""
    return psycopg2.connect(**DB_CONFIG)


def get_watermark(cursor, job_name='consumer_analytics_daily'):
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
    
    cursor.execute(query, (
        new_timestamp,
        status,
        records_processed,
        psycopg2.extras.Json(metadata or {}),
        job_name
    ))
    
    logger.info(f"Updated watermark to {new_timestamp}, status={status}, records={records_processed}")


def extract_customer_counts(**context):
    """
    Task 1: Extract customer counts per consumer (incremental based on watermark).
    
    Returns:
        dict: Customer count metrics per consumer_id
    """
    logger.info("=== Starting Task 1: Extract Customer Counts ===")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
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
        
        # Transform to dictionary keyed by consumer_id
        customer_metrics = {}
        new_customers_count = 0
        for row in results:
            consumer_id = str(row[0])
            customer_metrics[consumer_id] = {
                'total_customers': row[1],
                'active_customers': row[2],
                'inactive_customers': row[3],
                'oldest_customer_created': row[4].isoformat() if row[4] else None,
                'newest_customer_created': row[5].isoformat() if row[5] else None
            }
            new_customers_count += row[1]
        
        logger.info(f"Extracted {new_customers_count} new customers (created after {watermark}) for {len(customer_metrics)} consumers")
        for consumer_id, metrics in customer_metrics.items():
            logger.info(f"  Consumer {consumer_id}: {metrics['total_customers']} new customers ({metrics['active_customers']} active)")
        
        # Push to XCom for next task
        context['task_instance'].xcom_push(key='customer_metrics', value=customer_metrics)
        context['task_instance'].xcom_push(key='watermark', value=watermark.isoformat())
        context['task_instance'].xcom_push(key='new_customers_count', value=new_customers_count)
        
        return customer_metrics
        
    except Exception as e:
        logger.error(f"Error extracting customer counts: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()


def extract_event_counts(**context):
    """
    Task 2: Extract event counts per consumer and event type (incremental based on watermark).
    
    Returns:
        dict: Event count metrics per consumer_id
    """
    logger.info("=== Starting Task 2: Extract Event Counts ===")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
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
        
        # Transform to nested dictionary
        event_metrics = {}
        total_new_events = 0
        for row in results:
            consumer_id = str(row[0])
            event_type = row[1]
            event_count = row[2]
            total_new_events += event_count
            
            if consumer_id not in event_metrics:
                event_metrics[consumer_id] = {
                    'events_by_type': {},
                    'total_events': 0,
                    'earliest_event': row[3].isoformat() if row[3] else None,
                    'latest_event': row[4].isoformat() if row[4] else None
                }
            
            event_metrics[consumer_id]['events_by_type'][event_type] = event_count
            event_metrics[consumer_id]['total_events'] += event_count
            
            # Update earliest/latest if necessary
            if row[3] and (not event_metrics[consumer_id]['earliest_event'] or row[3].isoformat() < event_metrics[consumer_id]['earliest_event']):
                event_metrics[consumer_id]['earliest_event'] = row[3].isoformat()
            if row[4] and (not event_metrics[consumer_id]['latest_event'] or row[4].isoformat() > event_metrics[consumer_id]['latest_event']):
                event_metrics[consumer_id]['latest_event'] = row[4].isoformat()
        
        logger.info(f"Extracted {total_new_events} new events (created after {watermark}) for {len(event_metrics)} consumers")
        for consumer_id, metrics in event_metrics.items():
            logger.info(f"  Consumer {consumer_id}: {metrics['total_events']} new events")
            logger.info(f"    Event types: {metrics['events_by_type']}")
        
        # Push to XCom for next task
        context['task_instance'].xcom_push(key='event_metrics', value=event_metrics)
        context['task_instance'].xcom_push(key='new_events_count', value=total_new_events)
        
        return event_metrics
        
    except Exception as e:
        logger.error(f"Error extracting event counts: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()


def load_consumer_analytics(**context):
    """
    Task 3: Combine metrics, insert into consumer_analytics, and update watermark.
    
    Creates one snapshot per consumer with aggregated metrics.
    Updates watermark after successful processing.
    """
    logger.info("=== Starting Task 3: Load Consumer Analytics ===")
    
    # Pull metrics from XCom
    customer_metrics = context['task_instance'].xcom_pull(task_ids='extract_customer_counts', key='customer_metrics')
    event_metrics = context['task_instance'].xcom_pull(task_ids='extract_event_counts', key='event_metrics')
    watermark_str = context['task_instance'].xcom_pull(task_ids='extract_customer_counts', key='watermark')
    new_customers_count = context['task_instance'].xcom_pull(task_ids='extract_customer_counts', key='new_customers_count') or 0
    new_events_count = context['task_instance'].xcom_pull(task_ids='extract_event_counts', key='new_events_count') or 0
    
    # If no new data, skip processing but still update watermark
    if not customer_metrics and not event_metrics:
        logger.info("No new data since last watermark - skipping snapshot creation")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Update watermark with current timestamp to mark successful run
            current_timestamp = datetime.utcnow()
            update_watermark(
                cursor=cursor,
                job_name='consumer_analytics_daily',
                new_timestamp=current_timestamp,
                status='success',
                records_processed=0,
                metadata={'skip_reason': 'no_new_data', 'previous_watermark': watermark_str}
            )
            conn.commit()
            logger.info(f"Watermark updated to {current_timestamp} (no data processed)")
            
            return {
                'status': 'skipped',
                'reason': 'no_new_data',
                'watermark_updated': current_timestamp.isoformat()
            }
        finally:
            cursor.close()
            conn.close()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        snapshot_timestamp = datetime.utcnow()
        inserted_count = 0
        
        # Get all unique consumer IDs
        all_consumer_ids = set(customer_metrics.keys() if customer_metrics else []) | set(event_metrics.keys() if event_metrics else [])
        
        for consumer_id in all_consumer_ids:
            # Merge customer and event metrics
            cust_metrics = customer_metrics.get(consumer_id, {
                'total_customers': 0,
                'active_customers': 0,
                'inactive_customers': 0
            }) if customer_metrics else {
                'total_customers': 0,
                'active_customers': 0,
                'inactive_customers': 0
            }
            evt_metrics = event_metrics.get(consumer_id, {
                'events_by_type': {},
                'total_events': 0
            }) if event_metrics else {'events_by_type': {}, 'total_events': 0}
            
            # Calculate average customer lifetime (days)
            avg_lifetime_days = 0
            if cust_metrics.get('oldest_customer_created'):
                try:
                    oldest = datetime.fromisoformat(cust_metrics['oldest_customer_created'])
                    avg_lifetime_days = (snapshot_timestamp - oldest).days
                except Exception as e:
                    logger.warning(f"Error calculating lifetime for consumer {consumer_id}: {e}")
            
            # Build metrics JSON
            metrics_json = {
                'total_customers': cust_metrics.get('total_customers', 0),
                'active_customers': cust_metrics.get('active_customers', 0),
                'inactive_customers': cust_metrics.get('inactive_customers', 0),
                'total_events': evt_metrics.get('total_events', 0),
                'events_by_type': evt_metrics.get('events_by_type', {}),
                'avg_customer_lifetime_days': avg_lifetime_days,
                'snapshot_source': 'airflow_etl',
                'etl_job': 'consumer_analytics_daily',
                'incremental_stats': {
                    'new_customers_in_window': cust_metrics.get('total_customers', 0),
                    'new_events_in_window': evt_metrics.get('total_events', 0),
                    'watermark_used': watermark_str
                }
            }
            
            # Insert snapshot
            insert_query = """
                INSERT INTO consumer_analytics (analytics_id, consumer_id, snapshot_timestamp, metrics_json)
                VALUES (gen_random_uuid(), %s, %s, %s::jsonb)
                ON CONFLICT (consumer_id, snapshot_timestamp) DO NOTHING
            """
            
            cursor.execute(insert_query, (consumer_id, snapshot_timestamp, psycopg2.extras.Json(metrics_json)))
            inserted_count += cursor.rowcount
            
            logger.info(f"Inserted snapshot for consumer {consumer_id}: {metrics_json}")
        
        # Update watermark after successful processing
        update_watermark(
            cursor=cursor,
            job_name='consumer_analytics_daily',
            new_timestamp=snapshot_timestamp,
            status='success',
            records_processed=new_customers_count + new_events_count,
            metadata={
                'consumers_processed': len(all_consumer_ids),
                'snapshots_inserted': inserted_count,
                'new_customers': new_customers_count,
                'new_events': new_events_count
            }
        )
        
        conn.commit()
        
        logger.info(f"Successfully loaded {inserted_count} consumer analytics snapshots")
        logger.info(f"Watermark updated to {snapshot_timestamp}")
        
        return {
            'status': 'success',
            'snapshots_inserted': inserted_count,
            'snapshot_timestamp': snapshot_timestamp.isoformat(),
            'consumers_processed': len(all_consumer_ids),
            'new_customers': new_customers_count,
            'new_events': new_events_count,
            'watermark_updated': snapshot_timestamp.isoformat()
        }
        
    except Exception as e:
        conn.rollback()
        
        # Update watermark with failed status
        try:
            update_watermark(
                cursor=cursor,
                job_name='consumer_analytics_daily',
                new_timestamp=datetime.utcnow(),
                status='failed',
                records_processed=0,
                metadata={'error': str(e)}
            )
            conn.commit()
        except Exception as watermark_error:
            logger.error(f"Failed to update watermark after error: {watermark_error}")
        
        logger.error(f"Error loading consumer analytics: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()


# DAG default arguments
default_args = {
    'owner': 'fintegrate',
    'depends_on_past': False,
    'start_date': datetime(2025, 11, 3),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

# Define DAG
with DAG(
    'consumer_analytics_etl',
    default_args=default_args,
    description='Daily ETL job to aggregate consumer-level analytics',
    schedule_interval=SCHEDULE_INTERVAL,  # Configurable via env var
    catchup=False,  # Don't backfill historical runs
    tags=['etl', 'analytics', 'consumer'],
) as dag:
    
    # Task 1: Extract customer counts
    task_extract_customers = PythonOperator(
        task_id='extract_customer_counts',
        python_callable=extract_customer_counts,
        provide_context=True,
    )
    
    # Task 2: Extract event counts
    task_extract_events = PythonOperator(
        task_id='extract_event_counts',
        python_callable=extract_event_counts,
        provide_context=True,
    )
    
    # Task 3: Load aggregated analytics
    task_load_analytics = PythonOperator(
        task_id='load_consumer_analytics',
        python_callable=load_consumer_analytics,
        provide_context=True,
    )
    
    # Define task dependencies
    # Tasks 1 and 2 run in parallel, Task 3 waits for both
    [task_extract_customers, task_extract_events] >> task_load_analytics
