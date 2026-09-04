import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createNursingReport,
  createPatient,
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
      resourceType: "Patient",
      id: "patient-1",
      name: [{ family: "Beispiel", given: ["Eva"] }],
    }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("csrf-test-value");

    const patient = await createPatient({ family: "Beispiel", given: "Eva" });

    expect(patient.id).toBe("patient-1");
    expect(fetchMock).toHaveBeenCalledWith("/api/Patient", expect.anything());
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(requestJson(init)).toEqual({
      name: [{ family: "Beispiel", given: ["Eva"] }],
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
      measuredAt: "2026-09-04T08:30:00Z",
      value: 82,
    });

    expect(result).toEqual(expect.objectContaining({ kind: "heart-rate", value: 82 }));
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const payload = requestJson(init) as Record<string, unknown>;
    expect(payload).toEqual({
      patientId: "patient-1",
      measurementType: "heart-rate",
      measuredAt: "2026-09-04T08:30:00Z",
      value: 82,
    });
    expect(payload).not.toHaveProperty("code");
    expect(payload).not.toHaveProperty("unit");
  });

  it("behandelt Berichtsinhalte als Text und übernimmt den FHIR-Zeitpunkt", async () => {
    const attack = '<img src=x onerror="alert(1)">';
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      resourceType: "ClinicalImpression",
      id: "report-1",
      status: "completed",
      summary: "Pflegebericht",
      description: attack,
      date: "2026-09-04T08:35:00Z",
    }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await createNursingReport("patient-1", {
      title: "Pflegebericht",
      text: attack,
    });

    expect(result.description).toBe(attack);
    expect(result.occurredAt).toBe("2026-09-04T08:35:00Z");
  });
});
