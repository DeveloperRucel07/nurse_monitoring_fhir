import { z, type ZodType } from "zod";

const MAX_RESPONSE_BYTES = 5 * 1024 * 1024;
let csrfToken: string | null = null;
let authenticationFailureHandler: ((kind: "unauthorized" | "forbidden") => void) | null = null;

export type ApiErrorKind =
  | "unauthorized"
  | "forbidden"
  | "validation"
  | "not-found"
  | "network"
  | "invalid-response"
  | "server";

export class ApiError extends Error {
  constructor(
    public readonly kind: ApiErrorKind,
    public readonly status: number | undefined,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function setCsrfToken(value: string | null): void {
  csrfToken = value;
}

export function onAuthenticationFailure(handler: ((kind: "unauthorized" | "forbidden") => void) | null): void {
  authenticationFailureHandler = handler;
}

function classifyStatus(status: number): ApiErrorKind {
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not-found";
  if (status === 400 || status === 409 || status === 422) return "validation";
  return "server";
}

function safeErrorMessage(value: unknown, fallback: string): string {
  const schema = z.looseObject({
    detail: z.string().max(500).optional(),
    issue: z.array(z.looseObject({ diagnostics: z.string().max(500).optional() })).optional(),
  });
  const result = schema.safeParse(value);
  if (!result.success) return fallback;
  return result.data.detail ?? result.data.issue?.[0]?.diagnostics ?? fallback;
}

async function parseResponseBody(response: Response): Promise<unknown> {
  const length = Number(response.headers.get("content-length") ?? "0");
  if (Number.isFinite(length) && length > MAX_RESPONSE_BYTES) {
    throw new ApiError("invalid-response", response.status, "Die Serverantwort ist zu groß.");
  }
  const text = await response.text();
  if (new TextEncoder().encode(text).byteLength > MAX_RESPONSE_BYTES) {
    throw new ApiError("invalid-response", response.status, "Die Serverantwort ist zu groß.");
  }
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new ApiError("invalid-response", response.status, "Der Server hat ungültige Daten geliefert.");
  }
}

export async function apiRequest<T>(
  path: string,
  schema: ZodType<T>,
  options: { method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE"; body?: unknown } = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const headers = new Headers({ Accept: "application/fhir+json, application/json" });
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD"].includes(method) && csrfToken) headers.set("X-CSRF-Token", csrfToken);

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      cache: "no-store",
      redirect: "follow",
      ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}),
    });
  } catch {
    throw new ApiError("network", undefined, "Keine Verbindung zum Server.");
  }

  const payload = await parseResponseBody(response);
  if (!response.ok) {
    if (response.status === 401) authenticationFailureHandler?.("unauthorized");
    if (response.status === 403) authenticationFailureHandler?.("forbidden");
    throw new ApiError(
      classifyStatus(response.status),
      response.status,
      safeErrorMessage(payload, "Die Anfrage konnte nicht verarbeitet werden."),
    );
  }
  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new ApiError("invalid-response", response.status, "Klinische Daten konnten nicht sicher gelesen werden.");
  }
  return parsed.data;
}

export async function apiVoid(
  path: string,
  options: { method: "POST" | "DELETE"; body?: unknown },
): Promise<void> {
  const headers = new Headers();
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  let response: Response;
  try {
    response = await fetch(path, {
      method: options.method,
      headers,
      credentials: "same-origin",
      cache: "no-store",
      ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}),
    });
  } catch {
    throw new ApiError("network", undefined, "Keine Verbindung zum Server.");
  }
  if (!response.ok) {
    if (response.status === 401) authenticationFailureHandler?.("unauthorized");
    if (response.status === 403) authenticationFailureHandler?.("forbidden");
    const payload = await parseResponseBody(response);
    throw new ApiError(classifyStatus(response.status), response.status, safeErrorMessage(payload, "Aktion fehlgeschlagen."));
  }
}
