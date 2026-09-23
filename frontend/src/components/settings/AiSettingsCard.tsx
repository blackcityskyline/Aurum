import { useState } from "react";
import { Trash2, Pencil, CheckCircle2, Circle, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { PillSelector } from "@/components/layout/PillSelector";
import { AddProviderButton, ProviderDialog } from "@/components/settings/ProviderDialog";
import {
  useCreateLlmProvider,
  useDeleteLlmProvider,
  useLlmConfig,
  useTestLlmBackend,
  useUpdateLlmConfig,
  useUpdateLlmProvider,
} from "@/hooks/useLlm";
import { useTranslation } from "@/lib/i18n";
import type { LlmProvider } from "@/types/llm";

type Mode = "harness" | "api";

/** Settings → AI: which backend answers in the chat (opencode harness vs
 * any OpenAI-compatible API), the provider/key/model list for the api
 * mode, generation params, and a connectivity test. */
export function AiSettingsCard() {
  const { t } = useTranslation();
  const { data: config, isLoading } = useLlmConfig();
  const updateConfig = useUpdateLlmConfig();
  const createProvider = useCreateLlmProvider();
  const updateProvider = useUpdateLlmProvider();
  const deleteProvider = useDeleteLlmProvider();
  const testBackend = useTestLlmBackend();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<LlmProvider | null>(null);
  const [testResult, setTestResult] = useState<{ ok: boolean; detail: string } | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  if (isLoading || !config) {
    return (
      <Card>
        <CardContent className="p-4 text-sm text-text-muted sm:p-5">
          {t("common.loading")}
        </CardContent>
      </Card>
    );
  }

  const mode: Mode = config.mode === "api" ? "api" : "harness";

  const handleModeChange = (value: Mode) => {
    setTestResult(null);
    updateConfig.mutate({ mode: value });
  };

  const handleAdd = () => {
    setEditing(null);
    setDialogOpen(true);
  };

  const handleEdit = (provider: LlmProvider) => {
    setEditing(provider);
    setDialogOpen(true);
  };

  const handleSave = (values: {
    name: string;
    base_url: string;
    api_key: string | undefined;
    model: string;
    activate: boolean;
  }) => {
    const payload = {
      name: values.name,
      base_url: values.base_url,
      // "" (cleared) and undefined (kept) both end up as null/absent for
      // create — a new row just has no key yet.
      api_key: values.api_key ?? null,
      model: values.model || null,
      activate: values.activate,
    };
    if (editing) {
      // Editing must not silently flip the active flag — activation is
      // its own action (radio button in the card), and `activate` stays
      // omitted here so the backend leaves it untouched.
      updateProvider.mutate(
        {
          id: editing.id,
          patch: {
            name: values.name,
            base_url: values.base_url,
            // undefined → keep stored key; a typed value replaces it.
            ...(values.api_key !== undefined ? { api_key: values.api_key } : {}),
            model: values.model || null,
          },
        },
        { onSuccess: () => setDialogOpen(false) }
      );
    } else {
      createProvider.mutate(payload, { onSuccess: () => setDialogOpen(false) });
    }
  };

  const handleDelete = (id: number) => {
    if (confirmDeleteId !== id) {
      setConfirmDeleteId(id);
      return;
    }
    setConfirmDeleteId(null);
    deleteProvider.mutate(id);
  };

  const handleTest = () => {
    setTestResult(null);
    testBackend.mutate(undefined, {
      onSuccess: (data) => setTestResult(data),
      onError: (e) => setTestResult({ ok: false, detail: String(e) }),
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.aiTitle")}</CardTitle>
        <AddProviderButton onClick={handleAdd} />
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Backend switch: opencode harness vs OpenAI-compatible API */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-xs font-medium text-text-secondary">{t("settings.aiModeLabel")}</p>
            <p className="mt-0.5 text-xs text-text-muted">{t("settings.aiModeHint")}</p>
          </div>
          <PillSelector<Mode>
            options={[
              { value: "harness", label: t("settings.aiModeHarness") },
              { value: "api", label: t("settings.aiModeApi") },
            ]}
            value={mode}
            onChange={handleModeChange}
          />
        </div>

        {mode === "harness" ? (
          <div>
            <Label htmlFor="llm-harness-url">{t("settings.aiHarnessUrlLabel")}</Label>
            <div className="flex gap-2">
              <Input
                id="llm-harness-url"
                defaultValue={config.harness_url}
                placeholder="http://host.docker.internal:4096"
                onBlur={(e) => {
                  const value = e.target.value.trim();
                  if (value && value !== config.harness_url) {
                    updateConfig.mutate({ harness_url: value });
                  }
                }}
              />
            </div>
            <p className="mt-1 text-xs text-text-muted">{t("settings.aiHarnessUrlHint")}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {config.providers.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border p-4 text-center">
                <p className="text-sm text-text-secondary">{t("settings.aiNoProviders")}</p>
                <Button type="button" className="mt-2 h-8" onClick={handleAdd}>
                  {t("settings.aiAddProvider")}
                </Button>
              </div>
            ) : (
              <ul className="space-y-2">
                {config.providers.map((provider) => (
                  <li
                    key={provider.id}
                    className={`flex items-center gap-3 rounded-lg border p-3 ${
                      provider.is_active ? "border-primary/40 bg-primary/5" : "border-border"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() =>
                        !provider.is_active && updateConfig.mutate({ active_provider_id: provider.id })
                      }
                      title={t("settings.aiActivate")}
                      className="shrink-0 text-text-muted hover:text-primary"
                    >
                      {provider.is_active ? (
                        <CheckCircle2 size={18} className="text-primary" />
                      ) : (
                        <Circle size={18} />
                      )}
                    </button>

                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-text-primary">{provider.name}</p>
                      <p className="truncate text-xs text-text-muted">
                        {provider.base_url}
                        {provider.model ? ` · ${provider.model}` : ""}
                        {!provider.has_api_key ? ` · ${t("settings.aiNoKey")}` : ""}
                      </p>
                    </div>

                    <button
                      type="button"
                      onClick={() => handleEdit(provider)}
                      title={t("common.edit")}
                      className="shrink-0 text-text-muted hover:text-text-primary"
                    >
                      <Pencil size={15} />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(provider.id)}
                      title={
                        confirmDeleteId === provider.id
                          ? t("settings.aiConfirmDelete")
                          : t("common.delete")
                      }
                      className={`shrink-0 hover:text-danger ${
                        confirmDeleteId === provider.id ? "text-danger" : "text-text-muted"
                      }`}
                    >
                      <Trash2 size={15} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Generation params (api mode only — harness is tuned opencode-side) */}
        {mode === "api" && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <Label htmlFor="llm-max-tokens">{t("settings.aiMaxTokens")}</Label>
              <Input
                id="llm-max-tokens"
                type="number"
                min={256}
                max={32768}
                step={256}
                defaultValue={config.max_tokens}
                onBlur={(e) => {
                  const value = Math.min(32768, Math.max(256, Number(e.target.value) || 2048));
                  e.target.value = String(value);
                  if (value !== config.max_tokens) updateConfig.mutate({ max_tokens: value });
                }}
              />
            </div>
            <div>
              <Label htmlFor="llm-temperature">{t("settings.aiTemperature")}</Label>
              <Input
                id="llm-temperature"
                type="number"
                min={0}
                max={2}
                step={0.1}
                defaultValue={config.temperature}
                onBlur={(e) => {
                  const value = Math.min(2, Math.max(0, Number(e.target.value) || 0.7));
                  e.target.value = String(value);
                  if (value !== config.temperature) updateConfig.mutate({ temperature: value });
                }}
              />
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3">
          <Button
            type="button"
            variant="secondary"
            onClick={handleTest}
            disabled={testBackend.isPending || updateConfig.isPending}
          >
            {testBackend.isPending && <Loader2 size={14} className="animate-spin" />}
            {t("settings.aiTestConnection")}
          </Button>
          {testResult && (
            <p className={`text-xs ${testResult.ok ? "text-success" : "text-danger"}`}>
              {testResult.detail}
            </p>
          )}
          {(updateConfig.isPending || createProvider.isPending || updateProvider.isPending) && (
            <span className="text-xs text-text-muted">{t("common.saving")}</span>
          )}
        </div>
      </CardContent>

      <ProviderDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        provider={editing}
        onSave={handleSave}
        isPending={createProvider.isPending || updateProvider.isPending}
      />
    </Card>
  );
}
