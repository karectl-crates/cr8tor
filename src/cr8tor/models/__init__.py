"""Pydantic models for all CRDs."""

# Import all models to ensure they're registered
from . import identity
from . import workspaces

__all__ = ["identity", "workspaces"]
