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
  harness_url: string;
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
  harness_url?: string;
  max_tokens?: number;
  temperature?: number;
  active_provider_id?: number | null;
}

export interface LlmModelsResponse {
  models: string[];
}

export interface LlmTestResponse {
  ok: boolean;
  detail: string;
}
