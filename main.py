
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.database import check_database_connection

from app.routers.auth import router as auth_router
from app.routers.family import router as family_router
from app.routers.account import router as account_router
from app.routers.category import router as category_router
from app.routers.transaction import router as transaction_router
from app.routers.transfer import router as transfer_router


app = FastAPI(
    title="家庭記帳系統",
    description="全家共用的家庭財務管理系統",
    version="1.0.0"
)


# =========================================================
# API 路由
# =========================================================

app.include_router(auth_router)
app.include_router(family_router)
app.include_router(account_router)
app.include_router(category_router)
app.include_router(transaction_router)
app.include_router(transfer_router)


# =========================================================
# 首頁
# =========================================================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>家庭記帳系統</title>
    </head>
    <body>
        <h1>家庭記帳系統</h1>
        <p>Family Finance</p>
        <p>FastAPI 網站啟動成功！</p>
    </body>
    </html>
    """


# =========================================================
# 系統健康檢查
# =========================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "framework": "FastAPI"
    }


# =========================================================
# 資料庫健康檢查
# =========================================================

@app.get("/health/db")
def database_health():
    try:
        check_database_connection()

        return {
            "status": "ok",
            "database": "connected"
        }

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed"
        )
