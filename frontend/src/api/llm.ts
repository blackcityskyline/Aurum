import { api } from "@/api/client";
import type {
  HarnessModelsResponse,
  LlmConfigPatch,
  LlmModelsResponse,
  LlmProvider,
  LlmProviderInput,
  LlmProviderPatch,
  LlmSettings,
  LlmTestResponse,
} from "@/types/llm";

export function fetchLlmConfig() {
  return api.get<LlmSettings>("/llm/config");
}

export function updateLlmConfig(patch: LlmConfigPatch) {
  return api.patch<LlmSettings>("/llm/config", patch);
}

export function createLlmProvider(input: LlmProviderInput) {
  return api.post<LlmProvider>("/llm/providers", input);
}

export function updateLlmProvider(id: number, patch: LlmProviderPatch) {
  return api.patch<LlmProvider>(`/llm/providers/${id}`, patch);
}

export function deleteLlmProvider(id: number) {
  return api.delete<void>(`/llm/providers/${id}`);
}

/** Model catalogue from a provider's /models endpoint — pass values from
 * an unsaved form too (provider_id takes precedence when given). */
export function fetchLlmModels(body: {
  base_url?: string;
  api_key?: string;
  provider_id?: number;
}) {
  return api.post<LlmModelsResponse>("/llm/models", {
    base_url: body.base_url ?? "",
    api_key: body.api_key,
    provider_id: body.provider_id,
  });
}

/** Cheap connectivity check of the currently configured backend. */
export function testLlmBackend() {
  return api.post<LlmTestResponse>("/llm/test", {});
}

/** Model catalogue of the active harness driver (opencode /provider →
 * connected providers only). Generic rows — no opencode specifics here. */
export function fetchHarnessModels() {
  return api.get<HarnessModelsResponse>("/llm/harness/models");
}
