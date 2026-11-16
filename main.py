
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.database import check_database_connection

# --------------------------------------------------
# Routers
# --------------------------------------------------

from app.routers.auth import router as auth_router
from app.routers.family import router as family_router
from app.routers.account import router as account_router
from app.routers.category import router as category_router
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
app.include_router(account_router)
app.include_router(category_router)
app.include_router(transaction_router)
app.include_router(transfer_router)
app.include_router(credit_card_payment_router)
app.include_router(household_report_router)
app.include_router(monthly_report_router)
app.include_router(daily_report_router)
app.include_router(yearly_report_router)


# --------------------------------------------------
# Home
# --------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html lang="zh-Hant">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>家庭記帳系統</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background: #f5f6fa;
                margin: 0;
                padding: 40px 20px;
                text-align: center;
            }
            .container {
                max-width: 600px;
                margin: auto;
                background: white;
                padding: 30px;
                border-radius: 12px;
                box-shadow: 0 2px 12px rgba(0,0,0,0.08);
            }
            h1 {
                color: #263238;
            }
            p {
                color: #607d8b;
                line-height: 1.8;
            }
            a {
                display: inline-block;
                margin-top: 15px;
                padding: 12px 24px;
                background: #1976d2;
                color: white;
                text-decoration: none;
                border-radius: 6px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>家庭記帳系統</h1>
            <p>全家共用的家庭財務管理系統</p>
            <p>系統目前正常運作。</p>
            <a href="/docs">開啟 API 文件</a>
        </div>
    </body>
    </html>
    """


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
