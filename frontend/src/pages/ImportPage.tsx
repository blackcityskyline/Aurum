import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Upload } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Label, Select } from "@/components/ui/Input";
import { useAccounts } from "@/hooks/useAccounts";
import { useCategories } from "@/hooks/useCategories";
import { useBulkCreateTransactions } from "@/hooks/useTransactions";
import { translateCategoryName } from "@/lib/categoryLabels";
import { DATE_FORMATS, parseAmount, parseCsv, parseDateWithFormat, type DateFormat } from "@/lib/csv";
import { formatCurrency } from "@/lib/format";
import { ApiError } from "@/api/client";
import { useTranslation } from "@/lib/i18n";
import { importPdfStatement, type PdfTransaction } from "@/api/transactions";
import type { TransactionInput } from "@/types";

type Step = "upload" | "map" | "preview";
type FileType = "csv" | "pdf" | null;

const NONE = "";

interface Mapping {
  date: string;
  amount: string;
  description: string;
  merchant: string;
  notes: string;
  category: string;
}

interface SkippedRow {
  row: number;
  reason: string;
}

export function ImportPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: accounts } = useAccounts();
  const { data: categories } = useCategories();
  const bulkCreate = useBulkCreateTransactions();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [accountId, setAccountId] = useState("");
  const [step, setStep] = useState<Step>("upload");
  const [fileName, setFileName] = useState("");
  const [fileType, setFileType] = useState<FileType>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [dataRows, setDataRows] = useState<string[][]>([]);
  const [mapping, setMapping] = useState<Mapping>({ date: "", amount: "", description: "", merchant: "", notes: "", category: "" });
  const [dateFormat, setDateFormat] = useState<DateFormat>("YYYY-MM-DD");
  const [parseError, setParseError] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [createdCount, setCreatedCount] = useState<number | null>(null);
  const [pdfTransactions, setPdfTransactions] = useState<PdfTransaction[] | null>(null);

  const categoryLookup = useMemo(() => {
    const map: Record<"income" | "expense", Map<string, number>> = { income: new Map(), expense: new Map() };
    for (const category of categories ?? []) {
      map[category.kind].set(category.name.trim().toLowerCase(), category.id);
      map[category.kind].set(translateCategoryName(category.name).trim().toLowerCase(), category.id);
    }
    return map;
  }, [categories]);

  function resolveType(amount: number): "income" | "expense" {
    return amount < 0 ? "expense" : "income";
  }

  const { valid, skipped } = useMemo(() => {
    if (step !== "preview") return { valid: [] as TransactionInput[], skipped: [] as SkippedRow[] };

    // PDF import — already parsed
    if (fileType === "pdf" && pdfTransactions) {
      const validRows: TransactionInput[] = pdfTransactions.map((tx) => ({
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
      return { valid: validRows, skipped: [] };
    }

    // CSV import
    const dateIdx = headers.indexOf(mapping.date);
    const amountIdx = headers.indexOf(mapping.amount);
    const descIdx = headers.indexOf(mapping.description);
    const merchantIdx = mapping.merchant ? headers.indexOf(mapping.merchant) : -1;
    const notesIdx = mapping.notes ? headers.indexOf(mapping.notes) : -1;
    const categoryIdx = mapping.category ? headers.indexOf(mapping.category) : -1;

    const validRows: TransactionInput[] = [];
    const skippedRows: SkippedRow[] = [];

    dataRows.forEach((cells, index) => {
      const rowNumber = index + 2;
      const rawDate = cells[dateIdx] ?? "";
      const rawAmount = cells[amountIdx] ?? "";
      const rawDescription = (cells[descIdx] ?? "").trim();
      const rawMerchant = merchantIdx >= 0 ? (cells[merchantIdx] ?? "").trim() : "";
      const rawNotes = notesIdx >= 0 ? (cells[notesIdx] ?? "").trim() : "";
      const rawCategory = categoryIdx >= 0 ? (cells[categoryIdx] ?? "").trim() : "";

      const isoDate = parseDateWithFormat(rawDate, dateFormat);
      if (!isoDate) {
        skippedRows.push({ row: rowNumber, reason: t("transactions.import.errorBadDate", { value: rawDate || "—" }) });
        return;
      }
      const amount = parseAmount(rawAmount);
      if (amount === null || amount === 0) {
        skippedRows.push({ row: rowNumber, reason: t("transactions.import.errorBadAmount", { value: rawAmount || "—" }) });
        return;
      }
      const description = rawDescription || rawMerchant;
      if (!description) {
        skippedRows.push({ row: rowNumber, reason: t("transactions.import.errorNoDescription") });
        return;
      }

      const type = resolveType(amount);
      const categoryId = rawCategory ? categoryLookup[type].get(rawCategory.toLowerCase()) ?? null : null;

      validRows.push({
        account_id: Number(accountId),
        category_id: categoryId,
        transfer_account_id: null,
        type,
        amount: Math.abs(amount).toFixed(2),
        description,
        merchant: rawMerchant || null,
        notes: rawNotes || null,
        date: isoDate,
      });
    });

    return { valid: validRows, skipped: skippedRows };
  }, [step, headers, dataRows, mapping, dateFormat, categoryLookup, accountId, t, fileType, pdfTransactions]);

  function detectFileType(file: File): FileType {
    if (file.name.toLowerCase().endsWith(".pdf") || file.type === "application/pdf") return "pdf";
    if (file.name.toLowerCase().endsWith(".csv") || file.type === "text/csv") return "csv";
    return null;
  }

  async function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    const type = detectFileType(file);
    if (!type) {
      setParseError(t("transactions.import.errorUnsupportedType"));
      return;
    }

    setParseError(null);
    setFileType(type);
    setFileName(file.name);

    if (type === "pdf") {
      // PDF — send to backend for parsing
      try {
        const result = await importPdfStatement(file);
        setPdfTransactions(result.transactions);
        setStep("preview");
      } catch (error) {
        setParseError(
          error instanceof ApiError ? error.message : t("transactions.import.pdfParseError")
        );
      }
      return;
    }

    // CSV — parse locally
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result ?? "");
      const rows = parseCsv(text);
      if (rows.length < 2) {
        setParseError(t("transactions.import.errorEmptyFile"));
        return;
      }
      const [headerRow, ...rest] = rows;
      setHeaders(headerRow);
      setDataRows(rest);
      const guess = (...candidates: string[]) =>
        headerRow.find((h) => candidates.includes(h.trim().toLowerCase())) ?? "";
      setMapping({
        date: guess("date", "дата"),
        amount: guess("amount", "сумма"),
        description: guess("description", "описание", "назначение платежа"),
        merchant: guess("merchant", "payee", "получатель"),
        notes: guess("notes", "заметка", "примечание"),
        category: guess("category", "категория"),
      });
      setStep("map");
    };
    reader.readAsText(file);
  }

  function startOver() {
    setStep("upload");
    setFileName("");
    setFileType(null);
    setHeaders([]);
    setDataRows([]);
    setPdfTransactions(null);
    setCreatedCount(null);
    setImportError(null);
  }

  async function handleImport() {
    setImportError(null);
    try {
      const result = await bulkCreate.mutateAsync(valid);
      setCreatedCount(result.created);
    } catch (error) {
      setImportError(error instanceof ApiError ? error.message : t("transactions.import.importError"));
    }
  }

  const mappingComplete = Boolean(mapping.date && mapping.amount && mapping.description);

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
        <h1 className="text-lg font-semibold text-text-primary">{t("transactions.import.title")}</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("transactions.import.accountLabel")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Select value={accountId} onChange={(event) => setAccountId(event.target.value)} className="sm:w-72">
            <option value="" disabled>
              {t("transactions.form.selectAccount")}
            </option>
            {accounts?.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </Select>
          <p className="mt-2 text-xs text-text-muted">{t("transactions.import.accountHint")}</p>
        </CardContent>
      </Card>

      {step === "upload" && (
        <Card>
          <CardHeader>
            <CardTitle>{t("transactions.import.uploadTitle")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-text-secondary">{t("transactions.import.uploadHint")}</p>
            <Button onClick={() => fileInputRef.current?.click()} disabled={!accountId}>
              <Upload size={16} />
              {t("transactions.import.chooseFile")}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              onChange={handleFileSelected}
              className="hidden"
              accept=".csv,.pdf,text/csv,application/pdf"
            />
            {!accountId && <p className="text-xs text-text-muted">{t("transactions.import.pickAccountFirst")}</p>}
            {parseError && <p className="text-sm text-danger">{parseError}</p>}
          </CardContent>
        </Card>
      )}

      {step === "map" && fileType === "csv" && (
        <Card>
          <CardHeader>
            <CardTitle>{t("transactions.import.mapTitle")}</CardTitle>
            <span className="text-xs text-text-muted">{fileName}</span>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <Label htmlFor="map-date">{t("transactions.import.dateColumnLabel")}</Label>
                <Select id="map-date" value={mapping.date} onChange={(event) => setMapping((prev) => ({ ...prev, date: event.target.value }))}>
                  <option value={NONE} disabled>
                    {t("transactions.import.selectColumn")}
                  </option>
                  {headers.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="map-date-format">{t("transactions.import.dateFormatLabel")}</Label>
                <Select id="map-date-format" value={dateFormat} onChange={(event) => setDateFormat(event.target.value as DateFormat)}>
                  {DATE_FORMATS.map((format) => (
                    <option key={format} value={format}>
                      {format}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="map-amount">{t("transactions.import.amountColumnLabel")}</Label>
                <Select id="map-amount" value={mapping.amount} onChange={(event) => setMapping((prev) => ({ ...prev, amount: event.target.value }))}>
                  <option value={NONE} disabled>
                    {t("transactions.import.selectColumn")}
                  </option>
                  {headers.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </Select>
                <p className="mt-1 text-xs text-text-muted">{t("transactions.import.amountHint")}</p>
              </div>
              <div>
                <Label htmlFor="map-description">{t("transactions.import.descriptionColumnLabel")}</Label>
                <Select
                  id="map-description"
                  value={mapping.description}
                  onChange={(event) => setMapping((prev) => ({ ...prev, description: event.target.value }))}
                >
                  <option value={NONE} disabled>
                    {t("transactions.import.selectColumn")}
                  </option>
                  {headers.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="map-merchant">{t("transactions.form.merchantLabel")}</Label>
                <Select id="map-merchant" value={mapping.merchant} onChange={(event) => setMapping((prev) => ({ ...prev, merchant: event.target.value }))}>
                  <option value={NONE}>{t("transactions.import.notMapped")}</option>
                  {headers.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="map-notes">{t("transactions.form.notesLabel")}</Label>
                <Select id="map-notes" value={mapping.notes} onChange={(event) => setMapping((prev) => ({ ...prev, notes: event.target.value }))}>
                  <option value={NONE}>{t("transactions.import.notMapped")}</option>
                  {headers.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="map-category">{t("transactions.form.categoryLabel")}</Label>
                <Select id="map-category" value={mapping.category} onChange={(event) => setMapping((prev) => ({ ...prev, category: event.target.value }))}>
                  <option value={NONE}>{t("transactions.import.notMapped")}</option>
                  {headers.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </Select>
                <p className="mt-1 text-xs text-text-muted">{t("transactions.import.categoryHint")}</p>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={startOver}>
                {t("transactions.import.startOver")}
              </Button>
              <Button disabled={!mappingComplete} onClick={() => setStep("preview")}>
                {t("transactions.import.previewButton")}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === "preview" && (
        <Card>
          <CardHeader>
            <CardTitle>{t("transactions.import.previewTitle")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {createdCount !== null ? (
              <div className="space-y-3">
                <p className="text-sm text-success">{t("transactions.import.importSuccess", { count: createdCount })}</p>
                <Button onClick={() => navigate("/transactions")}>{t("transactions.import.goToTransactions")}</Button>
              </div>
            ) : (
              <>
                <p className="text-sm text-text-secondary">
                  {t("transactions.import.summary", { valid: valid.length, skipped: skipped.length })}
                </p>

                {valid.length > 0 && (
                  <div className="overflow-x-auto rounded-lg border border-border">
                    <table className="w-full text-left text-sm">
                      <thead className="bg-surface-2 text-xs text-text-muted">
                        <tr>
                          <th className="px-3 py-2 font-medium">{t("transactions.form.dateLabel")}</th>
                          <th className="px-3 py-2 font-medium">{t("transactions.form.descriptionLabel")}</th>
                          <th className="px-3 py-2 font-medium">{t("transactions.form.categoryLabel")}</th>
                          <th className="px-3 py-2 text-right font-medium">{t("transactions.form.amountLabel")}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gridline">
                        {valid.slice(0, 20).map((item, index) => (
                          <tr key={index}>
                            <td className="whitespace-nowrap px-3 py-1.5 text-text-secondary">{item.date}</td>
                            <td className="px-3 py-1.5 text-text-primary">{item.description}</td>
                            <td className="whitespace-nowrap px-3 py-1.5 text-text-secondary">
                              {categories?.find((c) => c.id === item.category_id)
                                ? translateCategoryName(categories.find((c) => c.id === item.category_id)!.name)
                                : "—"}
                            </td>
                            <td
                              className={`whitespace-nowrap px-3 py-1.5 text-right tabular-nums ${
                                item.type === "expense" ? "text-text-primary" : "text-success"
                              }`}
                            >
                              {item.type === "expense" ? "-" : "+"}
                              {formatCurrency(item.amount)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {valid.length > 20 && (
                      <p className="border-t border-border px-3 py-2 text-xs text-text-muted">
                        {t("transactions.import.andMore", { count: valid.length - 20 })}
                      </p>
                    )}
                  </div>
                )}

                {skipped.length > 0 && (
                  <div className="max-h-40 overflow-y-auto rounded-lg border border-border bg-surface-2 p-3 text-xs text-text-muted">
                    {skipped.map((row) => (
                      <p key={row.row}>{t("transactions.import.skippedRow", { row: row.row, reason: row.reason })}</p>
                    ))}
                  </div>
                )}

                {importError && <p className="text-sm text-danger">{importError}</p>}

                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="ghost" onClick={() => setStep("map")}>
                    {t("common.back")}
                  </Button>
                  <Button disabled={valid.length === 0 || bulkCreate.isPending} onClick={() => void handleImport()}>
                    {bulkCreate.isPending
                      ? t("common.saving")
                      : t("transactions.import.importButton", { count: valid.length })}
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
