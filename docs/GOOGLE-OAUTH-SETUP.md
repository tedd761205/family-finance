# Google 登入設定

本專案使用 Google Identity Services 的 Sign in with Google 按鈕。後端會驗證 Google ID Token 的簽章、有效期限、issuer、audience 與已驗證 Email；前端只會取得公開的 OAuth Web Client ID，Google Client Secret 不需要放進 Render。

## Google Cloud Console

1. 在 Google Cloud Console 建立或選取專案。
2. 設定 OAuth consent screen，填寫應用程式名稱與聯絡資訊。
3. 建立 OAuth Client ID，應用程式類型選 **Web application**。
4. 在 Authorized JavaScript origins 加入正式網站來源：
   - `https://family-finance-web-grst.onrender.com`
5. 建立後複製 Client ID（結尾通常為 `.apps.googleusercontent.com`）。

此實作使用 Google Identity Services 的 ID token callback，不使用傳統 redirect callback，因此不需要為此按鈕設定 Authorized redirect URIs。

## Render

在 Render 的 Family Finance Web Service → Environment 新增：

- Key：`GOOGLE_CLIENT_ID`
- Value：Google Cloud Console 產生的 Web Client ID

儲存後等待 Render 部署完成，再開啟網站。登入頁會在設定存在時顯示 Google 登入按鈕。

## 帳號連結安全規則

- Google 身分以 Google 提供的 `sub` 作為唯一識別。
- Email 相同不代表自動合併帳號。
- 已有 Email／密碼帳號的使用者，必須先登入既有帳號，再呼叫已登入狀態下的 Google 綁定流程。
- 不要把 OAuth Client Secret、資料庫連線字串或 JWT secret 放到前端或提交到 Git。
