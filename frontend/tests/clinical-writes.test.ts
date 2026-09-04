import { afterEach, describe, expect, it, vi } from "vitest";
import {
  correctNursingReport,
  createNursingReport,
  admitPatient,
  createVitalMeasurement,
} from "../src/shared/api/clinicalApi";
import { setCsrfToken } from "../src/shared/api/http";

afterEach(() => {
  vi.unstubAllGlobals();
  setCsrfToken(null);
});

function jsonResponse(body: unknown, status = 201): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/fhir+json" },
  });
}

function requestJson(init: RequestInit): unknown {
  if (typeof init.body !== "string") throw new Error("JSON request body expected");
  return JSON.parse(init.body) as unknown;
}

describe("klinische Schreiboperationen", () => {
  it("übermittelt Patientenstammdaten im Body und keine erfundene Kennung", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      patient: { resourceType: "Patient", id: "patient-1", identifier: [{ use: "official", value: "PAT-1" }], name: [{ family: "Beispiel", given: ["Eva"] }] },
      encounter: { resourceType: "Encounter", id: "encounter-1", identifier: [{ use: "official", value: "FALL-1" }], status: "in-progress" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("csrf-test-value");

    const { patient, encounter } = await admitPatient({ family: "Beispiel", given: "Eva", admittedAt: "2026-09-04T08:00:00Z" });

    expect(patient.id).toBe("patient-1");
    expect(patient.identifier).toBe("PAT-1");
    expect(encounter.identifier).toBe("FALL-1");
    expect(fetchMock).toHaveBeenCalledWith("/api/ui/patients/admit", expect.anything());
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(requestJson(init)).toEqual({
      name: [{ family: "Beispiel", given: ["Eva"] }],
      admittedAt: "2026-09-04T08:00:00Z",
    });
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-test-value");
  });

  it("sendet nur den Messwertvertrag, keine frei wählbaren FHIR-Codes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      resourceType: "Observation",
      id: "observation-1",
      status: "final",
      code: { coding: [{ system: "http://loinc.org", code: "8867-4" }] },
      valueQuantity: { value: 82, unit: "/min", code: "/min" },
      effectiveDateTime: "2026-09-04T08:30:00Z",
    }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await createVitalMeasurement("patient-1", {
      measurementType: "heart-rate",
      encounterId: "encounter-1",
      measuredAt: "2026-09-04T08:30:00Z",
      value: 82,
    });

    expect(result).toEqual(expect.objectContaining({ kind: "heart-rate", value: 82 }));
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const payload = requestJson(init) as Record<string, unknown>;
    expect(payload).toEqual({
      patientId: "patient-1",
      measurementType: "heart-rate",
      encounterId: "encounter-1",
      measuredAt: "2026-09-04T08:30:00Z",
      value: 82,
    });
    expect(payload).not.toHaveProperty("code");
    expect(payload).not.toHaveProperty("unit");
  });

  it("behandelt Berichtsinhalte als Text und übernimmt den FHIR-Zeitpunkt", async () => {
    const attack = '<img src=x onerror="alert(1)">';
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      resourceType: "Composition",
      id: "report-1",
      meta: { versionId: "1" },
      identifier: { value: "BERICHT-1" },
      status: "final",
      title: "Pflegebericht",
      date: "2026-09-04T08:35:00Z",
      encounter: { reference: "Encounter/encounter-1" },
      author: [{ display: "Pflege Demo" }],
      section: [{ text: { status: "generated", div: '<div xmlns="http://www.w3.org/1999/xhtml"><p>&lt;img src=x onerror="alert(1)"&gt;</p></div>' } }],
    }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await createNursingReport("patient-1", {
      encounterId: "encounter-1",
      title: "Pflegebericht",
      text: attack,
    });

    expect(result.text).toBe(attack);
    expect(result.authoredAt).toBe("2026-09-04T08:35:00Z");
    expect(result.versionId).toBe("1");
  });

  it("sendet bei einer Korrektur die gelesene FHIR-Version", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      resourceType: "Composition",
      id: "report-1",
      meta: { versionId: "4" },
      status: "amended",
      title: "Korrigiert",
      section: [{ text: { div: '<div xmlns="http://www.w3.org/1999/xhtml"><p>Neu</p></div>' } }],
    }, 200));
    vi.stubGlobal("fetch", fetchMock);

    await correctNursingReport(
      "patient-1",
      { id: "report-1", versionId: "3", status: "final", title: "Alt", text: "Alt" },
      "Korrigiert",
      "Neu",
    );

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe("PUT");
    expect(requestJson(init)).toEqual({
      patientId: "patient-1",
      reportId: "report-1",
      expectedVersionId: "3",
      title: "Korrigiert",
      text: "Neu",
    });
  });
});
