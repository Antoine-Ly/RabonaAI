import type { ApiError, ApiErrorBody } from "../types/api";
import { API_URL } from "./api";

/** Erreur renvoyée par l'API avant l'ouverture d'un flux (authentification, validation, quota…). */
export class ApiRequestError extends Error {
  readonly error: ApiError;
  readonly status: number;

  constructor(error: ApiError, status: number) {
    super(error.message);
    this.error = error;
    this.status = status;
  }
}

export async function toApiRequestError(response: Response): Promise<ApiRequestError> {
  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    if (body.error) return new ApiRequestError(body.error, response.status);
  } catch {
    // corps absent ou non JSON : message générique ci-dessous
  }
  return new ApiRequestError(
    {
      code: response.status === 401 ? "unauthorized" : "internal_error",
      message: `Erreur inattendue (HTTP ${response.status}).`,
      retry_after_seconds: null,
    },
    response.status,
  );
}

interface RequestOptions {
  method?: "GET" | "PATCH" | "DELETE";
  token: string;
  body?: unknown;
  signal?: AbortSignal;
}

/** Requête JSON authentifiée ; lève `ApiRequestError` si la réponse n'est pas un succès. */
export async function apiRequest<T>(path: string, { method = "GET", token, body, signal }: RequestOptions): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw await toApiRequestError(response);
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}
