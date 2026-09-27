import { useState, useCallback } from "react";
import { PillSelector } from "@/components/layout/PillSelector";
import { YearRangeSelector } from "@/components/layout/YearSelector";
import { CashFlowChart } from "@/components/cashflow/CashFlowChart";
import { useCashFlow } from "@/hooks/useCashFlow";
import { useTransactionYears } from "@/hooks/useTransactions";
import { usePullToRefresh } from "@/hooks/usePullToRefresh";
import { computeRange, type CustomYearRange, type RangePreset } from "@/lib/dateRange";
import { useTranslation } from "@/lib/i18n";

export function CashFlowPage() {
  const { t } = useTranslation();
  const now = new Date();
  const { data: years, refetch: refetchYears } = useTransactionYears();
  const [range, setRange] = useState<RangePreset>("this_year");
  const [customRange, setCustomRange] = useState<CustomYearRange>({
    fromYear: now.getFullYear(),
    toYear: now.getFullYear(),
  });

  const RANGE_OPTIONS: Array<{ value: RangePreset; label: string }> = [
    { value: "all", label: t("reports.rangeAll") },
    { value: "this_year", label: t("reports.rangeThisYear") },
    { value: "5y", label: t("reports.range5y") },
    { value: "custom", label: t("reports.rangeCustom") },
  ];

  const { startDate, endDate } = computeRange(range, customRange);
  const { data: cashFlow, isLoading, refetch } = useCashFlow(startDate, endDate);

  const { isRefreshing, pullDistance } = usePullToRefresh({
    onRefresh: useCallback(() => {
      refetch();
      refetchYears();
    }, [refetch, refetchYears]),
  });

  return (
    <div className="space-y-5">
      {/* Pull-to-refresh indicator (mobile) */}
      {pullDistance > 0 && (
        <div className="fixed left-1/2 top-4 z-50 -translate-x-1/2 rounded-full bg-surface-2 px-4 py-2 text-xs text-text-secondary shadow-lg">
          {isRefreshing ? t("common.loading") : pullDistance >= 80 ? t("common.releaseToRefresh") : t("common.pullToRefresh")}
        </div>
      )}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <PillSelector options={RANGE_OPTIONS} value={range} onChange={setRange} />
        {range === "custom" && (
          <YearRangeSelector
            years={years ?? [now.getFullYear()]}
            fromYear={customRange.fromYear}
            toYear={customRange.toYear}
            onChange={setCustomRange}
          />
        )}
      </div>

      <CashFlowChart cashFlow={cashFlow} isLoading={isLoading} />
    </div>
  );
}
