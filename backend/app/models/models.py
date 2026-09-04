from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HumanName(BaseModel):
    family: str = Field(min_length=1, max_length=100)
    given: Optional[List[str]] = Field(default=None, min_length=1, max_length=10)

    @field_validator("family")
    @classmethod
    def family_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Nachname darf nicht leer sein")
        return value

    @field_validator("given")
    @classmethod
    def given_names_must_not_be_blank(
        cls, value: Optional[List[str]]
    ) -> Optional[List[str]]:
        if value is None:
            return value
        cleaned = [name.strip() for name in value]
        if any(not name for name in cleaned):
            raise ValueError("Vorname darf nicht leer sein")
        return cleaned


class PatientCreate(BaseModel):
    """Eingabemodell zum Anlegen eines Patienten."""

    model_config = ConfigDict(extra="forbid")

    name: List[HumanName] = Field(min_length=1, max_length=20)
    gender: Optional[Literal["male", "female", "other", "unknown"]] = None
    birthDate: Optional[date] = None

    @model_validator(mode="after")
    def birth_date_must_not_be_in_the_future(self) -> "PatientCreate":
        if self.birthDate is not None and self.birthDate > date.today():
            raise ValueError("Geburtsdatum darf nicht in der Zukunft liegen")
        return self


class PatientSearch(BaseModel):
    """Datensparsame Patientensuche ohne sensible Query-Parameter."""

    model_config = ConfigDict(extra="forbid")

    family: Optional[str] = Field(default=None, min_length=1, max_length=100)
    given: Optional[str] = Field(default=None, min_length=1, max_length=100)
    birthdate: Optional[date] = None


class PatientContextRequest(BaseModel):
    """Referenz auf einen Patienten für UI-Leseoperationen."""

    model_config = ConfigDict(extra="forbid")

    patientId: str = Field(pattern=r"^[A-Za-z0-9.-]{1,64}$")


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


class ClinicalRecordSearch(PatientContextRequest):
    recordType: ClinicalRecordType


VitalMeasurementType = Literal[
    "heart-rate",
    "blood-pressure",
    "temperature",
    "respiratory-rate",
    "oxygen-saturation",
    "pain",
    "morse-score",
    "mobility",
    "fall-history",
]


class VitalMeasurementCreate(PatientContextRequest):
    """UI contract for a bounded, server-mapped vital-sign Observation."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    measurementType: VitalMeasurementType
    encounterId: str = Field(pattern=r"^[A-Za-z0-9.-]{1,64}$")
    measuredAt: datetime
    value: Optional[float] = None
    systolic: Optional[float] = None
    diastolic: Optional[float] = None
    codedValue: Optional[
        Literal["independent", "needs-help", "dependent", "yes", "no"]
    ] = None

    @model_validator(mode="after")
    def validate_measurement(self) -> "VitalMeasurementCreate":
        if self.measuredAt.tzinfo is None or self.measuredAt.utcoffset() is None:
            raise ValueError("Messzeitpunkt muss eine Zeitzone enthalten")

        if self.measurementType == "blood-pressure":
            if (
                self.value is not None
                or self.systolic is None
                or self.diastolic is None
                or self.codedValue is not None
            ):
                raise ValueError(
                    "Blutdruck benötigt systolischen und diastolischen Wert"
                )
            if not 20 <= self.systolic <= 350 or not 20 <= self.diastolic <= 350:
                raise ValueError("Blutdruck liegt außerhalb der Erfassungsgrenzen")
            return self

        if self.measurementType in {"mobility", "fall-history"}:
            allowed = {
                "mobility": {"independent", "needs-help", "dependent"},
                "fall-history": {"yes", "no"},
            }
            if (
                self.codedValue not in allowed[self.measurementType]
                or self.value is not None
                or self.systolic is not None
                or self.diastolic is not None
            ):
                raise ValueError("Strukturierte Einschätzung hat einen ungültigen Wert")
            return self

        if (
            self.value is None
            or self.systolic is not None
            or self.diastolic is not None
            or self.codedValue is not None
        ):
            raise ValueError("Messung benötigt genau einen numerischen Wert")

        limits = {
            "heart-rate": (1, 400),
            "temperature": (20, 50),
            "respiratory-rate": (1, 150),
            "oxygen-saturation": (0, 100),
            "pain": (0, 10),
            "morse-score": (0, 125),
        }
        lower, upper = limits[self.measurementType]
        if not lower <= self.value <= upper:
            raise ValueError("Messwert liegt außerhalb der Erfassungsgrenzen")
        return self


class PatientAdmissionCreate(PatientCreate):
    """Patient and inpatient encounter created together."""

    admittedAt: datetime

    @field_validator("admittedAt")
    @classmethod
    def admission_time_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Aufnahmezeitpunkt muss eine Zeitzone enthalten")
        return value


class NursingReportCreate(PatientContextRequest):
    """Plain-text nursing report stored as a FHIR Composition."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=4000)
    encounterId: str = Field(pattern=r"^[A-Za-z0-9.-]{1,64}$")

    @field_validator("title", "text")
    @classmethod
    def report_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Text darf nicht leer sein")
        return value


class NursingReportCorrection(PatientContextRequest):
    model_config = ConfigDict(extra="forbid")

    reportId: str = Field(pattern=r"^[A-Za-z0-9.-]{1,64}$")
    expectedVersionId: str = Field(pattern=r"^[A-Za-z0-9.-]{1,64}$")
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=4000)

    @field_validator("title", "text")
    @classmethod
    def correction_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Text darf nicht leer sein")
        return value


class NursingReportErrorMark(PatientContextRequest):
    model_config = ConfigDict(extra="forbid")

    reportId: str = Field(pattern=r"^[A-Za-z0-9.-]{1,64}$")
    expectedVersionId: str = Field(pattern=r"^[A-Za-z0-9.-]{1,64}$")
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Korrekturgrund ist zu kurz")
        return value


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
    status: Literal["preliminary"]
    subject: RiskReference
    occurrenceDateTime: datetime
    method: RiskMethod
    extension: List[RiskExtension] = Field(default_factory=list)
    prediction: List[RiskPrediction]
    note: List[RiskNote]
