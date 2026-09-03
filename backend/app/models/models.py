from datetime import date, datetime
from typing import Literal, Optional, List

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HumanName(BaseModel):
    family: str = Field(min_length=1, max_length=100)
    given: Optional[List[str]] = Field(default=None, min_length=1, max_length=10)


class PatientCreate(BaseModel):
    """Eingabemodell zum Anlegen eines Patienten."""

    name: List[HumanName] = Field(min_length=1, max_length=20)
    gender: Optional[Literal["male", "female", "other", "unknown"]] = None
    birthDate: Optional[date] = None


class Coding(BaseModel):
    system: str = Field(min_length=1, max_length=500)
    code: str = Field(min_length=1, max_length=100)
    display: Optional[str] = Field(default=None, max_length=500)


class CodeableConcept(BaseModel):
    coding: List[Coding] = Field(min_length=1, max_length=20)


class Quantity(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    value: float
    unit: str = Field(min_length=1, max_length=100)
    system: str = "http://unitsofmeasure.org"
    code: str = Field(min_length=1, max_length=100)


class PatientReference(BaseModel):
    reference: str = Field(pattern=r"^Patient/[A-Za-z0-9.-]{1,64}$")


class ObservationComponent(BaseModel):
    code: CodeableConcept
    valueQuantity: Quantity


class ObservationCreate(BaseModel):
    """Eingabemodell zum Anlegen einer Observation."""

    status: Literal[
        "registered",
        "preliminary",
        "final",
        "amended",
        "corrected",
        "cancelled",
        "entered-in-error",
        "unknown",
    ] = "final"
    code: CodeableConcept
    subject: PatientReference
    effectiveDateTime: Optional[datetime] = None
    valueQuantity: Optional[Quantity] = None
    component: Optional[List[ObservationComponent]] = Field(
        default=None, min_length=1, max_length=100
    )

    @model_validator(mode="after")
    def require_value(self) -> "ObservationCreate":
        if self.valueQuantity is None and not self.component:
            raise ValueError("Observation benötigt valueQuantity oder component")
        return self


class ClinicalRecordCreate(BaseModel):
    """Validierte Eingabe für pflegerelevante FHIR-Ressourcen."""

    display: str = Field(min_length=1, max_length=500)
    code: Optional[str] = Field(default=None, max_length=100)
    system: str = Field(default="http://snomed.info/sct", min_length=1, max_length=500)
    status: str = Field(default="active", min_length=1, max_length=100)
    details: Optional[str] = Field(default=None, max_length=4000)


ClinicalRecordType = Literal[
    "Condition",
    "MedicationStatement",
    "AllergyIntolerance",
    "ClinicalImpression",
    "CarePlan",
]


class RiskReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str = Field(pattern=r"^Patient/[A-Za-z0-9.-]{1,64}$")


class RiskCoding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system: str
    code: str
    display: Optional[str] = None


class RiskCodeableConcept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coding: List[RiskCoding] = Field(min_length=1)
    text: Optional[str] = None


class RiskExtension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    valueCode: Optional[str] = None
    valueString: Optional[str] = None

    @model_validator(mode="after")
    def exactly_one_value(self) -> "RiskExtension":
        values = (self.valueCode is not None, self.valueString is not None)
        if sum(values) != 1:
            raise ValueError("Extension benötigt genau einen Wert")
        return self


class RiskPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: RiskCodeableConcept
    probabilityDecimal: Optional[float] = Field(default=None, ge=0, le=1)
    qualitativeRisk: Optional[RiskCodeableConcept] = None
    extension: List[RiskExtension] = Field(default_factory=list)


class RiskMethod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coding: List[RiskCoding] = Field(min_length=1)
    text: str


class RiskNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class RiskAssessmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resourceType: Literal["RiskAssessment"]
    status: Literal["final"]
    subject: RiskReference
    occurrenceDateTime: datetime
    method: RiskMethod
    prediction: List[RiskPrediction]
    note: List[RiskNote]
