"""Base classes for CRD specifications."""

from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from datetime import datetime


class CRDMetadata(BaseModel):
    """Standard Kubernetes metadata for CRDs."""

    name: str
    namespace: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)


class CRDCondition(BaseModel):
    """Custom Kubernetes condition."""

    type: str
    status: str  # True, False, Unknown
    reason: str
    message: str
    lastTransitionTime: Optional[datetime] = None


class CRDStatus(BaseModel):
    """Base class for all CRD status objects."""

    phase: Optional[str] = None
    conditions: List[CRDCondition] = Field(default_factory=list)
    observedGeneration: Optional[int] = None

    class Config:
        extra = "allow"


class CRDSpec(BaseModel):
    """Base class for all CRD spec objects."""

    class Config:
        extra = "forbid"
        validate_assignment = True
