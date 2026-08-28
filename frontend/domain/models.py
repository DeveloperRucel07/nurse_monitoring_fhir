from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Patient:
    id: str
    given_name: str
    family_name: str
    gender: str
    birth_date: str

    @property
    def display_name(self) -> str:
        return f"{self.given_name} {self.family_name}".strip()


@dataclass(frozen=True)
class Observation:
    id: str
    display: str
    code: str
    value: str
    effective: str


@dataclass(frozen=True)
class RiskResult:
    label: str
    probability: float | None
    status: str
    missing_features: str


RISK_LABELS: dict[str, str] = {
    "fall": "Sturzrisiko",
    "clinical_deterioration": "Klinische Verschlechterung",
    "pain_escalation": "Schmerzeskalation",
    "pressure_ulcer": "Dekubitusrisiko",
}


def parse_patient(resource: dict[str, Any]) -> Patient:
    name = (resource.get("name") or [{}])[0]
    given = " ".join(name.get("given") or [])
    return Patient(
        id=str(resource.get("id", "")),
        given_name=given,
        family_name=str(name.get("family", "")),
        gender=str(resource.get("gender") or "Nicht angegeben"),
        birth_date=str(resource.get("birthDate") or "Nicht angegeben"),
    )


def parse_observation(resource: dict[str, Any]) -> Observation:
    coding = ((resource.get("code") or {}).get("coding") or [{}])[0]
    quantity = resource.get("valueQuantity") or {}
    value = quantity.get("value")
    unit = quantity.get("unit") or quantity.get("code") or ""
    if value is None and resource.get("component"):
        parts = []
        for component in resource["component"]:
            component_code = ((component.get("code") or {}).get("coding") or [{}])[0]
            component_value = component.get("valueQuantity") or {}
            parts.append(f"{component_code.get('display', 'Wert')}: {component_value.get('value', 'n. a.')} {component_value.get('unit', '')}".strip())
        value_text = " | ".join(parts)
    else:
        value_text = f"{value} {unit}".strip() if value is not None else "Kein Wert"
    return Observation(
        id=str(resource.get("id", "")),
        display=str(coding.get("display") or coding.get("code") or "Observation"),
        code=str(coding.get("code") or ""),
        value=value_text,
        effective=str(resource.get("effectiveDateTime") or "Nicht angegeben"),
    )
