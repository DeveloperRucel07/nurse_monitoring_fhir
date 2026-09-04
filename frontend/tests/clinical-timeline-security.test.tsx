import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ClinicalTimeline } from "../src/features/clinical/ClinicalTimeline";

describe("ClinicalTimeline security", () => {
  it("interpretiert Berichtsinhalte nicht als HTML", () => {
    const attack = '<img src=x onerror="alert(1)">';
    const { container } = render(
      <ClinicalTimeline
        observations={[]}
        events={[{ resourceType: "ClinicalImpression", label: "Pflegebericht", description: attack }]}
      />,
    );

    expect(screen.getByText(attack)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });
});
