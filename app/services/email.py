
"""
家庭記帳系統：Email 寄送服務

負責：
1. 檢查 SMTP 設定
2. 建立密碼重設連結
3. 寄送密碼重設 Email

安全原則：
- SMTP 帳號密碼使用環境變數。
- 不在日誌記錄原始重設 Token。
- 不在 API 回應中暴露重設連結。
"""

import os
import smtplib

from email.message import EmailMessage
from urllib.parse import urlencode


def get_smtp_settings() -> dict:
    """讀取 SMTP 環境變數。"""

    host = os.getenv("SMTP_HOST")
    port = os.getenv("SMTP_PORT")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("SMTP_FROM_EMAIL")
    reset_url = os.getenv("PASSWORD_RESET_URL")

    if not all([
        host,
        port,
        username,
        password,
        from_email,
        reset_url,
    ]):
        raise RuntimeError("Email 寄送服務尚未完成設定")

    try:
        port_number = int(port)
    except (TypeError, ValueError):
        raise RuntimeError("SMTP_PORT 設定錯誤")

    if not 1 <= port_number <= 65535:
        raise RuntimeError("SMTP_PORT 超出有效範圍")

    return {
        "host": host,
        "port": port_number,
        "username": username,
        "password": password,
        "from_email": from_email,
        "reset_url": reset_url,
        "use_ssl": os.getenv("SMTP_USE_SSL", "false").lower()
        == "true",
    }


def send_password_reset_email(
    to_email: str,
    raw_token: str,
) -> None:
    """
    寄送密碼重設 Email。

    raw_token 僅用於組成重設連結，
    不會儲存或寫入日誌。
    """

    settings = get_smtp_settings()

    query = urlencode({
        "token": raw_token,
    })

    separator = (
        "&" if "?" in settings["reset_url"] else "?"
    )

    reset_link = (
        f"{settings['reset_url']}{separator}{query}"
    )

    message = EmailMessage()

    message["Subject"] = "家庭記帳系統－密碼重設"
    message["From"] = settings["from_email"]
    message["To"] = to_email

    message.set_content(
        f"""您好：

我們收到您的密碼重設申請。

請點選以下連結設定新密碼：

{reset_link}

此連結有效期限為 30 分鐘，且只能使用一次。

如果您沒有提出此申請，請忽略這封郵件。

家庭記帳系統
"""
    )

    if settings["use_ssl"]:
        with smtplib.SMTP_SSL(
            settings["host"],
            settings["port"],
            timeout=15,
        ) as server:
            server.login(
                settings["username"],
                settings["password"],
            )
            server.send_message(message)

    else:
        with smtplib.SMTP(
            settings["host"],
            settings["port"],
            timeout=15,
        ) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()

            server.login(
                settings["username"],
                settings["password"],
            )
            server.send_message(message)
