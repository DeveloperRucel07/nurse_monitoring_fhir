import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, FilePenLine, FileText } from "lucide-react";
import { useState, type FormEvent } from "react";
import type { NursingReport } from "../../entities/clinical/model";
import {
  correctNursingReport,
  createNursingReport,
  getNursingReports,
  markNursingReportEnteredInError,
} from "../../shared/api/clinicalApi";
import { ApiError } from "../../shared/api/http";
import { ErrorState, LoadingState, PartialDataNotice } from "../../shared/components/States";
import { formatDateTime } from "../../shared/utils/format";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Der Pflegebericht konnte nicht verarbeitet werden.";
}

export function NursingReportForm({ patientId, encounterId }: { patientId: string; encounterId: string }) {
  const [editing, setEditing] = useState<NursingReport | null>(null);
  const [markingError, setMarkingError] = useState<NursingReport | null>(null);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [reason, setReason] = useState("");
  const [success, setSuccess] = useState("");
  const queryClient = useQueryClient();
  const reports = useQuery({ queryKey: ["nursing-reports", patientId], queryFn: () => getNursingReports(patientId) });
  const refresh = async () => queryClient.invalidateQueries({ queryKey: ["nursing-reports", patientId] });
  const save = useMutation({
    mutationFn: () => editing
      ? correctNursingReport(patientId, editing, title.trim(), text.trim())
      : createNursingReport(patientId, { encounterId, title: title.trim(), text: text.trim() }),
    onSuccess: async () => {
      setSuccess(editing ? "Korrigierte Version wurde gespeichert." : "Pflegebericht wurde gespeichert.");
      setEditing(null); setTitle(""); setText("");
      await refresh();
    },
  });
  const markError = useMutation({
    mutationFn: () => {
      if (!markingError) throw new Error("Kein Bericht ausgewählt");
      return markNursingReportEnteredInError(patientId, markingError, reason.trim());
    },
    onSuccess: async () => {
      setSuccess("Bericht wurde als fehlerhaft gekennzeichnet und bleibt in der Historie erhalten.");
      setMarkingError(null); setReason("");
      await refresh();
    },
  });
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); setSuccess(""); save.mutate(); };
  const beginCorrection = (report: NursingReport) => { setEditing(report); setTitle(report.title); setText(report.text); setSuccess(""); };

  return <div className="report-workspace">
    <form className="clinical-form" onSubmit={submit}>
      <div className="form-intro"><FileText aria-hidden="true" /><div><strong>{editing ? `Bericht Version ${editing.versionId} korrigieren` : "Pflegebericht verfassen"}</strong><p>Autor, aktiver Fall und FHIR-Version werden serverseitig gebunden.</p></div></div>
      <label><span>Titel *</span><input value={title} onChange={(event) => setTitle(event.target.value)} required minLength={1} maxLength={200} autoComplete="off" /></label>
      <label><span>Bericht *</span><textarea value={text} onChange={(event) => setText(event.target.value)} required minLength={1} maxLength={4000} rows={7} /></label>
      <p className="form-help">Korrekturen überschreiben keine Historie. Bei einem Versionskonflikt wird das Speichern abgelehnt.</p>
      {save.isError ? <p className="form-error" role="alert">{errorMessage(save.error)}</p> : null}
      {success ? <p className="form-success" role="status"><CheckCircle2 />{success}</p> : null}
      <div className="form-actions">{editing ? <button className="button button-secondary" type="button" onClick={() => { setEditing(null); setTitle(""); setText(""); }}>Korrektur abbrechen</button> : null}<button className="button button-primary" type="submit" disabled={save.isPending}>{save.isPending ? "Wird gespeichert …" : editing ? "Korrektur speichern" : "Pflegebericht speichern"}</button></div>
    </form>
    <div className="report-history" aria-label="Pflegeberichtshistorie">
      <div className="form-intro"><FilePenLine aria-hidden="true" /><div><strong>Berichtshistorie</strong><p>Aktuelle Ressourcenstände; frühere Versionen bleiben im FHIR-Verlauf erhalten.</p></div></div>
      {reports.isPending ? <LoadingState label="Pflegeberichte werden geladen" /> : reports.isError ? <ErrorState error={reports.error} onRetry={() => void reports.refetch()} /> : <><PartialDataNotice count={reports.data.rejectedCount} />{reports.data.items.length === 0 ? <p className="muted">Noch keine Pflegeberichte für diese Akte.</p> : <ul className="report-list">{reports.data.items.map((report) => <li key={report.id}><div><strong>{report.title}</strong><span>{formatDateTime(report.authoredAt)} · Version {report.versionId} · {report.status}</span><p>{report.text}</p><small>{report.author ?? "Autor nicht verfügbar"} · {report.identifier ?? "Berichts-ID nicht verfügbar"}</small></div>{report.status !== "entered-in-error" ? <div className="report-actions"><button className="button button-secondary" type="button" onClick={() => beginCorrection(report)}>Korrigieren</button><button className="button button-danger" type="button" onClick={() => { setMarkingError(report); setReason(""); }}>Fehlerhaft</button></div> : <span className="status-badge neutral">Nicht verwenden</span>}</li>)}</ul>}</>}
      {markingError ? <form className="error-mark-form" onSubmit={(event) => { event.preventDefault(); markError.mutate(); }}><div className="notice notice-critical"><AlertTriangle aria-hidden="true" /><span>Der Bericht wird nicht gelöscht, sondern revisionssicher als „entered-in-error“ markiert.</span></div><label><span>Korrekturgrund *</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} required minLength={3} maxLength={500} rows={3} /></label>{markError.isError ? <p className="form-error" role="alert">{errorMessage(markError.error)}</p> : null}<div className="form-actions"><button className="button button-secondary" type="button" onClick={() => setMarkingError(null)}>Abbrechen</button><button className="button button-danger" type="submit" disabled={markError.isPending}>Als fehlerhaft markieren</button></div></form> : null}
    </div>
  </div>;
}
