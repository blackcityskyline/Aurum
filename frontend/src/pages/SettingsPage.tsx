import { AlertThresholdsCard } from "@/components/settings/AlertThresholdsCard";
import { AiSettingsCard } from "@/components/settings/AiSettingsCard";
import { BackupCard } from "@/components/settings/BackupCard";
import { CurrencyCard } from "@/components/settings/CurrencyCard";
import { PreferencesCard } from "@/components/settings/PreferencesCard";
import { useHealth } from "@/hooks/useHealth";
import { t } from "@/lib/i18n";

export function SettingsPage() {
  // Purely informational — if /api/health hasn't answered yet (or is
  // unreachable), just show nothing rather than a loading/error state for
  // one line of fine print.
  const { data: health } = useHealth();

  return (
    <div className="space-y-5">
      <PreferencesCard />
      <CurrencyCard />
      <AiSettingsCard />
      <AlertThresholdsCard />
      <BackupCard />
      {health?.version && (
        <p className="text-center text-xs text-text-muted">
          {t("settings.version", { version: health.version })}
        </p>
      )}
    </div>
  );
}
