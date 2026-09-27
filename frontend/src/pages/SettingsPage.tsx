import { useCallback } from "react";
import { AlertThresholdsCard } from "@/components/settings/AlertThresholdsCard";
import { AiSettingsCard } from "@/components/settings/AiSettingsCard";
import { BackupCard } from "@/components/settings/BackupCard";
import { CurrencyCard } from "@/components/settings/CurrencyCard";
import { PreferencesCard } from "@/components/settings/PreferencesCard";
import { useAppSettings } from "@/hooks/useSettings";
import { usePullToRefresh } from "@/hooks/usePullToRefresh";
import { t } from "@/lib/i18n";

export function SettingsPage() {
  // Purely informational — if the settings request hasn't answered yet (or is
  // unreachable), just show nothing rather than a loading/error state for
  // one line of fine print.
  const { data: appSettings, refetch } = useAppSettings();

  const { isRefreshing, pullDistance } = usePullToRefresh({
    onRefresh: useCallback(() => refetch(), [refetch]),
  });

  return (
    <div className="space-y-5">
      {/* Pull-to-refresh indicator (mobile) */}
      {pullDistance > 0 && (
        <div className="fixed left-1/2 top-4 z-50 -translate-x-1/2 rounded-full bg-surface-2 px-4 py-2 text-xs text-text-secondary shadow-lg">
          {isRefreshing ? t("common.loading") : pullDistance >= 80 ? t("common.releaseToRefresh") : t("common.pullToRefresh")}
        </div>
      )}
      <PreferencesCard />
      <CurrencyCard />
      <AiSettingsCard />
      <AlertThresholdsCard />
      <BackupCard />
      {appSettings?.app_version && (
        <p className="text-center text-xs text-text-muted">
          {t("settings.version", { version: appSettings.app_version })}
        </p>
      )}
    </div>
  );
}
