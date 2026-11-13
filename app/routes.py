from flask import Blueprint, render_template_string

main = Blueprint("main", __name__)


@main.route("/")
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="zh-Hant">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport"
              content="width=device-width, initial-scale=1.0">
        <title>家庭記帳系統</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background: #f5f7fa;
                margin: 0;
                padding: 40px 20px;
                color: #333;
            }
            .container {
                max-width: 700px;
                margin: 60px auto;
                background: white;
                padding: 35px;
                border-radius: 16px;
                text-align: center;
                box-shadow: 0 4px 18px rgba(0,0,0,.06);
            }
            h1 { color: #365b50; }
            .status {
                color: #16845b;
                font-weight: bold;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>家庭記帳系統</h1>
            <p>Family Finance</p>
            <p class="status">Flask 網站啟動成功！</p>
            <p>我們正在建立家庭財務管理平台。</p>
        </div>
    </body>
    </html>
    """)
