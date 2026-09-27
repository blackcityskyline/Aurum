"""PDF bank statement parser — extracts transactions from PDF files.

Supports common bank statement formats (Sberbank, Tinkoff, Alfa-Bank, etc.)
by extracting text and tables from PDF and parsing transaction lines.
"""
import io
import logging
import re
from datetime import date, datetime
from typing import Any

import pdfplumber

logger = logging.getLogger(__name__)


class PdfImportError(Exception):
    """Raised when a PDF file cannot be parsed or contains no transactions."""
    pass


def parse_pdf_statement(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """Parse a PDF bank statement and extract transactions.
    
    Returns a list of dicts with keys: date, description, amount, type.
    Amount is positive for income, negative for expense.
    """
    transactions = []
    
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Try to extract tables first (many bank statements use tables)
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or len(row) < 3:
                            continue
                        tx = _parse_table_row(row)
                        if tx:
                            transactions.append(tx)
                
                # If no tables found, try text extraction
                if not tables:
                    text = page.extract_text()
                    if text:
                        text_transactions = _parse_text_block(text)
                        transactions.extend(text_transactions)
    except Exception as e:
        raise PdfImportError(f"Failed to parse PDF: {e}") from e
    
    if not transactions:
        raise PdfImportError("No transactions found in the PDF file")
    
    return transactions


def _parse_table_row(row: list[str | None]) -> dict[str, Any] | None:
    """Parse a table row into a transaction dict.
    
    Expected formats vary by bank, but common patterns:
    - [date, description, amount, balance]
    - [date, description, debit, credit, balance]
    """
    # Clean up cells
    cells = [c.strip() if c else "" for c in row]
    
    # Try to find date in first cell
    date_str = cells[0] if cells else ""
    parsed_date = _parse_date(date_str)
    if not parsed_date:
        return None
    
    # Try to find description (usually the longest text cell)
    description = ""
    for cell in cells[1:]:
        if cell and len(cell) > len(description) and not _is_amount(cell):
            description = cell
    
    if not description:
        return None
    
    # Try to find amount
    amount = None
    for cell in cells[1:]:
        if cell:
            parsed_amount = _parse_amount(cell)
            if parsed_amount is not None and parsed_amount != 0:
                amount = parsed_amount
                break
    
    if amount is None:
        return None
    
    return {
        "date": parsed_date,
        "description": description,
        "amount": amount,
        "type": "expense" if amount < 0 else "income",
    }


def _parse_text_block(text: str) -> list[dict[str, Any]]:
    """Parse a text block into transactions.
    
    Looks for lines with date + description + amount patterns.
    """
    transactions = []
    lines = text.split("\n")
    
    for line in lines:
        # Common patterns:
        # "01.01.2024 Покупка в магазине -1000.00"
        # "01.01.2024 Покупка в магазине 1000.00"
        # "2024-01-01 Покупка в магазине -1000.00"
        
        # Try to find date at the start
        date_match = re.match(r"^(\d{2}[.\-/]\d{2}[.\-/]\d{4}|\d{4}[.\-/]\d{2}[.\-/]\d{2})", line)
        if not date_match:
            continue
        
        date_str = date_match.group(1)
        parsed_date = _parse_date(date_str)
        if not parsed_date:
            continue
        
        # Try to find amount at the end
        amount_match = re.search(r"(-?\d[\d\s]*[.,]\d{2})\s*$", line)
        if not amount_match:
            continue
        
        amount_str = amount_match.group(1)
        amount = _parse_amount(amount_str)
        if amount is None or amount == 0:
            continue
        
        # Description is everything between date and amount
        desc_start = len(date_str)
        desc_end = line.rfind(amount_str)
        description = line[desc_start:desc_end].strip()
        
        if not description:
            continue
        
        transactions.append({
            "date": parsed_date,
            "description": description,
            "amount": amount,
            "type": "expense" if amount < 0 else "income",
        })
    
    return transactions


def _parse_date(date_str: str) -> str | None:
    """Parse a date string into ISO format (YYYY-MM-DD)."""
    date_str = date_str.strip()
    
    # Try DD.MM.YYYY
    match = re.match(r"^(\d{2})[.\-/](\d{2})[.\-/](\d{4})$", date_str)
    if match:
        day, month, year = match.groups()
        try:
            d = date(int(year), int(month), int(day))
            return d.isoformat()
        except ValueError:
            return None
    
    # Try YYYY-MM-DD
    match = re.match(r"^(\d{4})[.\-/](\d{2})[.\-/](\d{2})$", date_str)
    if match:
        year, month, day = match.groups()
        try:
            d = date(int(year), int(month), int(day))
            return d.isoformat()
        except ValueError:
            return None
    
    return None


def _parse_amount(amount_str: str) -> float | None:
    """Parse an amount string into a float."""
    if not amount_str:
        return None
    
    # Remove spaces and normalize
    amount_str = amount_str.strip().replace(" ", "").replace("\xa0", "")
    
    # Handle negative amounts
    is_negative = amount_str.startswith("-") or amount_str.startswith("(")
    amount_str = amount_str.replace("-", "").replace("(", "").replace(")", "")
    
    # Determine decimal separator
    if "," in amount_str and "." in amount_str:
        # Both present — last one is decimal
        if amount_str.rfind(",") > amount_str.rfind("."):
            amount_str = amount_str.replace(".", "").replace(",", ".")
        else:
            amount_str = amount_str.replace(",", "")
    elif "," in amount_str:
        # Only comma — could be decimal or thousands
        parts = amount_str.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            amount_str = amount_str.replace(",", ".")
        else:
            amount_str = amount_str.replace(",", "")
    
    try:
        amount = float(amount_str)
        return -amount if is_negative else amount
    except ValueError:
        return None


def _is_amount(cell: str) -> bool:
    """Check if a cell looks like an amount."""
    return bool(re.match(r"^-?[\d\s]+[.,]?\d*$", cell.strip()))
