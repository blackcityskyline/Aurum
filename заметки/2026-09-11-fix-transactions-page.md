# Исправление: пустая страница транзакций

**Дата:** 2026-09-11

## Проблема

Страница транзакций (`/transactions`) была полностью пустая — ни одного элемента UI,
не работали кнопки, фильтры, поиск. Остальные страницы (дашборд, капитал и т.д.)
работали нормально.

### Ошибка в консоли

```
Uncaught TypeError: crypto.randomUUID is not a function
```

### Причина

`crypto.randomUUID()` доступен **только в secure context** (HTTPS или `localhost`).
Приложение открывалось по обычному HTTP через `192.168.1.10:3000`.

Вызов находился в `TransactionFormModal.tsx` в функции `emptySplitRow()`:

```tsx
function emptySplitRow(): SplitRowState {
  return { key: crypto.randomUUID(), category_id: "", amount: "", note: "" };
}
```

Модалка рендерилась даже в закрытом состоянии (`open={false}`), React вызывал
`useState` с дефолтным значением `[emptySplitRow(), emptySplitRow()]`, `crypto.randomUUID()`
падал, и **весь React-дерево крашилось** (в React 19 нет error boundary по умолчанию).

### Почему ломалась только страница транзакций

`TransactionFormModal` импортируется **только** в `TransactionsPage`. На других страницах
этот компонент не используется, поэтому `crypto.randomUUID()` вызывался только при
открытии `/transactions`.

## Исправление

Заменил `crypto.randomUUID()` на генерацию уникального ключа без зависимости от
secure context:

**Файл:** `frontend/src/components/transactions/TransactionFormModal.tsx`

```tsx
// Было:
function emptySplitRow(): SplitRowState {
  return { key: crypto.randomUUID(), category_id: "", amount: "", note: "" };
}

// Стало:
let _splitId = 0;
function emptySplitRow(): SplitRowState {
  return { key: `split-${++_splitId}-${Date.now()}`, category_id: "", amount: "", note: "" };
}
```

## Как откатить

### Полный откат (вернуть старый контейнер)

```bash
cd /home/black/docker/aurum
git checkout frontend/src/components/transactions/TransactionFormModal.tsx
echo "admin" | sudo -S docker compose build --no-cache web
echo "admin" | sudo -S docker compose up -d web
```

### Только откат изменений в коде (контейнер пересобирать не нужно)

```bash
cd /home/black/docker/aurum
git checkout frontend/src/components/transactions/TransactionFormModal.tsx
```

### Откат через git (если уже закоммичено)

```bash
cd /home/black/docker/aurum
git log --oneline -5                     # найти коммит
git revert <hash-коммита>                # откат конкретного коммита
echo "admin" | sudo -S docker compose build --no-cache web
echo "admin" | sudo -S docker compose up -d web
```
