import { useState, useCallback } from "react";
import { Plus } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { AccountList } from "@/components/accounts/AccountList";
import { AccountFormModal } from "@/components/accounts/AccountFormModal";
import { useAccounts, useDeleteAccount, useUpdateAccount } from "@/hooks/useAccounts";
import { usePullToRefresh } from "@/hooks/usePullToRefresh";
import { useTranslation } from "@/lib/i18n";
import type { Account, AccountWithBalance } from "@/types";

export function AccountsPage() {
  const { t } = useTranslation();
  const [showArchived, setShowArchived] = useState(false);
  const { data: accounts, isLoading, refetch } = useAccounts(showArchived);
  const updateAccount = useUpdateAccount();
  const deleteAccount = useDeleteAccount();

  const { isRefreshing, pullDistance } = usePullToRefresh({
    onRefresh: useCallback(() => refetch(), [refetch]),
  });

  const [modalOpen, setModalOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);

  function openCreateModal() {
    setEditingAccount(null);
    setModalOpen(true);
  }

  function openEditModal(account: Account) {
    setEditingAccount(account);
    setModalOpen(true);
  }

  function handleToggleArchived(account: AccountWithBalance) {
    updateAccount.mutate({ id: account.id, input: { is_archived: !account.is_archived } });
  }

  function handleDelete(account: AccountWithBalance) {
    if (window.confirm(t("account.confirmDelete", { name: account.name }))) {
      deleteAccount.mutate(account.id);
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
          <CardTitle>{t("nav.accounts")}</CardTitle>
          <Button onClick={openCreateModal}>
            <Plus size={16} />
            {t("common.add")}
          </Button>
        </CardHeader>
        <CardContent>
          <label className="mb-3 flex items-center gap-2 text-xs text-text-muted">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(event) => setShowArchived(event.target.checked)}
              className="h-3.5 w-3.5 accent-text-primary"
            />
            {t("account.showArchived")}
          </label>
          {isLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <AccountList
              items={accounts ?? []}
              onEdit={openEditModal}
              onToggleArchived={handleToggleArchived}
              onDelete={handleDelete}
            />
          )}
        </CardContent>
      </Card>

      <AccountFormModal open={modalOpen} onClose={() => setModalOpen(false)} account={editingAccount} />
    </div>
  );
}
