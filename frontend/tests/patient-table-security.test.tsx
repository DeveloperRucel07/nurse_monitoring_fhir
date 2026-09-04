import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { PatientContextProvider } from "../src/features/patients/PatientContext";
import { PatientTable } from "../src/features/patients/PatientTable";

describe("PatientTable security", () => {
  it("rendert unbekannte Namen ausschließlich als Text", () => {
    const { container } = render(
      <MemoryRouter>
        <PatientContextProvider>
          <PatientTable patients={[{ id: "p1", displayName: '<img src=x onerror="alert(1)">', gender: "Nicht verfügbar" }]} />
        </PatientContextProvider>
      </MemoryRouter>,
    );

    expect(screen.getByText('<img src=x onerror="alert(1)">')).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });
});
