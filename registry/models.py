from pydantic import BaseModel
from typing import Optional


class PartAttributes(BaseModel):
    part_number: str
    make: str
    model: str
    category: str
    compatibility: str


class PartValidation(BaseModel):
    part_number: str
    valid: bool


class PartInfo(BaseModel):
    """Combined result: validity + full attributes in one call."""
    part_number: str
    valid: bool
    make: Optional[str] = None
    model: Optional[str] = None
    category: Optional[str] = None
    compatibility: Optional[str] = None


class RegistryError(BaseModel):
    error: str
