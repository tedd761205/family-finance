
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.database import check_database_connection

app = FastAPI(
    title="家庭記帳系統",
    description="全家共用的家庭財務管理系統",
    version="1.0.0"
)


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


@app.get("/health")
def health():
    return {
        "status": "ok",
        "framework": "FastAPI"
    }


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
