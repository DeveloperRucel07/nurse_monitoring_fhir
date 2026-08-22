from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class HumanName(BaseModel):
    family: str
    given: Optional[List[str]] = None

class PatientCreate(BaseModel):
    """Eingabemodell zum Anlegen eines Patienten."""
    name: List[HumanName]
    gender: Optional[str] = None
    birthDate: Optional[str] = None


class Coding(BaseModel):
    system: str
    code: str
    display: Optional[str] = None

class CodeableConcept(BaseModel):
    coding: List[Coding]

class Quantity(BaseModel):
    value: float
    unit: str
    system: str = "http://unitsofmeasure.org"
    code: str

class ObservationComponent(BaseModel):
    code: CodeableConcept
    valueQuantity: Quantity

class ObservationCreate(BaseModel):
    """Eingabemodell zum Anlegen einer Observation."""
    status: str = "final"
    code: CodeableConcept
    subject: Dict[str, str] 
    effectiveDateTime: Optional[str] = None
    valueQuantity: Optional[Quantity] = None
    component: Optional[List[ObservationComponent]] = None

