import { Activity, ClipboardList, HeartPulse, Pill, ShieldAlert, Stethoscope } from "lucide-react";
import type { ReactNode } from "react";
import type { ClinicalEvent, VitalSign } from "../../entities/clinical/model";
import { formatDateTime } from "../../shared/utils/format";

type TimelineItem = { key: string; label: string; type: string; at?: string; detail: string; icon: ReactNode };

function vitalDetail(vital: VitalSign): string {
  if (vital.kind === "blood-pressure" && vital.systolic !== undefined && vital.diastolic !== undefined) return `${vital.systolic} / ${vital.diastolic} ${vital.unit ?? ""}`.trim();
  if (vital.value !== undefined) return `${vital.value} ${vital.unit ?? ""}`.trim();
  return vital.textValue ?? "Messwert nicht verfügbar";
}

function eventIcon(type: string): ReactNode {
  if (type.includes("Medication")) return <Pill />;
  if (type === "Condition") return <Stethoscope />;
  if (type === "AllergyIntolerance") return <ShieldAlert />;
  return <ClipboardList />;
}

export function ClinicalTimeline({ observations, events }: { observations: VitalSign[]; events: ClinicalEvent[] }) {
  const items: TimelineItem[] = [
    ...observations.map((item, index) => ({ key: `o-${item.id ?? index}`, label: item.label, type: "Observation", ...(item.measuredAt ? { at: item.measuredAt } : {}), detail: vitalDetail(item), icon: item.kind === "heart-rate" ? <HeartPulse /> : <Activity /> })),
    ...events.map((item, index) => ({ key: `e-${item.id ?? index}`, label: item.label, type: item.resourceType, ...(item.occurredAt ? { at: item.occurredAt } : {}), detail: item.description ?? item.status ?? "Details nicht verfügbar", icon: eventIcon(item.resourceType) })),
  ].sort((a, b) => (b.at ?? "").localeCompare(a.at ?? ""));
  if (items.length === 0) return <p className="muted">Keine darstellbaren klinischen Ereignisse vorhanden.</p>;
  return <ol className="timeline">{items.slice(0, 50).map((item) => <li key={item.key}><span className="timeline-icon">{item.icon}</span><div className="timeline-time"><time dateTime={item.at}>{formatDateTime(item.at)}</time><small>{item.type}</small></div><div><strong>{item.label}</strong><p>{item.detail}</p></div></li>)}</ol>;
}
