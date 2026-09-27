import { useState, useCallback } from "react";
import { Plus } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { RecurringList } from "@/components/recurring/RecurringList";
import { RecurringFormModal } from "@/components/recurring/RecurringFormModal";
import { useDeleteRecurring, usePostRecurring, useRecurring } from "@/hooks/useRecurring";
import { usePullToRefresh } from "@/hooks/usePullToRefresh";
import { useTranslation } from "@/lib/i18n";
import type { RecurringTransaction } from "@/types";

export function RecurringPage() {
  const { t } = useTranslation();
  const { data: items, isLoading, refetch } = useRecurring();
  const deleteRecurring = useDeleteRecurring();
  const postRecurring = usePostRecurring();

  const { isRefreshing, pullDistance } = usePullToRefresh({
    onRefresh: useCallback(() => refetch(), [refetch]),
  });

  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<RecurringTransaction | null>(null);

  function openCreateModal() {
    setEditingItem(null);
    setModalOpen(true);
  }

  function openEditModal(item: RecurringTransaction) {
    setEditingItem(item);
    setModalOpen(true);
  }

  function handleDelete(item: RecurringTransaction) {
    if (window.confirm(t("recurring.confirmDelete", { name: item.description }))) {
      deleteRecurring.mutate(item.id);
    }
  }

  function handlePost(item: RecurringTransaction) {
    postRecurring.mutate(item.id);
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
          <CardTitle>{t("nav.recurring")}</CardTitle>
          <Button onClick={openCreateModal}>
            <Plus size={16} />
            {t("common.add")}
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <RecurringList
              items={items ?? []}
              onPost={handlePost}
              onEdit={openEditModal}
              onDelete={handleDelete}
              isPosting={postRecurring.isPending}
            />
          )}
        </CardContent>
      </Card>

      <RecurringFormModal open={modalOpen} onClose={() => setModalOpen(false)} recurring={editingItem} />
    </div>
  );
}
