# Cloudflare R2 私有附件儲存設定

本專案的附件本體存放在 S3 相容物件儲存，Render 只保存附件中繼資料與資料庫連線，不將圖片寫入 Render 本機磁碟。

## 1. 建立 R2 Bucket

1. 登入 Cloudflare Dashboard。
2. 開啟 **Storage & databases → R2 object storage**。
3. 建立專用 Bucket，例如 `family-finance-private`。
4. Bucket 建立後，進入 Bucket 的 Settings。
5. 確認沒有啟用 Public Development URL（`r2.dev`），也不要綁定公開網域。
6. 不要設定公開讀取權限或公開 Bucket policy。

R2 Bucket 預設不公開；家庭帳單照片包含個人財務資料，必須維持私有。應用程式透過後端 S3 API 讀寫，使用者只能經過登入、家庭權限與附件權限檢查後讀取。

## 2. 建立最小權限 API Token

1. 在 Cloudflare R2 Overview 開啟 **Manage R2 API Tokens**。
2. 建立專用 Token。
3. 權限選 **Object Read & Write**。
4. 資源範圍選 **Apply to specific buckets only**，只勾選剛建立的家庭記帳 Bucket。
5. 建立後立即安全保存 Access Key ID 與 Secret Access Key。

不要使用 Cloudflare Global API Key，也不要建立可存取所有 Bucket 的 Token。Secret Access Key 通常只在建立時顯示一次。

## 3. Render 環境變數

在 Render 的 Family Finance Web Service → Environment，新增下列變數：

| Key | Value |
|---|---|
| `ATTACHMENT_STORAGE_ENDPOINT_URL` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `ATTACHMENT_STORAGE_REGION` | `auto` |
| `ATTACHMENT_STORAGE_BUCKET` | 建立的 Bucket 名稱 |
| `ATTACHMENT_STORAGE_ACCESS_KEY_ID` | R2 Access Key ID |
| `ATTACHMENT_STORAGE_SECRET_ACCESS_KEY` | R2 Secret Access Key |

`<ACCOUNT_ID>` 要替換為 Cloudflare 帳戶 ID。Endpoint 必須是 HTTPS API 根網址，不可加 Bucket 名稱、路徑、Query string 或公開網域。

請直接在 Render Environment 輸入 Secret；不要貼到 ChatGPT、GitHub 程式碼、GitHub Actions log、Issue 或 PR。

## 4. 驗證儲存連線

部署包含 `scripts/check_attachment_storage.py` 的版本後，可在 Render Shell 執行：

```bash
python scripts/check_attachment_storage.py
```

此檢查會在 Bucket 的 `system-checks/` 前綴建立一個隨機測試物件、下載並驗證 SHA-256，最後刪除測試物件。成功時顯示：

```
Private attachment storage connection check passed.
```

如果檢查失敗，先確認 Endpoint、Bucket 名稱、Token 是否只授權該 Bucket 且具有 Object Read & Write 權限。不要將錯誤 log 中可能含有的請求資訊或憑證貼到公開位置。

## 5. 正式啟用前檢查

- [ ] R2 Bucket 保持 Private，沒有啟用 `r2.dev` 或公開網域。
- [ ] API Token 只授權家庭記帳專用 Bucket。
- [ ] Render 五個 `ATTACHMENT_STORAGE_*` 變數均已設定。
- [ ] Render Shell 儲存連線測試成功。
- [ ] 使用正式附件 API 上傳一張測試圖片。
- [ ] 透過登入後的附件內容 API 下載，確認 SHA-256 一致。
- [ ] 由未授權家庭成員測試，確認不能讀取其他家庭附件。

## 6. 資料庫與 OCR

這份設定文件及程式變更不會自動執行 Neon Migration，也不會自動設定 Google Cloud Vision。正式啟用附件 API 前，仍須先完成 G-01-06 Migration 與 R2 設定檢查；OCR 則另需設定 `GOOGLE_CLOUD_VISION_API_KEY`。

## 官方文件

- [Cloudflare R2 S3 API 與建立憑證](https://developers.cloudflare.com/r2/get-started/s3/)
- [Cloudflare R2 boto3 範例](https://developers.cloudflare.com/r2/examples/aws/boto3/)
- [Cloudflare R2 公開 Bucket 設定與停用方式](https://developers.cloudflare.com/r2/buckets/public-buckets/)
