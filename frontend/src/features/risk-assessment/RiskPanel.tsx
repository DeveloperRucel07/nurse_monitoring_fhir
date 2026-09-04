import { AlertTriangle, Info, ShieldAlert } from "lucide-react";
import type { RiskAssessment } from "../../entities/clinical/model";
import { formatDateTime } from "../../shared/utils/format";

export function RiskPanel({ assessment }: { assessment: RiskAssessment }) {
  return <div className="risk-panel">
    <div className="notice notice-critical"><ShieldAlert aria-hidden="true" /><span><strong>Nicht klinisch validierte Simulation.</strong> Keine Diagnose, Triage- oder Behandlungsgrundlage.</span></div>
    <dl className="assessment-meta"><div><dt>Zeitpunkt</dt><dd>{formatDateTime(assessment.calculatedAt)}</dd></div><div><dt>Assessment-ID</dt><dd>{assessment.id ?? "Nicht vergeben"}</dd></div><div><dt>Methode / Modellversion</dt><dd>{assessment.method ?? "Nicht verfügbar"}</dd></div><div><dt>Status</dt><dd>{assessment.status}</dd></div></dl>
    <div className="prediction-grid">{assessment.predictions.map((prediction, index) => <article key={`${prediction.label}-${index}`}><span><AlertTriangle aria-hidden="true" />Risikobewertung</span><h3>{prediction.label}</h3>{prediction.probability !== undefined ? <strong>{new Intl.NumberFormat("de-DE", { style: "percent", maximumFractionDigits: 0 }).format(prediction.probability)}</strong> : <strong className="missing">Nicht berechenbar</strong>}<p>{prediction.probability !== undefined ? "Modellausgabe; keine validierte Ereigniswahrscheinlichkeit." : "Für die Bewertung fehlen klinische Daten."}</p>{prediction.missingFeatures.length ? <small>Fehlende Features: {prediction.missingFeatures.join(", ")}</small> : null}</article>)}</div>
    {assessment.note ? <p className="assessment-note"><Info aria-hidden="true" />{assessment.note}</p> : null}
  </div>;
}
