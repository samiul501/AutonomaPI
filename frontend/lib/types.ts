/** Mirrors backend/app/schemas/*.py — keep in sync with the FastAPI models. */

export type HttpMethod = "get" | "post" | "put" | "patch" | "delete" | "options" | "head";

export interface ParameterSpec {
  name: string;
  location: string;
  required: boolean;
  schema: Record<string, unknown>;
  description?: string | null;
}

export interface EndpointSpec {
  operation_id: string;
  path: string;
  method: HttpMethod;
  tags: string[];
  summary?: string | null;
  parameters: ParameterSpec[];
  request_body_schema?: Record<string, unknown> | null;
  request_body_required: boolean;
  response_schemas: Record<string, Record<string, unknown>>;
  security: string[];
  resource_name?: string | null;
}

export interface ParsedSpec {
  title: string;
  version: string;
  base_url?: string | null;
  security_schemes: Record<string, unknown>;
  endpoints: EndpointSpec[];
}

export interface AuthField {
  scheme: string;
  type: "bearer_token" | "basic_auth" | "api_key" | "oauth2_token";
  label: string;
  placeholder?: string;
  secret: boolean;
  location?: string;
  param_name?: string;
}

export interface IngestSpecResponse {
  spec_id: string;
  spec: ParsedSpec;
  auth_fields: AuthField[];
  method_detection?: { url: string; method: string; confirmed_by_server: boolean }[];
}

/** One hand-described endpoint for Quick Test — no Swagger doc involved. */
export interface QuickEndpointDraft {
  method: string; // "auto" | "GET" | "POST" | "PUT" | "PATCH" | "DELETE"
  url: string;
  bodyText: string; // raw JSON typed by the user; "" means no body
  public: boolean;
}

export type CaseCategory =
  | "positive"
  | "type_mismatch"
  | "missing_required"
  | "boundary"
  | "sql_injection"
  | "xss"
  | "auth_bypass"
  | "bola"
  | "dependency";

export type TestVerdict = "passed" | "failed" | "critical_leak" | "error";

export interface TestCase {
  id: string;
  endpoint_operation_id: string;
  method: string;
  path: string;
  category: CaseCategory;
  description: string;
  headers: Record<string, string>;
  query_params: Record<string, unknown>;
  path_params: Record<string, unknown>;
  body: unknown;
}

export interface TestResult {
  case: TestCase;
  status_code: number | null;
  elapsed_ms: number | null;
  verdict: TestVerdict;
  reason: string;
  response_snippet?: string | null;
  executed_at: string;
}

export type LogLevel = "info" | "thought" | "warning" | "success" | "error";

export interface LogEvent {
  run_id: string;
  level: LogLevel;
  message: string;
  timestamp: string;
}

export type RunStatus = "pending" | "running" | "completed" | "failed";

export interface RunMetrics {
  total_cases: number;
  passed: number;
  failed: number;
  critical_leaks: number;
  errors: number;
  success_rate: number;
}

export interface RunEvent {
  type: "log" | "result" | "metrics" | "status";
  payload: Record<string, unknown>;
}
