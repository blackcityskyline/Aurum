import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { useFetchLlmModels } from "@/hooks/useLlm";
import { useTranslation } from "@/lib/i18n";
import type { LlmProvider } from "@/types/llm";

interface ProviderDialogProps {
  open: boolean;
  onClose: () => void;
  // null → creating a new provider.
  provider: LlmProvider | null;
  onSave: (values: {
    name: string;
    base_url: string;
    api_key: string | undefined;
    model: string;
    activate: boolean;
  }) => void;
  isPending: boolean;
}

/** Add/edit one API provider. The key field is always blank on open: the
 * server never returns the stored value, so blank means "keep as is" and
 * the placeholder states that explicitly. */
export function ProviderDialog({ open, onClose, provider, onSave, isPending }: ProviderDialogProps) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const fetchModels = useFetchLlmModels();

  useEffect(() => {
    if (!open) return;
    setName(provider?.name ?? "");
    setBaseUrl(provider?.base_url ?? "https://openrouter.ai/api/v1");
    setApiKey("");
    setModel(provider?.model ?? "");
    setModels([]);
    setModelsError(null);
  }, [open, provider]);

  const handleLoadModels = () => {
    setModelsError(null);
    fetchModels.mutate(
      // Saved row → use its stored key; unsaved/typed values → send what's
      // in the form (a freshly pasted key works before first save too).
      provider
        ? { provider_id: provider.id, base_url: baseUrl, api_key: apiKey || undefined }
        : { base_url: baseUrl, api_key: apiKey || undefined },
      {
        onSuccess: (data) => setModels(data.models),
        onError: (e) => setModelsError(e instanceof Error ? e.message : String(e)),
      }
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !baseUrl.trim()) return;
    onSave({
      name: name.trim(),
      base_url: baseUrl.trim(),
      // undefined → backend keeps the stored key; "" → clears it.
      api_key: apiKey === "" ? undefined : apiKey,
      model: model.trim(),
      activate: true,
    });
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={provider ? t("settings.aiEditProvider") : t("settings.aiAddProvider")}
    >
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="llm-provider-name">{t("settings.aiProviderName")}</Label>
          <Input
            id="llm-provider-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="OpenRouter"
            required
          />
        </div>

        <div>
          <Label htmlFor="llm-provider-url">{t("settings.aiProviderBaseUrl")}</Label>
          <Input
            id="llm-provider-url"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://openrouter.ai/api/v1"
            required
          />
        </div>

        <div>
          <Label htmlFor="llm-provider-key">{t("settings.aiProviderApiKey")}</Label>
          <Input
            id="llm-provider-key"
            type="password"
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={
              provider?.has_api_key ? t("settings.aiProviderKeyStored") : t("settings.aiProviderKeyOptional")
            }
          />
          <p className="mt-1 text-xs text-text-muted">{t("settings.aiProviderKeyHint")}</p>
        </div>

        <div>
          <Label htmlFor="llm-provider-model">{t("settings.aiProviderModel")}</Label>
          <div className="flex gap-2">
            <Input
              id="llm-provider-model"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="meta-llama/llama-3.3-70b-instruct:free"
              list="llm-model-catalogue"
            />
            <datalist id="llm-model-catalogue">
              {models.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
            <Button
              type="button"
              variant="secondary"
              onClick={handleLoadModels}
              disabled={fetchModels.isPending || !baseUrl.trim()}
              className="shrink-0"
            >
              {fetchModels.isPending ? t("common.loading") : t("settings.aiLoadModels")}
            </Button>
          </div>
          {modelsError ? (
            <p className="mt-1 text-xs text-danger">{modelsError}</p>
          ) : models.length > 0 ? (
            <p className="mt-1 text-xs text-text-muted">
              {t("settings.aiModelsLoaded", { count: models.length })}
            </p>
          ) : null}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={isPending}>
            {isPending ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function AddProviderButton({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation();
  return (
    <Button type="button" variant="secondary" onClick={onClick} className="h-8 px-2.5 text-xs">
      <Plus size={14} />
      {t("settings.aiAddProvider")}
    </Button>
  );
}
