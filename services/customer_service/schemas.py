from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import Optional, Any, Dict, List


class CustomerCreate(BaseModel):
    """Schema for POST /customer/data - Create customer"""
    name: str = Field(..., min_length=1, max_length=255, description="Customer name")


class CustomerCreateResponse(BaseModel):
    """Response schema for POST /customer/data"""
    customer_id: UUID
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class CustomerResponse(BaseModel):
    """Response schema for GET /customer/data"""
    customer_id: UUID
    name: str
    status: str
    created_at: datetime
    updated_at: datetime
    tags: Dict[str, str] = Field(default_factory=dict, description="Customer tags as key-value pairs")
    
    class Config:
        from_attributes = True


class CustomerStatusChange(BaseModel):
    """Schema for PATCH /customer/change-status"""
    customer_id: UUID
    status: str = Field(..., pattern="^(ACTIVE|INACTIVE)$", description="Customer status: ACTIVE or INACTIVE")


class CustomerTagCreate(BaseModel):
    """Schema for POST /customer/tag - Create tags"""
    customer_id: UUID
    tag_keys: List[str] = Field(..., min_length=1, description="List of tag keys")
    tag_values: List[str] = Field(..., min_length=1, description="List of tag values")


class CustomerTagGet(BaseModel):
    """Schema for GET /customer/tag-value - Get tag value"""
    customer_id: UUID
    tag_key: str


class CustomerTagGetResponse(BaseModel):
    """Response schema for GET /customer/tag-value"""
    tag_value: str


class CustomerTagDelete(BaseModel):
    """Schema for DELETE /customer/tag - Delete tag"""
    customer_id: UUID
    tag_key: str


class CustomerTagKeyUpdate(BaseModel):
    """Schema for PATCH /customer/tag-key - Update tag key"""
    customer_id: UUID
    tag_key: str
    new_tag_key: str


class CustomerTagValueUpdate(BaseModel):
    """Schema for PATCH /customer/tag-value - Update tag value"""
    customer_id: UUID
    tag_key: str
    new_tag_value: str


# Deprecated: CustomerAnalyticsCreate schema removed (endpoint deprecated)
# Analytics now handled by Airflow ETL job


class Detail(BaseModel):
    """Standard detail information for all API responses"""
    status_code: str
    status_name: str
    status_description: str


class StandardResponse(BaseModel):
    """Standard wrapper for all API responses"""
    data: Dict[str, Any]
    detail: Detail


class CustomerCreateStandardResponse(BaseModel):
    """Standard response for POST /customer/data"""
    data: CustomerCreateResponse
    detail: Detail


class CustomerGetStandardResponse(BaseModel):
    """Standard response for GET /customer/data"""
    data: CustomerResponse
    detail: Detail


class CustomerDeleteStandardResponse(BaseModel):
    """Standard response for DELETE /customer/data"""
    data: Dict[str, Any]
    detail: Detail


class CustomerStatusChangeStandardResponse(BaseModel):
    """Standard response for PATCH /customer/change-status"""
    data: Dict[str, Any]
    detail: Detail


class CustomerTagStandardResponse(BaseModel):
    """Standard response for tag operations"""
    data: Dict[str, Any]
    detail: Detail


class CustomerTagGetStandardResponse(BaseModel):
    """Standard response for GET /customer/tag-value"""
    data: CustomerTagGetResponse
    detail: Detail


class EventResendRequest(BaseModel):
    """Schema for POST /events/resend - Resend pending events"""
    period_in_days: int = Field(..., ge=1, le=365, description="How many days back to search for pending events")
    max_try_count: Optional[int] = Field(None, ge=1, le=10, description="Skip events that exceeded this retry count")
    event_types: Optional[List[str]] = Field(None, description="Filter by specific event types (e.g., ['customer_creation'])")


class EventResendFailedEvent(BaseModel):
    """Schema for failed event details in resend response"""
    event_id: UUID
    event_type: str
    try_count: int
    failure_reason: Optional[str]


class EventResendSummary(BaseModel):
    """Summary statistics for event resend operation"""
    total_pending: int = Field(..., description="Total pending events found in database")
    attempted: int = Field(..., description="Number of events attempted to republish")
    succeeded: int = Field(..., description="Number of successfully published events")
    failed: int = Field(..., description="Number of events that failed to publish")
    skipped: int = Field(..., description="Number of events skipped (exceeded max_try_count)")


class EventResendResponseData(BaseModel):
    """Data section for event resend response"""
    summary: EventResendSummary
    failed_events: List[EventResendFailedEvent]


class EventResendStandardResponse(BaseModel):
    """Standard response for POST /events/resend"""
    data: EventResendResponseData
    detail: Detail


class EventHealthResponseData(BaseModel):
    """Data section for event health response"""
    pending_count: int = Field(..., description="Number of events with publish_status='pending'")
    oldest_pending_age_seconds: Optional[float] = Field(None, description="Age in seconds of oldest pending event")
    failed_count: int = Field(..., description="Number of events with publish_status='failed'")


class EventHealthStandardResponse(BaseModel):
    """Standard response for GET /events/health"""
    data: EventHealthResponseData
    detail: Detail


class EventConfirmDeliveryRequest(BaseModel):
    """Schema for POST /events/confirm-delivery - Consumer confirms receipt"""
    event_id: UUID = Field(..., description="Event ID from the message")
    status: str = Field(..., pattern="^(received|processed|failed)$", description="Processing status: received, processed, or failed")
    received_at: datetime = Field(..., description="Timestamp when consumer received the message")
    failure_reason: Optional[str] = Field(None, description="Reason for failure if status='failed'")
    consumer_name: str = Field(..., description="Name of the consumer processing this event")


class EventConfirmDeliveryStandardResponse(BaseModel):
    """Standard response for POST /events/confirm-delivery"""
    data: Dict[str, Any]
    detail: Detail


class EventRedeliverRequest(BaseModel):
    """Schema for POST /events/redeliver - Redeliver pending deliveries"""
    period_in_days: int = Field(..., ge=1, le=365, description="How many days back to search for undelivered events")
    max_try_count: Optional[int] = Field(None, ge=1, le=10, description="Skip events that exceeded this delivery retry count")
    event_types: Optional[List[str]] = Field(None, description="Filter by specific event types")


class EventRedeliverFailedEvent(BaseModel):
    """Schema for failed event details in redeliver response"""
    event_id: UUID
    event_type: str
    deliver_try_count: int
    deliver_failure_reason: Optional[str]


class EventRedeliverSummary(BaseModel):
    """Summary statistics for event redelivery operation"""
    total_pending: int = Field(..., description="Total undelivered events found")
    attempted: int = Field(..., description="Number of events attempted to republish")
    succeeded: int = Field(..., description="Number of successfully republished events")
    failed: int = Field(..., description="Number of events that failed to republish")
    skipped: int = Field(..., description="Number of events skipped (exceeded max_try_count)")


class EventRedeliverResponseData(BaseModel):
    """Data section for event redeliver response"""
    summary: EventRedeliverSummary
    failed_events: List[EventRedeliverFailedEvent]


class EventRedeliverStandardResponse(BaseModel):
    """Standard response for POST /events/redeliver"""
    data: EventRedeliverResponseData
    detail: Detail


# Consumer Management Schemas

class ConsumerCreate(BaseModel):
    """Schema for POST /consumer/data - Create consumer"""
    name: str = Field(..., min_length=1, max_length=230, pattern="^[a-z0-9_]+$", description="Consumer name (alphanumeric + underscore)")
    description: Optional[str] = Field(None, description="Consumer description")


class ConsumerCreateResponseData(BaseModel):
    """Response data for POST /consumer/data"""
    consumer_id: UUID
    api_key: str = Field(..., description="API key in plaintext (only shown once)")


class ConsumerCreateStandardResponse(BaseModel):
    """Standard response for POST /consumer/data"""
    data: ConsumerCreateResponseData
    detail: Detail


class ConsumerRotateKeyResponseData(BaseModel):
    """Response data for POST /consumer/me/api-key/rotate"""
    api_key: str = Field(..., description="New API key in plaintext (only shown once)")


class ConsumerRotateKeyStandardResponse(BaseModel):
    """Standard response for POST /consumer/me/api-key/rotate"""
    data: ConsumerRotateKeyResponseData
    detail: Detail


class ConsumerGetResponseData(BaseModel):
    """Response data for GET /consumer/me"""
    consumer_id: UUID
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


class ConsumerGetStandardResponse(BaseModel):
    """Standard response for GET /consumer/me"""
    data: ConsumerGetResponseData
    detail: Detail


class ConsumerKeyStatusResponseData(BaseModel):
    """Response data for GET /consumer/me/api-key"""
    status: str
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    updated_at: datetime


class ConsumerKeyStatusStandardResponse(BaseModel):
    """Standard response for GET /consumer/me/api-key"""
    data: ConsumerKeyStatusResponseData
    detail: Detail


class ConsumerChangeStatusRequest(BaseModel):
    """Schema for POST /admin/consumer/{consumer_id}/change-status"""
    status: str = Field(..., pattern="^(active|deactivated|suspended)$", description="Consumer status")


class ConsumerChangeStatusStandardResponse(BaseModel):
    """Standard response for POST /admin/consumer/{consumer_id}/change-status"""
    data: Dict[str, Any]
    detail: Detail


# Analytics API Schemas (Power BI Integration - Task 1)

class AnalyticsSnapshot(BaseModel):
    """Schema for individual analytics snapshot"""
    analytics_id: UUID
    consumer_id: Optional[UUID] = Field(None, description="Consumer UUID for per-consumer snapshots, null for global snapshots")
    consumer_name: Optional[str] = Field(None, description="Consumer name, null for global snapshots")
    snapshot_timestamp: datetime
    snapshot_type: str = Field(..., description="CONSUMER or GLOBAL")
    metrics: Dict[str, Any] = Field(..., description="Metrics JSON (structure varies by snapshot_type)")
    
    class Config:
        from_attributes = True


class PaginationMetadata(BaseModel):
    """Pagination metadata for analytics responses"""
    page: int = Field(..., ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(..., ge=1, le=1000, description="Number of records per page")
    total_records: int = Field(..., ge=0, description="Total number of records matching filter")
    total_pages: int = Field(..., ge=0, description="Total number of pages")


class AnalyticsSnapshotsResponseData(BaseModel):
    """Data section for GET /analytics/snapshots"""
    snapshots: List[AnalyticsSnapshot]
    pagination: PaginationMetadata


class AnalyticsSnapshotsStandardResponse(BaseModel):
    """Standard response for GET /analytics/snapshots"""
    data: AnalyticsSnapshotsResponseData
    detail: Detail
