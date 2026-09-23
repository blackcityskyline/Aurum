import { useQuery } from "@tanstack/react-query";
import { RotateCw } from "lucide-react";
import { fetchLlmModels } from "@/api/llm";
import { useLlmConfig, useUpdateLlmProvider } from "@/hooks/useLlm";
import { useTranslation } from "@/lib/i18n";

/** Chat header's model controls: shows which backend/model answers right
 * now and, in api mode, lets the user switch among the active provider's
 * catalogue (fetched live from its /models endpoint). Harness mode has no
 * picker — opencode owns its models on its side. */
export function ModelPicker() {
  const { t } = useTranslation();
  const { data: config } = useLlmConfig();
  const updateProvider = useUpdateLlmProvider();

  const activeProvider = config?.providers.find((p) => p.is_active) ?? null;
  const isApi = config?.mode === "api";

  const modelsQuery = useQuery({
    queryKey: ["llm", "models", activeProvider?.id],
    queryFn: () => fetchLlmModels({ provider_id: activeProvider!.id }),
    enabled: Boolean(isApi && activeProvider),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  if (!config) return null;

  if (!isApi) {
    return (
      <span
        className="rounded-full bg-surface-2 px-2.5 py-1 text-xs text-text-secondary"
        title={t("chat.backendHarnessHint")}
      >
        {t("chat.backendHarness")}
      </span>
    );
  }

  if (!activeProvider) {
    return (
      <a
        href="/settings"
        className="rounded-full bg-warning/15 px-2.5 py-1 text-xs text-warning hover:underline"
      >
        {t("chat.noProviderConfigured")}
      </a>
    );
  }

  const models = modelsQuery.data?.models ?? [];
  const current = activeProvider.model ?? "";
  const loadError = modelsQuery.isError;
  const loading = modelsQuery.isLoading;

  return (
    <div className="flex items-center gap-2">
      <span className="hidden text-xs text-text-muted sm:inline">{activeProvider.name}</span>
      {/* Disabled only while the catalogue is in flight: an empty or failed
          list still opens, so the arrow never looks dead — the placeholder
          option states what's going on instead. */}
      <select
        value={current}
        onChange={(e) =>
          updateProvider.mutate({ id: activeProvider.id, patch: { model: e.target.value } })
        }
        disabled={loading}
        title={loadError ? t("chat.modelsLoadError") : undefined}
        className="h-7 max-w-[14rem] rounded-lg border border-border bg-surface-1 px-2 text-xs text-text-primary outline-none focus:border-series-1 disabled:opacity-60"
      >
        {!current && (
          <option value="">{loading ? t("common.loading") : t("chat.modelUnknown")}</option>
        )}
        {current && !models.includes(current) && <option value={current}>{current}</option>}
        {models.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
      {loadError && (
        <button
          type="button"
          onClick={() => modelsQuery.refetch()}
          title={t("chat.modelsRetry")}
          aria-label={t("chat.modelsRetry")}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-text-muted hover:bg-surface-2 hover:text-text-primary"
        >
          <RotateCw size={13} />
        </button>
      )}
      {/* "Model tier" — free OpenRouter ids end with :free, everything
          else is a paid/bring-your-own-key model. Hidden until a model is
          actually picked, so an empty id doesn't claim to be paid. */}
      {current && (
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
            current.includes(":free")
              ? "bg-series-3/15 text-series-3"
              : "bg-surface-2 text-text-muted"
          }`}
        >
          {current.includes(":free") ? t("chat.modelTierFree") : t("chat.modelTierPaid")}
        </span>
      )}
    </div>
  );
}
