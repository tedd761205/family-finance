
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import check_database_connection

# --------------------------------------------------
# Routers
# --------------------------------------------------

from app.routers.auth import router as auth_router
from app.routers.family import router as family_router
from app.routers.family_invitations import router as family_invitations_router
from app.routers.roles import router as family_roles_router
from app.routers.audit_log import router as audit_log_router
from app.routers.account import router as account_router
from app.routers.category import router as category_router
from app.routers.bill import router as bill_router
from app.routers.bill_payment import router as bill_payment_router
from app.routers.attachment import router as attachment_router
from app.routers.ocr_task import router as ocr_task_router
from app.routers.recurring_bill import router as recurring_bill_router
from app.routers.transaction import router as transaction_router
from app.routers.transfer import router as transfer_router

from app.routers.credit_card_payment import (
    router as credit_card_payment_router,
)

from app.routers.household_report import (
    router as household_report_router,
)

from app.routers.monthly_report import (
    router as monthly_report_router,
)

from app.routers.daily_report import (
    router as daily_report_router,
)

from app.routers.yearly_report import (
    router as yearly_report_router,
)

from app.routers.category_report import (
    router as category_report_router,
)

from app.routers.account_report import (
    router as account_report_router,
)

from app.routers.account_transaction import (
    router as account_transaction_router,
)

from app.routers.account_overview import (
    router as account_overview_router,
)
from app.routers.g01_07 import router as g01_07_router
from app.routers.bank_import import router as bank_import_router
from app.routers.reconciliation import router as reconciliation_router
from app.routers.einvoice import router as einvoice_router


# --------------------------------------------------
# FastAPI Application
# --------------------------------------------------

app = FastAPI(
    title="家庭記帳系統",
    description="全家共用的家庭財務管理系統",
    version="1.0.0",
)


# --------------------------------------------------
# Register Routers
# --------------------------------------------------

app.include_router(auth_router)
app.include_router(family_router)
app.include_router(family_invitations_router)
app.include_router(family_roles_router)
app.include_router(audit_log_router)
app.include_router(account_router)
app.include_router(category_router)
app.include_router(bill_router)
app.include_router(bill_payment_router)
app.include_router(attachment_router)
app.include_router(ocr_task_router)
app.include_router(recurring_bill_router)
app.include_router(transaction_router)
app.include_router(transfer_router)
app.include_router(credit_card_payment_router)

app.include_router(household_report_router)
app.include_router(monthly_report_router)
app.include_router(daily_report_router)
app.include_router(yearly_report_router)
app.include_router(category_report_router)
app.include_router(account_report_router)
app.include_router(account_transaction_router)
app.include_router(account_overview_router)
app.include_router(g01_07_router)
app.include_router(bank_import_router)
app.include_router(reconciliation_router)
app.include_router(einvoice_router)


# --------------------------------------------------
# Web application
# --------------------------------------------------

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static",
)


@app.get("/")
def home():
    """Serve the responsive family finance web application."""
    return FileResponse("static/index.html")


@app.get("/app-config")
def app_config():
    """Return public frontend configuration only; never expose OAuth secrets."""
    return {
        "google_client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        # 採買明細等正式資料庫遷移完成後，再由 Render 環境變數開啟。
        "purchase_line_items_enabled": os.getenv(
            "PURCHASE_LINE_ITEMS_ENABLED", ""
        ).strip().lower() in {"1", "true", "yes", "on"},
    }


# --------------------------------------------------
# Health Check
# --------------------------------------------------

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "framework": "FastAPI",
    }


# --------------------------------------------------
# Database Health Check
# --------------------------------------------------

@app.get("/health/db")
def database_health_check():
    try:
        check_database_connection()

        return {
            "status": "ok",
            "database": "connected",
        }

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        )
