import { useState, useCallback } from "react";
import { Plus } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { GoalList } from "@/components/goals/GoalList";
import { GoalFormModal } from "@/components/goals/GoalFormModal";
import { GoalContributionModal } from "@/components/goals/GoalContributionModal";
import { useDeleteGoal, useGoals } from "@/hooks/useGoals";
import { usePullToRefresh } from "@/hooks/usePullToRefresh";
import { useTranslation } from "@/lib/i18n";
import type { Goal } from "@/types";

export function GoalsPage() {
  const { t } = useTranslation();
  const { data: goals, isLoading, refetch } = useGoals();
  const deleteGoal = useDeleteGoal();

  const { isRefreshing, pullDistance } = usePullToRefresh({
    onRefresh: useCallback(() => refetch(), [refetch]),
  });

  const [formOpen, setFormOpen] = useState(false);
  const [editingGoal, setEditingGoal] = useState<Goal | null>(null);
  const [contributionOpen, setContributionOpen] = useState(false);
  const [contributingGoal, setContributingGoal] = useState<Goal | null>(null);

  function openCreateModal() {
    setEditingGoal(null);
    setFormOpen(true);
  }

  function openEditModal(goal: Goal) {
    setEditingGoal(goal);
    setFormOpen(true);
  }

  function openContributionModal(goal: Goal) {
    setContributingGoal(goal);
    setContributionOpen(true);
  }

  function handleDelete(goal: Goal) {
    if (window.confirm(t("goal.confirmDelete", { name: goal.name }))) {
      deleteGoal.mutate(goal.id);
    }
  }

  return (
    <div className="space-y-5">
      {/* Pull-to-refresh indicator (mobile) */}
      {pullDistance > 0 && (
        <div className="fixed left-1/2 top-4 z-50 -translate-x-1/2 rounded-full bg-surface-2 px-4 py-2 text-xs text-text-secondary shadow-lg">
          {isRefreshing ? t("common.loading") : pullDistance >= 80 ? t("common.releaseToRefresh") : t("common.pullToRefresh")}
        </div>
      )}
      <Card>
        <CardHeader>
          <CardTitle>{t("nav.goals")}</CardTitle>
          <Button onClick={openCreateModal}>
            <Plus size={16} />
            {t("common.add")}
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <GoalList
              items={goals ?? []}
              onContribute={openContributionModal}
              onEdit={openEditModal}
              onDelete={handleDelete}
            />
          )}
        </CardContent>
      </Card>

      <GoalFormModal open={formOpen} onClose={() => setFormOpen(false)} goal={editingGoal} />
      <GoalContributionModal
        open={contributionOpen}
        onClose={() => setContributionOpen(false)}
        goal={contributingGoal}
      />
    </div>
  );
}
