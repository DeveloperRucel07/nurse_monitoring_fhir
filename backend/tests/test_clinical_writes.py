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
    updated: tuple[str, str, dict, str] | None = None
    transaction_bundle: dict | None = None

    def create_observation(self, resource: dict) -> dict:
        self.observation = resource
        return {**resource, "id": "observation-1"}

    def create_resource(self, resource_type: str, resource: dict) -> dict:
        self.resource = (resource_type, resource)
        return {**resource, "id": "report-1", "meta": {"versionId": "1"}}

    def get_resource(self, resource_type: str, resource_id: str) -> dict:
        if resource_type == "Encounter":
            return {
                "resourceType": "Encounter",
                "id": resource_id,
                "status": "in-progress",
                "subject": {"reference": "Patient/patient-1"},
            }
        return {
            "resourceType": "Composition",
            "id": resource_id,
            "meta": {"versionId": "1"},
            "status": "final",
            "subject": {"reference": "Patient/patient-1"},
            "author": [{"identifier": {"value": "test-user"}}],
            "title": "Alt",
        }

    def update_resource(
        self,
        resource_type: str,
        resource_id: str,
        resource: dict,
        *,
        expected_version_id: str,
    ) -> dict:
        self.updated = (resource_type, resource_id, resource, expected_version_id)
        return {**resource, "meta": {"versionId": "2"}}

    def transaction(self, bundle: dict) -> dict:
        self.transaction_bundle = bundle
        return {
            "resourceType": "Bundle",
            "type": "transaction-response",
            "entry": [
                {"resource": {**bundle["entry"][0]["resource"], "id": "patient-1"}},
                {"resource": {**bundle["entry"][1]["resource"], "id": "encounter-1"}},
            ],
        }


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
            "encounterId": "encounter-1",
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
            "encounterId": "encounter-1",
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
            "encounterId": "encounter-1",
            "measurementType": "heart-rate",
            "measuredAt": "2026-09-04T10:30:00Z",
            "value": 82,
        },
    )

    assert response.status_code == 403
    assert fake.observation is None


def test_nurse_cannot_bypass_safe_contract_with_raw_fhir_write(monkeypatch) -> None:
    fake = RecordingFhir()
    monkeypatch.setattr(main, "fhir", fake)
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_write"
    )

    response = TestClient(main.app).post(
        "/Observation",
        json={
            "status": "final",
            "code": {
                "coding": [{"system": "https://attacker.invalid", "code": "fabricated"}]
            },
            "subject": {"reference": "Patient/patient-1"},
            "valueQuantity": {
                "value": 42,
                "unit": "unknown",
                "code": "unknown",
            },
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
            "encounterId": "encounter-1",
            "measurementType": "custom-code",
            "measuredAt": "2026-09-04T10:30:00Z",
            "value": 42,
        },
    )
    impossible = client.post(
        "/ui/patient/vital-measurements",
        json={
            "patientId": "patient-1",
            "encounterId": "encounter-1",
            "measurementType": "oxygen-saturation",
            "measuredAt": "2026-09-04T10:30:00Z",
            "value": 150,
        },
    )

    assert unknown.status_code == 422
    assert impossible.status_code == 422
    assert fake.observation is None


def test_nursing_report_is_authored_encounter_bound_composition(monkeypatch) -> None:
    fake = RecordingFhir()
    monkeypatch.setattr(main, "fhir", fake)
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_write"
    )

    response = TestClient(main.app).post(
        "/ui/patient/nursing-reports",
        json={
            "patientId": "patient-1",
            "encounterId": "encounter-1",
            "title": "Mobilität beobachtet",
            "text": "Patientin ging mit Unterstützung zum Waschbecken. <script>alert(1)</script>",
        },
    )

    assert response.status_code == 201
    assert fake.resource is not None
    resource_type, resource = fake.resource
    assert resource_type == "Composition"
    assert resource["subject"]["reference"] == "Patient/patient-1"
    assert resource["encounter"]["reference"] == "Encounter/encounter-1"
    assert resource["type"]["coding"][0]["code"] == "34746-8"
    assert resource["author"][0]["identifier"]["value"] == "test-user"
    narrative = resource["section"][0]["text"]["div"]
    assert "<script>" not in narrative
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in narrative
    assert resource["status"] == "final"
    assert "date" in resource


def test_blank_report_is_rejected(monkeypatch) -> None:
    fake = RecordingFhir()
    monkeypatch.setattr(main, "fhir", fake)
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_write"
    )

    response = TestClient(main.app).post(
        "/ui/patient/nursing-reports",
        json={
            "patientId": "patient-1",
            "encounterId": "encounter-1",
            "title": "   ",
            "text": "   ",
        },
    )

    assert response.status_code == 422
    assert fake.resource is None


def test_patient_and_encounter_are_created_in_one_transaction(monkeypatch) -> None:
    fake = RecordingFhir()
    monkeypatch.setattr(main, "fhir", fake)
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_write"
    )

    response = TestClient(main.app).post(
        "/ui/patients/admit",
        json={
            "name": [{"family": "Test", "given": ["Tina"]}],
            "birthDate": "1980-01-02",
            "admittedAt": "2026-09-04T10:00:00Z",
        },
    )

    assert response.status_code == 201
    assert fake.transaction_bundle is not None
    assert fake.transaction_bundle["type"] == "transaction"
    patient, encounter = [
        entry["resource"] for entry in fake.transaction_bundle["entry"]
    ]
    assert patient["identifier"][0]["value"].startswith("PAT-")
    assert encounter["identifier"][0]["value"].startswith("FALL-")
    assert encounter["subject"]["reference"].startswith("urn:uuid:")


def test_report_correction_uses_optimistic_concurrency(monkeypatch) -> None:
    fake = RecordingFhir()
    monkeypatch.setattr(main, "fhir", fake)
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_write"
    )

    response = TestClient(main.app).put(
        "/ui/patient/nursing-reports",
        json={
            "patientId": "patient-1",
            "reportId": "report-1",
            "expectedVersionId": "1",
            "title": "Korrigiert",
            "text": "Korrigierter Inhalt",
        },
    )

    assert response.status_code == 200
    assert fake.updated is not None
    assert fake.updated[2]["status"] == "amended"
    assert fake.updated[3] == "1"


def test_report_correction_rejects_stale_version(monkeypatch) -> None:
    fake = RecordingFhir()
    monkeypatch.setattr(main, "fhir", fake)
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_write"
    )

    response = TestClient(main.app).put(
        "/ui/patient/nursing-reports",
        json={
            "patientId": "patient-1",
            "reportId": "report-1",
            "expectedVersionId": "0",
            "title": "Veraltet",
            "text": "Dieser Stand darf nicht gespeichert werden.",
        },
    )

    assert response.status_code == 409
    assert fake.updated is None


def test_non_author_cannot_correct_report(monkeypatch) -> None:
    fake = RecordingFhir()
    monkeypatch.setattr(main, "fhir", fake)
    main.app.dependency_overrides[security.get_current_client] = lambda: {
        **claims("pflege_write"),
        "sub": "different-user",
    }

    response = TestClient(main.app).put(
        "/ui/patient/nursing-reports",
        json={
            "patientId": "patient-1",
            "reportId": "report-1",
            "expectedVersionId": "1",
            "title": "Nicht erlaubt",
            "text": "Dieser Nutzer ist nicht der Autor.",
        },
    )

    assert response.status_code == 403
    assert fake.updated is None


def test_marking_report_as_error_preserves_resource(monkeypatch) -> None:
    fake = RecordingFhir()
    monkeypatch.setattr(main, "fhir", fake)
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_write"
    )

    response = TestClient(main.app).post(
        "/ui/patient/nursing-reports/entered-in-error",
        json={
            "patientId": "patient-1",
            "reportId": "report-1",
            "expectedVersionId": "1",
            "reason": "Falscher Patientenkontext",
        },
    )

    assert response.status_code == 200
    assert fake.updated is not None
    assert fake.updated[2]["status"] == "entered-in-error"
    assert fake.updated[2]["extension"][-1]["valueString"] == (
        "Falscher Patientenkontext"
    )


def test_structured_mobility_uses_loinc_answer_codes(monkeypatch) -> None:
    fake = RecordingFhir()
    monkeypatch.setattr(main, "fhir", fake)
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_write"
    )

    response = TestClient(main.app).post(
        "/ui/patient/vital-measurements",
        json={
            "patientId": "patient-1",
            "encounterId": "encounter-1",
            "measurementType": "mobility",
            "measuredAt": "2026-09-04T10:30:00Z",
            "codedValue": "needs-help",
        },
    )

    assert response.status_code == 201
    assert fake.observation["code"]["coding"][0]["code"] == "83186-7"
    assert fake.observation["valueCodeableConcept"]["coding"][0]["code"] == "LA12303-6"
