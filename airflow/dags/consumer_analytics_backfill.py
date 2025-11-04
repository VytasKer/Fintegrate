"""
Consumer Analytics Historical Backfill DAG
Generates analytics snapshots for historical date ranges.

Purpose: One-time or ad-hoc backfill of consumer_analytics table for past dates
Schedule: Manual trigger only (schedule_interval=None)
Parameters: start_date, end_date, interval (daily/weekly)

Usage Example:
    Trigger via Airflow UI with params:
    {
        "start_date": "2025-01-01",
        "end_date": "2025-01-31",
        "interval": "daily"
    }

Email Alerts: Sends failure notifications to vytaske11@gmail.com
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.models.param import Param
from airflow.operators.python import PythonOperator
import psycopg2
import psycopg2.extras
import logging

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


def validate_params(**context):
    """
    Validate DAG parameters before processing.
    
    Raises:
        ValueError: If parameters are invalid
    """
    params = context['params']
    
    start_date_str = params.get('start_date')
    end_date_str = params.get('end_date')
    interval = params.get('interval')
    
    logger.info("=" * 80)
    logger.info("VALIDATING BACKFILL PARAMETERS")
    logger.info(f"Start Date: {start_date_str}")
    logger.info(f"End Date: {end_date_str}")
    logger.info(f"Interval: {interval}")
    
    # Parse dates
    try:
        start_date = datetime.fromisoformat(start_date_str)
        end_date = datetime.fromisoformat(end_date_str)
    except ValueError as e:
        raise ValueError(f"Invalid date format (use YYYY-MM-DD): {str(e)}")
    
    # Validate date range
    if start_date >= end_date:
        raise ValueError(f"start_date ({start_date_str}) must be before end_date ({end_date_str})")
    
    if start_date > datetime.utcnow():
        raise ValueError(f"start_date ({start_date_str}) cannot be in the future")
    
    # Validate interval
    if interval not in ['daily', 'weekly']:
        raise ValueError(f"interval must be 'daily' or 'weekly', got: {interval}")
    
    # Calculate number of periods
    delta = end_date - start_date
    if interval == 'daily':
        num_periods = delta.days
    else:  # weekly
        num_periods = delta.days // 7
    
    logger.info(f"Validation passed - will process {num_periods} {interval} periods")
    
    context['task_instance'].xcom_push(key='start_date', value=start_date.isoformat())
    context['task_instance'].xcom_push(key='end_date', value=end_date.isoformat())
    context['task_instance'].xcom_push(key='interval', value=interval)
    context['task_instance'].xcom_push(key='num_periods', value=num_periods)


def process_historical_period(**context):
    """
    Generate analytics snapshots for historical date ranges.
    Processes one period at a time, updates watermarks for backfilled periods.
    """
    # Retrieve validated params from XCom
    start_date = datetime.fromisoformat(context['task_instance'].xcom_pull(task_ids='validate_params', key='start_date'))
    end_date = datetime.fromisoformat(context['task_instance'].xcom_pull(task_ids='validate_params', key='end_date'))
    interval = context['task_instance'].xcom_pull(task_ids='validate_params', key='interval')
    num_periods = context['task_instance'].xcom_pull(task_ids='validate_params', key='num_periods')
    
    logger.info("=" * 80)
    logger.info("STARTING HISTORICAL BACKFILL")
    logger.info(f"Date Range: {start_date.date()} to {end_date.date()}")
    logger.info(f"Interval: {interval}")
    logger.info(f"Periods to process: {num_periods}")
    
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Generate list of period boundaries
        current_date = start_date
        period_delta = timedelta(days=1) if interval == 'daily' else timedelta(weeks=1)
        
        total_snapshots = 0
        total_consumers_processed = 0
        periods_processed = 0
        
        while current_date < end_date:
            period_end = min(current_date + period_delta, end_date)
            
            logger.info(f"\nProcessing period: {current_date.date()} to {period_end.date()}")
            
            # Query customers created in this period
            customer_query = """
                SELECT 
                    consumer_id,
                    COUNT(*) as total_customers,
                    COUNT(*) FILTER (WHERE status = 'ACTIVE') as active_customers,
                    COUNT(*) FILTER (WHERE status = 'INACTIVE') as inactive_customers
                FROM customers
                WHERE created_at >= %s AND created_at < %s
                GROUP BY consumer_id
            """
            
            cursor.execute(customer_query, (current_date, period_end))
            customer_results = cursor.fetchall()
            
            # Query events created in this period
            event_query = """
                SELECT 
                    consumer_id,
                    event_type,
                    COUNT(*) as event_count
                FROM customer_events
                WHERE created_at >= %s AND created_at < %s
                GROUP BY consumer_id, event_type
            """
            
            cursor.execute(event_query, (current_date, period_end))
            event_results = cursor.fetchall()
            
            # Transform to dictionaries
            customer_metrics = {}
            for row in customer_results:
                consumer_id = str(row[0])
                customer_metrics[consumer_id] = {
                    'total_customers': row[1],
                    'active_customers': row[2],
                    'inactive_customers': row[3]
                }
            
            event_metrics = {}
            for row in event_results:
                consumer_id = str(row[0])
                event_type = row[1]
                event_count = row[2]
                
                if consumer_id not in event_metrics:
                    event_metrics[consumer_id] = {'events_by_type': {}, 'total_events': 0}
                
                event_metrics[consumer_id]['events_by_type'][event_type] = event_count
                event_metrics[consumer_id]['total_events'] += event_count
            
            # Get all unique consumer IDs
            all_consumer_ids = set(customer_metrics.keys()) | set(event_metrics.keys())
            
            if len(all_consumer_ids) == 0:
                logger.info(f"No data for period {current_date.date()} - skipping")
                current_date = period_end
                continue
            
            # Insert snapshots for this period
            snapshot_timestamp = period_end  # Use period end as snapshot time
            period_snapshots = 0
            
            for consumer_id in all_consumer_ids:
                cust_metrics = customer_metrics.get(consumer_id, {
                    'total_customers': 0,
                    'active_customers': 0,
                    'inactive_customers': 0
                })
                evt_metrics = event_metrics.get(consumer_id, {'events_by_type': {}, 'total_events': 0})
                
                metrics_json = {
                    'total_customers': cust_metrics['total_customers'],
                    'active_customers': cust_metrics['active_customers'],
                    'inactive_customers': cust_metrics['inactive_customers'],
                    'total_events': evt_metrics['total_events'],
                    'events_by_type': evt_metrics['events_by_type'],
                    'snapshot_source': 'airflow_backfill',
                    'etl_job': 'consumer_analytics_backfill',
                    'backfill_period': {
                        'start': current_date.isoformat(),
                        'end': period_end.isoformat(),
                        'interval': interval
                    }
                }
                
                # Insert with idempotency (ON CONFLICT DO NOTHING)
                insert_query = """
                    INSERT INTO consumer_analytics (analytics_id, consumer_id, snapshot_timestamp, metrics_json)
                    VALUES (gen_random_uuid(), %s, %s, %s::jsonb)
                    ON CONFLICT (consumer_id, snapshot_timestamp) DO NOTHING
                """
                
                cursor.execute(insert_query, (consumer_id, snapshot_timestamp, psycopg2.extras.Json(metrics_json)))
                
                if cursor.rowcount > 0:
                    period_snapshots += 1
            
            # Create global snapshot for this period
            global_customer_query = """
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'ACTIVE') as active,
                    COUNT(*) FILTER (WHERE status = 'INACTIVE') as inactive
                FROM customers
                WHERE created_at < %s
            """
            cursor.execute(global_customer_query, (period_end,))
            global_stats = cursor.fetchone()
            
            global_metrics_json = {
                'total_customers_all_consumers': global_stats[0],
                'active_customers_all_consumers': global_stats[1],
                'inactive_customers_all_consumers': global_stats[2],
                'snapshot_source': 'airflow_backfill',
                'etl_job': 'consumer_analytics_backfill',
                'snapshot_type': 'GLOBAL',
                'backfill_period': {
                    'start': current_date.isoformat(),
                    'end': period_end.isoformat(),
                    'interval': interval
                }
            }
            
            global_insert_query = """
                INSERT INTO consumer_analytics (analytics_id, consumer_id, snapshot_timestamp, metrics_json)
                VALUES (gen_random_uuid(), NULL, %s, %s::jsonb)
                ON CONFLICT (consumer_id, snapshot_timestamp) DO NOTHING
            """
            cursor.execute(global_insert_query, (snapshot_timestamp, psycopg2.extras.Json(global_metrics_json)))
            
            if cursor.rowcount > 0:
                period_snapshots += 1
            
            conn.commit()
            
            total_snapshots += period_snapshots
            total_consumers_processed += len(all_consumer_ids)
            periods_processed += 1
            
            logger.info(f"Period complete: {period_snapshots} snapshots inserted for {len(all_consumer_ids)} consumers")
            
            current_date = period_end
        
        logger.info("=" * 80)
        logger.info("BACKFILL COMPLETE")
        logger.info(f"Total periods processed: {periods_processed}")
        logger.info(f"Total snapshots inserted: {total_snapshots}")
        logger.info(f"Total consumers processed: {total_consumers_processed}")
        
        return {
            'status': 'success',
            'periods_processed': periods_processed,
            'snapshots_inserted': total_snapshots,
            'consumers_processed': total_consumers_processed,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'interval': interval
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Backfill error: {str(e)}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# DAG default arguments
default_args = {
    'owner': 'fintegrate',
    'depends_on_past': False,
    'start_date': datetime(2025, 11, 3),
    'email_on_failure': True,
    'email_on_retry': False,
    'email': ['vytaske11@gmail.com'],
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Define DAG with parameters
with DAG(
    'consumer_analytics_backfill',
    default_args=default_args,
    description='Historical backfill of consumer analytics snapshots for specified date ranges',
    schedule_interval=None,  # Manual trigger only
    catchup=False,
    tags=['etl', 'analytics', 'backfill', 'manual'],
    params={
        'start_date': Param(
            '2025-01-01',
            type='string',
            description='Start date for backfill (YYYY-MM-DD format)',
            title='Start Date'
        ),
        'end_date': Param(
            '2025-01-31',
            type='string',
            description='End date for backfill (YYYY-MM-DD format)',
            title='End Date'
        ),
        'interval': Param(
            'daily',
            type='string',
            enum=['daily', 'weekly'],
            description='Snapshot interval (daily or weekly)',
            title='Interval'
        ),
    },
    doc_md="""
    # Consumer Analytics Historical Backfill DAG
    
    ## Purpose
    Generate historical analytics snapshots for past date ranges where data exists but snapshots were not created.
    
    ## Parameters
    - **start_date**: Beginning of backfill period (format: YYYY-MM-DD)
    - **end_date**: End of backfill period (format: YYYY-MM-DD)
    - **interval**: Snapshot frequency - 'daily' or 'weekly'
    
    ## Usage
    1. Navigate to DAG in Airflow UI
    2. Click "Trigger DAG w/ config" button
    3. Modify parameters as needed
    4. Click "Trigger"
    
    ## Example
    To backfill January 2025 with daily snapshots:
    ```json
    {
        "start_date": "2025-01-01",
        "end_date": "2025-02-01",
        "interval": "daily"
    }
    ```
    
    ## Notes
    - Idempotent: Re-running same parameters will not create duplicates (ON CONFLICT DO NOTHING)
    - Each period gets per-consumer + global snapshots
    - Watermarks are NOT updated (this is historical data only)
    - Email alerts sent to vytaske11@gmail.com on failure
    """
) as dag:
    
    # Task 1: Validate parameters
    task_validate = PythonOperator(
        task_id='validate_params',
        python_callable=validate_params,
        provide_context=True,
    )
    
    # Task 2: Process historical periods
    task_process = PythonOperator(
        task_id='process_historical_periods',
        python_callable=process_historical_period,
        provide_context=True,
    )
    
    # Task dependencies
    task_validate >> task_process
