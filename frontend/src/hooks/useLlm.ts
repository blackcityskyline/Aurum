import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createLlmProvider,
  deleteLlmProvider,
  fetchHarnessModels,
  fetchLlmConfig,
  fetchLlmModels,
  testLlmBackend,
  updateLlmConfig,
  updateLlmProvider,
} from "@/api/llm";
import type {
  LlmConfigPatch,
  LlmProviderInput,
  LlmProviderPatch,
} from "@/types/llm";

const CONFIG_KEY = ["llm", "config"];
const HARNESS_MODELS_KEY = ["llm", "harness-models"];

export function useLlmConfig() {
  return useQuery({ queryKey: CONFIG_KEY, queryFn: fetchLlmConfig });
}

/** Harness model catalogue — only worth fetching in harness mode (the
 * catalogue itself is a capability: a driver without one returns 400 and
 * the picker falls back to a plain badge). */
export function useHarnessModels() {
  const { data: config } = useLlmConfig();
  return useQuery({
    queryKey: HARNESS_MODELS_KEY,
    queryFn: fetchHarnessModels,
    enabled: config?.mode === "harness",
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

/** Every mutation below invalidates the config query — the card is one
 * logical state (mode + providers + active one), so a partial response
 * would drift from what the server actually stored. */
export function useUpdateLlmConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: LlmConfigPatch) => updateLlmConfig(patch),
    onSuccess: (data) => queryClient.setQueryData(CONFIG_KEY, data),
  });
}

export function useCreateLlmProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: LlmProviderInput) => createLlmProvider(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CONFIG_KEY }),
  });
}

export function useUpdateLlmProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: LlmProviderPatch }) =>
      updateLlmProvider(id, patch),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CONFIG_KEY }),
  });
}

export function useDeleteLlmProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteLlmProvider(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CONFIG_KEY }),
  });
}

/** Manual "load models" action (not a query): it usually fires against a
 * not-yet-saved base_url/api_key typed into the form. */
export function useFetchLlmModels() {
  return useMutation({
    mutationFn: (body: { base_url?: string; api_key?: string; provider_id?: number }) =>
      fetchLlmModels(body),
  });
}

export function useTestLlmBackend() {
  return useMutation({ mutationFn: testLlmBackend });
}
