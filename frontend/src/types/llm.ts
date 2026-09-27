// Chat AI backend configuration (Settings → AI) — mirrors
// backend/app/schemas/llm.py.
export type LlmMode = "harness" | "api" | "stub";

export interface LlmProvider {
  id: number;
  name: string;
  base_url: string;
  model: string | null;
  // The stored key is never sent back — this flag only says "one exists".
  has_api_key: boolean;
  is_active: boolean;
}

export interface LlmSettings {
  mode: LlmMode;
  // Which harness driver answers (registry key) and which model inside
  // it to pin — null = the harness's own default.
  harness_type: string;
  harness_url: string;
  harness_model: string | null;
  max_tokens: number;
  temperature: number;
  active_provider_id: number | null;
  providers: LlmProvider[];
}

export interface LlmProviderInput {
  name: string;
  base_url: string;
  api_key?: string | null;
  model?: string | null;
  activate?: boolean;
}

export interface LlmProviderPatch {
  name?: string;
  base_url?: string;
  // undefined → keep the stored key; "" → clear it.
  api_key?: string;
  model?: string | null;
  activate?: boolean;
}

export interface LlmConfigPatch {
  mode?: "harness" | "api";
  harness_type?: string;
  harness_url?: string;
  // "" or null → clear the pin, fall back to the harness default.
  harness_model?: string | null;
  max_tokens?: number;
  temperature?: number;
  active_provider_id?: number | null;
}

export interface LlmModelsResponse {
  models: string[];
}

/** Generic harness model row — `id` is an opaque driver-side string. */
export interface HarnessModel {
  id: string;
  label: string;
  provider: string;
  context: number | null;
  tool_calling: boolean;
}

export interface HarnessModelsResponse {
  models: HarnessModel[];
}

export interface LlmTestResponse {
  ok: boolean;
  detail: string;
}
