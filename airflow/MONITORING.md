# Consumer Analytics ETL - Monitoring & Usage Guide

## Task 8: Airflow Monitoring & Logging

### Email Alerts Configuration

**Status**: ✅ ACTIVE

**SMTP Server**: smtp.gmail.com:587 (Gmail with TLS)  
**From**: certalertnotifications@gmail.com  
**To**: vytaske11@gmail.com  

**Trigger Conditions**:
- `email_on_failure=True`: Sends email when any task fails after all retries exhausted
- `email_on_retry=False`: No emails during retry attempts (reduces noise)

**Email Content**: Airflow includes task name, execution date, error message, and link to logs.

---

## Viewing Analytics Data

### Per-Consumer Snapshots

```sql
-- Latest snapshot for each consumer
SELECT 
    consumer_id,
    snapshot_timestamp,
    metrics_json->>'total_customers' AS total_customers,
    metrics_json->>'active_customers' AS active_customers,
    metrics_json->>'total_events' AS total_events,
    metrics_json->'events_by_type' AS events_by_type
FROM consumer_analytics
WHERE consumer_id IS NOT NULL
ORDER BY snapshot_timestamp DESC, consumer_id
LIMIT 10;
```

### Global System-Wide Snapshots

```sql
-- Global snapshots (consumer_id=NULL)
SELECT 
    snapshot_timestamp,
    metrics_json->>'total_customers_all_consumers' AS total_customers,
    metrics_json->>'active_customers_all_consumers' AS active_customers,
    metrics_json->>'system_wide_active_ratio' AS active_ratio,
    metrics_json->>'consumers_in_system' AS num_consumers,
    metrics_json->'events_by_type_all_consumers' AS events_by_type
FROM consumer_analytics
WHERE consumer_id IS NULL
ORDER BY snapshot_timestamp DESC
LIMIT 10;
```

### Time-Series Trend Analysis

```sql
-- Customer growth over time (per consumer)
SELECT 
    consumer_id,
    snapshot_timestamp::date AS date,
    (metrics_json->>'total_customers')::int AS customers,
    (metrics_json->>'active_customers')::int AS active_customers,
    (metrics_json->>'total_events')::int AS total_events
FROM consumer_analytics
WHERE consumer_id IS NOT NULL
ORDER BY consumer_id, snapshot_timestamp;
```

### System-Wide Growth Metrics

```sql
-- Global system growth (7-day window)
SELECT 
    snapshot_timestamp::date AS date,
    (metrics_json->>'total_customers_all_consumers')::int AS total_customers,
    (metrics_json->>'system_wide_active_ratio')::numeric AS active_ratio,
    (metrics_json->'events_by_type_all_consumers'->>'customer_creation')::int AS creations,
    (metrics_json->'events_by_type_all_consumers'->>'customer_deletion')::int AS deletions
FROM consumer_analytics
WHERE consumer_id IS NULL
    AND snapshot_timestamp >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY snapshot_timestamp;
```

---

## ETL Job Watermarks

### Check Watermark Status

```sql
-- View current watermark state
SELECT 
    job_name,
    last_processed_timestamp,
    last_run_at,
    last_run_status,
    records_processed,
    metadata_json
FROM etl_job_watermarks
WHERE job_name = 'consumer_analytics_daily';
```

### Manually Reset Watermark (Troubleshooting)

```sql
-- DANGER: Resets watermark to reprocess all data
UPDATE etl_job_watermarks
SET last_processed_timestamp = '1970-01-01 00:00:00',
    last_run_status = 'pending',
    metadata_json = jsonb_build_object('reset_reason', 'manual_reset', 'reset_at', NOW())
WHERE job_name = 'consumer_analytics_daily';
```

### Set Watermark to Specific Date

```sql
-- Resume processing from specific timestamp
UPDATE etl_job_watermarks
SET last_processed_timestamp = '2025-11-03 00:00:00',
    last_run_status = 'pending',
    metadata_json = jsonb_build_object('manual_override', true, 'override_at', NOW())
WHERE job_name = 'consumer_analytics_daily';
```

---

## DAG Execution Logs

### View Task Execution Times (Airflow UI)

1. Navigate to http://localhost:8081
2. Click on DAG: `consumer_analytics_etl`
3. Select DAG run
4. View task durations in Gantt chart

### Query Airflow Metadata (Advanced)

```sql
-- Connect to Airflow metadata DB
-- (Same PostgreSQL instance, different schema)

-- Recent DAG runs with duration
SELECT 
    dag_id,
    run_id,
    state,
    start_date,
    end_date,
    EXTRACT(EPOCH FROM (end_date - start_date)) AS duration_seconds
FROM dag_run
WHERE dag_id = 'consumer_analytics_etl'
ORDER BY start_date DESC
LIMIT 10;
```

---

## Performance Metrics

### Expected Execution Times (Baseline)

- **Extract Customer Counts**: ~0.15-0.20 seconds
- **Extract Event Counts**: ~0.15-0.20 seconds  
- **Load Consumer Analytics**: ~0.18-0.30 seconds
- **Total DAG Runtime**: ~2.0-2.5 seconds (with 2-3 consumers)

**Scaling Assumptions**: Add ~0.05s per additional consumer, ~0.10s per 1000 events.

### Monitoring Thresholds

| Metric | Normal | Warning | Critical |
|--------|---------|---------|----------|
| DAG Runtime | < 5s | 5-15s | > 15s |
| Failed Runs | 0 | 1/day | 2+/day |
| Watermark Lag | < 1 hour | 1-6 hours | > 6 hours |
| Pending Events | 0 | < 100 | > 100 |

---

## Troubleshooting Runbook

### Issue: DAG Not Running on Schedule

**Symptoms**: No new snapshots created, scheduler logs silent  
**Diagnosis**:
```bash
docker exec fintegrate-airflow-scheduler airflow dags list | findstr consumer_analytics_etl
docker exec fintegrate-airflow-scheduler airflow dags state consumer_analytics_etl
```

**Solutions**:
1. Check DAG paused: Unpause in UI
2. Check scheduler running: `docker ps | findstr airflow-scheduler`
3. Check logs: `docker logs fintegrate-airflow-scheduler --tail 50`

### Issue: Email Alerts Not Sending

**Symptoms**: Task fails but no email received  
**Diagnosis**:
```bash
# Check SMTP config
docker exec fintegrate-airflow-scheduler env | findstr SMTP

# Test connection
docker exec -it fintegrate-airflow-scheduler python -c "
import smtplib
import os
server = smtplib.SMTP('smtp.gmail.com', 587)
server.starttls()
server.login('certalertnotifications@gmail.com', os.getenv('AIRFLOW__SMTP__SMTP_PASSWORD'))
print('SMTP OK')
server.quit()
"
```

**Solutions**:
1. Verify Gmail app password valid
2. Check spam folder
3. Restart Airflow: `docker-compose restart airflow-scheduler`

### Issue: Duplicate Snapshots

**Symptoms**: Multiple rows for same consumer + timestamp  
**Diagnosis**:
```sql
SELECT consumer_id, snapshot_timestamp, COUNT(*)
FROM consumer_analytics
GROUP BY consumer_id, snapshot_timestamp
HAVING COUNT(*) > 1;
```

**Solution**: Unique constraint should prevent this. If occurs:
```sql
-- Remove duplicates, keep earliest by analytics_id
DELETE FROM consumer_analytics a
USING consumer_analytics b
WHERE a.analytics_id > b.analytics_id
    AND a.consumer_id = b.consumer_id
    AND a.snapshot_timestamp = b.snapshot_timestamp;
```

### Issue: Watermark Not Advancing

**Symptoms**: ETL runs successfully but processes zero records  
**Diagnosis**:
```sql
-- Check if new data exists after watermark
SELECT last_processed_timestamp FROM etl_job_watermarks WHERE job_name = 'consumer_analytics_daily';

-- Check for newer customers
SELECT COUNT(*) FROM customers WHERE created_at > (SELECT last_processed_timestamp FROM etl_job_watermarks WHERE job_name = 'consumer_analytics_daily');
```

**Solution**: If data exists but not processed, manually reset watermark (see above).

---

## Historical Backfill Usage

### Trigger via Airflow UI

1. Navigate to http://localhost:8081
2. Find DAG: `consumer_analytics_backfill`
3. Click "Trigger DAG w/ config"
4. Enter parameters:
   ```json
   {
       "start_date": "2025-10-01",
       "end_date": "2025-11-01",
       "interval": "daily"
   }
   ```
5. Click "Trigger"

### Trigger via CLI

```bash
# Backfill October 2025 with daily snapshots
docker exec fintegrate-airflow-scheduler airflow dags trigger consumer_analytics_backfill \
    --conf '{"start_date": "2025-10-01", "end_date": "2025-11-01", "interval": "daily"}'

# Backfill Q1 2025 with weekly snapshots
docker exec fintegrate-airflow-scheduler airflow dags trigger consumer_analytics_backfill \
    --conf '{"start_date": "2025-01-01", "end_date": "2025-04-01", "interval": "weekly"}'
```

### Verify Backfill Results

```sql
-- Count snapshots by source
SELECT 
    metrics_json->>'snapshot_source' AS source,
    COUNT(*) AS snapshot_count,
    MIN(snapshot_timestamp) AS earliest,
    MAX(snapshot_timestamp) AS latest
FROM consumer_analytics
GROUP BY metrics_json->>'snapshot_source';
```

---

## SLA Monitoring (Future Enhancement)

### Define SLAs in DAG

```python
# Add to default_args in consumer_analytics_etl.py
'sla': timedelta(minutes=10),  # Alert if task runs longer than 10 minutes
```

### Query SLA Misses

```sql
-- Airflow tracks SLA violations in sla_miss table
SELECT 
    task_id,
    dag_id,
    execution_date,
    timestamp AS sla_miss_time
FROM sla_miss
WHERE dag_id = 'consumer_analytics_etl'
ORDER BY timestamp DESC;
```

---

## Log Retention

**Current**: Logs stored in `airflow_logs` Docker volume  
**Retention**: Indefinite (manual cleanup required)

**Cleanup Command**:
```bash
# Remove logs older than 30 days
docker exec fintegrate-airflow-scheduler find /opt/airflow/logs -type f -mtime +30 -delete
```

**Recommended**: Implement log rotation in production (logrotate or Airflow log cleanup DAG).

---

## Contact

**Alerts Email**: vytaske11@gmail.com  
**System Admin**: Fintegrate Team  
**Escalation**: Check scheduler logs, database connection, watermark state
