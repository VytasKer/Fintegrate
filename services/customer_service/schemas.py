from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import Optional, Any, Dict


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
    
    class Config:
        from_attributes = True


class CustomerStatusChange(BaseModel):
    """Schema for PATCH /customer/change-status"""
    customer_id: UUID
    status: str = Field(..., pattern="^(ACTIVE|INACTIVE)$", description="Customer status: ACTIVE or INACTIVE")


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
