"""PDF statement import endpoint."""
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.services.pdf_import_service import parse_pdf_statement, PdfImportError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("/import-pdf")
async def import_pdf_statement(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Upload a PDF bank statement and extract transactions.
    
    Returns a list of parsed transactions for preview before import.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    
    try:
        transactions = parse_pdf_statement(content)
    except PdfImportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {
        "filename": file.filename,
        "transactions": transactions,
        "count": len(transactions),
    }
