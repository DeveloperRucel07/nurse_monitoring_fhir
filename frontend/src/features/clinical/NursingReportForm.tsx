import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileText } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { createNursingReport } from "../../shared/api/clinicalApi";
import { ApiError } from "../../shared/api/http";

function text(values: FormData, name: string): string {
  const value = values.get(name);
  return typeof value === "string" ? value.trim() : "";
}

export function NursingReportForm({ patientId }: { patientId: string }) {
  const formRef = useRef<HTMLFormElement>(null);
  const [success, setSuccess] = useState(false);
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (input: { title: string; text: string }) => createNursingReport(patientId, input),
    onSuccess: async () => {
      formRef.current?.reset();
      setSuccess(true);
      await queryClient.invalidateQueries({ queryKey: ["clinical-records", patientId, "ClinicalImpression"] });
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSuccess(false);
    const values = new FormData(event.currentTarget);
    mutation.mutate({ title: text(values, "title"), text: text(values, "text") });
  };
  const errorMessage = mutation.error instanceof ApiError
    ? mutation.error.message
    : "Der Pflegebericht konnte nicht gespeichert werden.";

  return (
    <form ref={formRef} className="clinical-form" onSubmit={submit}>
      <div className="form-intro"><FileText aria-hidden="true" /><div><strong>Pflegebericht verfassen</strong><p>Nur sachliche, erforderliche und überprüfte Angaben dokumentieren.</p></div></div>
      <label><span>Titel *</span><input name="title" required minLength={1} maxLength={200} autoComplete="off" /></label>
      <label><span>Bericht *</span><textarea name="text" required minLength={1} maxLength={4000} rows={7} /></label>
      <p className="form-help">Der Inhalt wird ausschließlich als Klartext verarbeitet; HTML wird nicht interpretiert.</p>
      {mutation.isError ? <p className="form-error" role="alert">{errorMessage}</p> : null}
      {success ? <p className="form-success" role="status"><CheckCircle2 />Pflegebericht wurde gespeichert.</p> : null}
      <div className="form-actions"><button className="button button-primary" type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Wird gespeichert …" : "Pflegebericht speichern"}</button></div>
    </form>
  );
}
