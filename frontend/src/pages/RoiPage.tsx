import { useState, useCallback } from "react";
import { RoiCalculatorCard } from "@/components/roi/RoiCalculatorCard";
import { RoiProjectionCard } from "@/components/roi/RoiProjectionCard";
import { usePullToRefresh } from "@/hooks/usePullToRefresh";

export function RoiPage() {
  const [investment, setInvestment] = useState("");
  const [monthlyIncome, setMonthlyIncome] = useState("");

  const investmentAmount = Number(investment);
  const monthlyAmount = Number(monthlyIncome);
  const hasInputs = investment !== "" && monthlyIncome !== "" && investmentAmount > 0;

  const annualIncome = monthlyAmount * 12;
  const annualRoiPercent = hasInputs ? (annualIncome / investmentAmount) * 100 : null;
  const paybackYears = annualRoiPercent !== null && annualIncome > 0 ? investmentAmount / annualIncome : null;

  const { isRefreshing, pullDistance } = usePullToRefresh({
    onRefresh: useCallback(() => {
      // ROI page is purely local calculation — no data to refetch
    }, []),
  });

  return (
    <div className="space-y-5">
      {/* Pull-to-refresh indicator (mobile) */}
      {pullDistance > 0 && (
        <div className="fixed left-1/2 top-4 z-50 -translate-x-1/2 rounded-full bg-surface-2 px-4 py-2 text-xs text-text-secondary shadow-lg">
          {isRefreshing ? "Loading…" : pullDistance >= 80 ? "Release to refresh" : "Pull to refresh"}
        </div>
      )}
      <RoiCalculatorCard
        investment={investment}
        onInvestmentChange={setInvestment}
        monthlyIncome={monthlyIncome}
        onMonthlyIncomeChange={setMonthlyIncome}
        annualRoiPercent={annualRoiPercent}
        paybackYears={paybackYears}
      />

      {annualRoiPercent !== null && (
        <RoiProjectionCard
          investmentAmount={investmentAmount}
          annualIncome={annualIncome}
          annualRoiPercent={annualRoiPercent}
        />
      )}
    </div>
  );
}
