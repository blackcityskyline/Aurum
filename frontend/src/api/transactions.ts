import { api } from "@/api/client";
import type { Transaction, TransactionInput, TransactionPage } from "@/types";

export type TransactionSort = "date_desc" | "amount_desc" | "amount_asc";

export interface TransactionFilters {
  year?: number;
  month?: number;
  start_date?: string;
  end_date?: string;
  account_id?: number;
  category_id?: number;
  tag_id?: number;
  type?: string;
  search?: string;
  sort?: TransactionSort;
  page?: number;
  page_size?: number;
}

export function fetchTransactions(filters: TransactionFilters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null) params.set(key, String(value));
  });
  return api.get<TransactionPage>(`/transactions?${params.toString()}`);
}

/** Full range of years to offer in the year picker, from the earliest
 * transaction through the current year (see backend for the "gap year"
 * rationale). */
export function fetchTransactionYears() {
  return api.get<number[]>("/transactions/years");
}

export function createTransaction(input: TransactionInput) {
  return api.post<Transaction>("/transactions", input);
}

/** CSV import — see pages/CsvImportPage.tsx. All-or-nothing on the backend:
 * either every row is created, or (on a validation error) none are. */
export function bulkCreateTransactions(items: TransactionInput[]) {
  return api.post<{ created: number }>("/transactions/bulk", { items });
}

export function updateTransaction(id: number, input: Partial<TransactionInput>) {
  return api.patch<Transaction>(`/transactions/${id}`, input);
}

export function deleteTransaction(id: number) {
  return api.delete<void>(`/transactions/${id}`);
}

export interface PdfTransaction {
  date: string;
  description: string;
  amount: number;
  type: "income" | "expense";
}

export interface PdfImportResult {
  filename: string;
  transactions: PdfTransaction[];
  count: number;
}

export function importPdfStatement(file: File): Promise<PdfImportResult> {
  const formData = new FormData();
  formData.append("file", file);
  return api.post<PdfImportResult>("/transactions/import-pdf", formData);
}
