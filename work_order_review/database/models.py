from sqlalchemy import Column, String, JSON, ForeignKey, Boolean, DateTime, func, Enum, Float, UniqueConstraint
from sqlalchemy.orm import relationship
from .base import Base
import enum
import uuid

class WorkOrderStatus(enum.Enum):
    UNPROCESSED = "UNPROCESSED"
    PENDING_REVIEW = "PENDING_REVIEW"
    REVIEWED = "REVIEWED"

class Tenant(Base):
    __tablename__ = 'tenants'
    __table_args__ = {'extend_existing': True}
    
    id = Column(String, primary_key=True)
    name = Column(String)
    raw_data = Column(JSON)

class Facility(Base):
    __tablename__ = 'facilities'
    __table_args__ = {'extend_existing': True}
    
    id = Column(String, primary_key=True)
    name = Column(String)
    tenant_id = Column(String, ForeignKey('tenants.id'))
    raw_data = Column(JSON)
    
    tenant = relationship("Tenant", backref="facilities")

class FacilityScenario(Base):
    __tablename__ = 'facility_scenarios'
    __table_args__ = {'extend_existing': True}
    
    id = Column(String, primary_key=True)
    name = Column(String)
    tenant_id = Column(String, ForeignKey('tenants.id'))
    facility_id = Column(String, ForeignKey('facilities.id'))
    raw_data = Column(JSON)
    
    tenant = relationship("Tenant", backref="scenarios")
    facility = relationship("Facility", backref="scenarios")

class Asset(Base):
    __tablename__ = 'assets'
    __table_args__ = {'extend_existing': True}
    
    id = Column(String, primary_key=True)
    client_id = Column(String)
    name = Column(String)
    tenant_id = Column(String)
    facility_scenario_id = Column(String)
    is_active = Column(Boolean, default=True)
    raw_data = Column(JSON)
    
    components = relationship("Component", back_populates="asset")

class Component(Base):
    __tablename__ = 'components'
    __table_args__ = {'extend_existing': True}
    
    id = Column(String, primary_key=True)
    asset_id = Column(String, ForeignKey('assets.id'))
    client_id = Column(String)
    name = Column(String)
    tenant_id = Column(String)
    facility_scenario_id = Column(String)
    is_active = Column(Boolean, default=True)
    raw_data = Column(JSON)
    
    asset = relationship("Asset", back_populates="components")
    assessments = relationship("Assessment", back_populates="component")

class Assessment(Base):
    __tablename__ = 'assessments'
    __table_args__ = {'extend_existing': True}
    
    id = Column(String, primary_key=True)
    component_id = Column(String, ForeignKey('components.id'))
    tenant_id = Column(String)
    facility_scenario_id = Column(String)
    is_active = Column(Boolean, default=True)
    raw_data = Column(JSON)
    
    component = relationship("Component", back_populates="assessments")

class WorkOrderMatch(Base):
    __tablename__ = "work_order_matches"
    __table_args__ = {'extend_existing': True}
    
    id = Column(String, primary_key=True)
    work_order_id = Column(String, ForeignKey("work_orders.id"))
    asset_client_id = Column(String, nullable=False)
    matching_confidence_score = Column(Float, nullable=False)
    matching_reasoning = Column(String, nullable=False)
    review_status = Column(String, default='PENDING')
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    
    work_order = relationship("WorkOrder", back_populates="matches")

class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        UniqueConstraint('tenant_id', 'facility_scenario_id', 'external_id', 
                        name='unique_work_order'),
        {'extend_existing': True}
    )
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    external_id = Column(String, nullable=False)
    tenant_id = Column(String, ForeignKey('tenants.id'), nullable=False)
    facility_scenario_id = Column(String, ForeignKey('facility_scenarios.id'), nullable=False)
    raw_data = Column(JSON, nullable=False)
    status = Column(String, nullable=False, default=WorkOrderStatus.UNPROCESSED.value)
    review_notes = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    tenant = relationship("Tenant", backref="work_orders")
    facility_scenario = relationship("FacilityScenario", backref="work_orders")
    matches = relationship("WorkOrderMatch", back_populates="work_order")
    processing_results = relationship("WorkOrderProcessingResult", back_populates="work_order")

class WorkOrderProcessingResult(Base):
    __tablename__ = "work_order_processing_results"
    __table_args__ = {'extend_existing': True}
    
    id = Column(String, primary_key=True)
    work_order_id = Column(String, ForeignKey("work_orders.id"))
    processed_at = Column(DateTime, server_default=func.now())
    error = Column(String, nullable=True)
    raw_response = Column(JSON, nullable=True)
    
    work_order = relationship("WorkOrder") 