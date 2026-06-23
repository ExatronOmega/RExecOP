"""Domain-neutral target and profile-operation catalog projection."""

from rexecop.catalog.model import (
    ApplicabilityResult,
    CatalogBinding,
    OperationDescriptor,
    TargetDescriptor,
)
from rexecop.catalog.service import CatalogService

__all__ = [
    "ApplicabilityResult",
    "CatalogBinding",
    "CatalogService",
    "OperationDescriptor",
    "TargetDescriptor",
]
