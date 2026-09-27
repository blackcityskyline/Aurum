import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Upload } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Input";
import { useAccounts } from "@/hooks/useAccounts";
import { useBulkCreateTransactions } from "@/hooks/useTransactions";
import { importPdfStatement, type PdfTransaction } from "@/api/transactions";
import { formatCurrency } from "@/lib/format";
import { ApiError } from "@/api/client";
import { useTranslation } from "@/lib/i18n";
import type { TransactionInput } from "@/types";

export function PdfImportPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: accounts } = useAccounts();
  const bulkCreate = useBulkCreateTransactions();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [accountId, setAccountId] = useState("");
  const [isParsing, setIsParsing] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [transactions, setTransactions] = useState<PdfTransaction[] | null>(null);
  const [fileName, setFileName] = useState("");
  const [importError, setImportError] = useState<string | null>(null);
  const [createdCount, setCreatedCount] = useState<number | null>(null);

  async function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setIsParsing(true);
    setParseError(null);
    setTransactions(null);
    setFileName(file.name);

    try {
      const result = await importPdfStatement(file);
      setTransactions(result.transactions);
    } catch (error) {
      setParseError(
        error instanceof ApiError
          ? error.message
          : t("transactions.import.pdfParseError")
      );
    } finally {
      setIsParsing(false);
    }
  }

  async function handleImport() {
    if (!transactions || transactions.length === 0) return;

    setImportError(null);
    try {
      const items: TransactionInput[] = transactions.map((tx) => ({
        account_id: Number(accountId),
        category_id: null,
        transfer_account_id: null,
        type: tx.type,
        amount: Math.abs(tx.amount).toFixed(2),
        description: tx.description,
        merchant: null,
        notes: null,
        date: tx.date,
      }));

      const result = await bulkCreate.mutateAsync(items);
      setCreatedCount(result.created);
    } catch (error) {
      setImportError(
        error instanceof ApiError ? error.message : t("transactions.import.importError")
      );
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <Link
          to="/transactions"
          aria-label={t("common.back")}
          className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
        >
          <ArrowLeft size={18} />
        </Link>
        <h1 className="text-lg font-semibold text-text-primary">
          {t("transactions.import.pdfTitle")}
        </h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("transactions.import.accountLabel")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Select
            value={accountId}
            onChange={(event) => setAccountId(event.target.value)}
            className="sm:w-72"
          >
            <option value="" disabled>
              {t("transactions.form.selectAccount")}
            </option>
            {accounts?.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </Select>
          <p className="mt-2 text-xs text-text-muted">
            {t("transactions.import.accountHint")}
          </p>
        </CardContent>
      </Card>

      {!transactions && (
        <Card>
          <CardHeader>
            <CardTitle>{t("transactions.import.pdfUploadTitle")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-text-secondary">
              {t("transactions.import.pdfUploadHint")}
            </p>
            <Button
              onClick={() => fileInputRef.current?.click()}
              disabled={!accountId || isParsing}
            >
              <Upload size={16} />
              {isParsing
                ? t("transactions.import.pdfParsing")
                : t("transactions.import.pdfChooseFile")}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              onChange={handleFileSelected}
              className="hidden"
              accept=".pdf,application/pdf"
            />
            {!accountId && (
              <p className="text-xs text-text-muted">
                {t("transactions.import.pickAccountFirst")}
              </p>
            )}
            {parseError && <p className="text-sm text-danger">{parseError}</p>}
          </CardContent>
        </Card>
      )}

      {transactions && (
        <Card>
          <CardHeader>
            <CardTitle>{t("transactions.import.pdfPreviewTitle")}</CardTitle>
            <span className="text-xs text-text-muted">{fileName}</span>
          </CardHeader>
          <CardContent className="space-y-4">
            {createdCount !== null ? (
              <div className="space-y-3">
                <p className="text-sm text-success">
                  {t("transactions.import.pdfImportSuccess", { count: createdCount })}
                </p>
                <Button onClick={() => navigate("/transactions")}>
                  {t("transactions.import.goToTransactions")}
                </Button>
              </div>
            ) : (
              <>
                <p className="text-sm text-text-secondary">
                  {t("transactions.import.summary", {
                    valid: transactions.length,
                    skipped: 0,
                  })}
                </p>

                <div className="overflow-x-auto rounded-lg border border-border">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-surface-2 text-xs text-text-muted">
                      <tr>
                        <th className="px-3 py-2 font-medium">
                          {t("transactions.form.dateLabel")}
                        </th>
                        <th className="px-3 py-2 font-medium">
                          {t("transactions.form.descriptionLabel")}
                        </th>
                        <th className="px-3 py-2 text-right font-medium">
                          {t("transactions.form.amountLabel")}
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gridline">
                      {transactions.slice(0, 20).map((tx, index) => (
                        <tr key={index}>
                          <td className="whitespace-nowrap px-3 py-1.5 text-text-secondary">
                            {tx.date}
                          </td>
                          <td className="px-3 py-1.5 text-text-primary">
                            {tx.description}
                          </td>
                          <td
                            className={`whitespace-nowrap px-3 py-1.5 text-right tabular-nums ${
                              tx.type === "expense"
                                ? "text-text-primary"
                                : "text-success"
                            }`}
                          >
                            {tx.type === "expense" ? "-" : "+"}
                            {formatCurrency(Math.abs(tx.amount))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {transactions.length > 20 && (
                    <p className="border-t border-border px-3 py-2 text-xs text-text-muted">
                      {t("transactions.import.andMore", {
                        count: transactions.length - 20,
                      })}
                    </p>
                  )}
                </div>

                {importError && <p className="text-sm text-danger">{importError}</p>}

                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="ghost" onClick={() => setTransactions(null)}>
                    {t("common.back")}
                  </Button>
                  <Button
                    disabled={transactions.length === 0 || bulkCreate.isPending}
                    onClick={() => void handleImport()}
                  >
                    {bulkCreate.isPending
                      ? t("common.saving")
                      : t("transactions.import.pdfImportButton", {
                          count: transactions.length,
                        })}
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
