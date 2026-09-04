from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import main
from backend.app.core import security


def claims(*roles: str) -> dict:
    return {
        "sub": "test-user",
        "azp": security.ALLOWED_CLIENT_ID,
        "resource_access": {security.API_AUDIENCE: {"roles": list(roles)}},
    }


class RecordingFhir:
    observation: dict | None = None
    resource: tuple[str, dict] | None = None

    def create_observation(self, resource: dict) -> dict:
        self.observation = resource
        return {**resource, "id": "observation-1"}

    def create_resource(self, resource_type: str, resource: dict) -> dict:
        self.resource = (resource_type, resource)
        return {**resource, "id": "report-1"}


def setup_function() -> None:
    main.app.dependency_overrides.clear()


def teardown_function() -> None:
    main.app.dependency_overrides.clear()


def test_writer_can_record_server_mapped_heart_rate(monkeypatch) -> None:
    fake = RecordingFhir()
    monkeypatch.setattr(main, "fhir", fake)
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_write"
    )

    response = TestClient(main.app).post(
        "/ui/patient/vital-measurements",
        json={
            "patientId": "patient-1",
            "measurementType": "heart-rate",
            "measuredAt": "2026-09-04T10:30:00+02:00",
            "value": 82,
        },
    )

    assert response.status_code == 201
    assert fake.observation is not None
    assert fake.observation["code"]["coding"][0]["code"] == "8867-4"
    assert fake.observation["valueQuantity"] == {
        "value": 82.0,
        "unit": "/min",
        "system": "http://unitsofmeasure.org",
        "code": "/min",
    }
    assert fake.observation["subject"]["reference"] == "Patient/patient-1"


def test_blood_pressure_has_fixed_component_codes(monkeypatch) -> None:
    fake = RecordingFhir()
    monkeypatch.setattr(main, "fhir", fake)
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_write"
    )

    response = TestClient(main.app).post(
        "/ui/patient/vital-measurements",
        json={
            "patientId": "patient-1",
            "measurementType": "blood-pressure",
            "measuredAt": "2026-09-04T10:30:00Z",
            "systolic": 128,
            "diastolic": 78,
        },
    )

    assert response.status_code == 201
    assert fake.observation is not None
    components = fake.observation["component"]
    assert [item["code"]["coding"][0]["code"] for item in components] == [
        "8480-6",
        "8462-4",
    ]
    assert all(item["valueQuantity"]["code"] == "mm[Hg]" for item in components)


def test_reader_cannot_write_vital_measurement(monkeypatch) -> None:
    fake = RecordingFhir()
    monkeypatch.setattr(main, "fhir", fake)
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_read"
    )

    response = TestClient(main.app).post(
        "/ui/patient/vital-measurements",
        json={
            "patientId": "patient-1",
            "measurementType": "heart-rate",
            "measuredAt": "2026-09-04T10:30:00Z",
            "value": 82,
        },
    )

    assert response.status_code == 403
    assert fake.observation is None


def test_manipulated_or_invalid_measurement_is_rejected(monkeypatch) -> None:
    fake = RecordingFhir()
    monkeypatch.setattr(main, "fhir", fake)
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_write"
    )
    client = TestClient(main.app)

    unknown = client.post(
        "/ui/patient/vital-measurements",
        json={
            "patientId": "patient-1",
            "measurementType": "custom-code",
            "measuredAt": "2026-09-04T10:30:00Z",
            "value": 42,
        },
    )
    impossible = client.post(
        "/ui/patient/vital-measurements",
        json={
            "patientId": "patient-1",
            "measurementType": "oxygen-saturation",
            "measuredAt": "2026-09-04T10:30:00Z",
            "value": 150,
        },
    )

    assert unknown.status_code == 422
    assert impossible.status_code == 422
    assert fake.observation is None


def test_nursing_report_is_plain_text_clinical_impression(monkeypatch) -> None:
    fake = RecordingFhir()
    monkeypatch.setattr(main, "fhir", fake)
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_write"
    )

    response = TestClient(main.app).post(
        "/ui/patient/nursing-reports",
        json={
            "patientId": "patient-1",
            "title": "Mobilität beobachtet",
            "text": "Patientin ging mit Unterstützung zum Waschbecken. <script>alert(1)</script>",
        },
    )

    assert response.status_code == 201
    assert fake.resource is not None
    resource_type, resource = fake.resource
    assert resource_type == "ClinicalImpression"
    assert resource["subject"]["reference"] == "Patient/patient-1"
    assert resource["description"].endswith("<script>alert(1)</script>")
    assert "date" in resource


def test_blank_report_is_rejected(monkeypatch) -> None:
    fake = RecordingFhir()
    monkeypatch.setattr(main, "fhir", fake)
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_write"
    )

    response = TestClient(main.app).post(
        "/ui/patient/nursing-reports",
        json={"patientId": "patient-1", "title": "   ", "text": "   "},
    )

    assert response.status_code == 422
    assert fake.resource is None
