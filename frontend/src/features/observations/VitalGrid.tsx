import { Activity, Gauge, HeartPulse, PersonStanding, Thermometer, Wind } from "lucide-react";
import type { ReactNode } from "react";
import type { VitalKind, VitalSign } from "../../entities/clinical/model";
import { formatDateTime } from "../../shared/utils/format";

const icon: Partial<Record<VitalKind, ReactNode>> = {
  "heart-rate": <HeartPulse />,
  "blood-pressure": <Gauge />,
  temperature: <Thermometer />,
  "respiratory-rate": <Wind />,
  mobility: <PersonStanding />,
  "morse-score": <Activity />,
};

function reading(vital?: VitalSign): string {
  if (!vital) return "Nicht verfügbar";
  if (vital.kind === "blood-pressure") {
    return vital.systolic !== undefined && vital.diastolic !== undefined
      ? `${vital.systolic} / ${vital.diastolic} ${vital.unit ?? ""}`.trim()
      : "Nicht verfügbar";
  }
  if (vital.value !== undefined) return `${vital.value} ${vital.unit ?? ""}`.trim();
  return vital.textValue ?? "Nicht verfügbar";
}

export function VitalGrid({ observations }: { observations: VitalSign[] }) {
  const latest = new Map<VitalKind, VitalSign>();
  for (const observation of [...observations].sort((a, b) => (b.measuredAt ?? "").localeCompare(a.measuredAt ?? ""))) {
    if (!latest.has(observation.kind)) latest.set(observation.kind, observation);
  }
  const cards: Array<[VitalKind, string]> = [
    ["blood-pressure", "Blutdruck"], ["heart-rate", "Herzfrequenz"], ["temperature", "Temperatur"],
    ["respiratory-rate", "Atemfrequenz"], ["mobility", "Mobilität"], ["morse-score", "Morse Fall Scale"],
  ];
  return <div className="vital-grid">{cards.map(([kind, label]) => {
    const vital = latest.get(kind);
    return <article className="vital-card" key={kind}><span className="vital-icon">{icon[kind] ?? <Activity />}</span><div><small>{label}</small><strong className={!vital ? "missing" : ""}>{reading(vital)}</strong><span>{formatDateTime(vital?.measuredAt)}</span><span>Status: {vital?.status ?? "nicht verfügbar"} · Quelle: {vital?.source ?? "nicht verfügbar"}</span></div></article>;
  })}</div>;
}
