from typing import Optional, List
from pydantic import BaseModel


class HumanName(BaseModel):
    family: str
    given: Optional[List[str]] = None

class PatientCreate(BaseModel):
    """Eingabemodell zum Anlegen eines Patienten."""
    name: List[HumanName]
    gender: Optional[str] = None
    birthDate: Optional[str] = None