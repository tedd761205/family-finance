# 附件物件儲存設定（G-01-06）

## 設計

附件檔案不存放在 Render Web Service 的本機磁碟，也不存進 Neon PostgreSQL。資料庫只保存家庭關聯、檔名、實際 MIME 類型、大小、SHA-256、物件鍵與稽核欄位；檔案本體放在私有 S3 相容物件儲存。

目前 API 支援 JPEG、PNG、WebP 單張圖片，原始上傳上限 10 MiB。伺服器會解碼並重新編碼圖片，去除 EXIF 等多餘中繼資料，再計算 SHA-256。動畫圖片、偽裝副檔名、損毀圖片及超出像素限制的圖片會被拒絕。

下載必須通過登入、家庭成員、附件權限及資料範圍檢查；API 驗證下載內容的 SHA-256。附件作廢只標記資料庫狀態，不會刪除物件。

## 建議的正式儲存服務

建議使用 Cloudflare R2 的私有 bucket（S3 相容）。不要啟用公開存取；所有檔案讀取都經由家庭記帳 API 的授權檢查。

在 Cloudflare 建立 R2 bucket 與只允許該 bucket 讀寫的 API Token 後，在 Render Web Service 的 Environment 加入：

| Environment variable | 值 |
|---|---|
| `ATTACHMENT_STORAGE_ENDPOINT_URL` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `ATTACHMENT_STORAGE_REGION` | `auto` |
| `ATTACHMENT_STORAGE_BUCKET` | 私有 bucket 名稱 |
| `ATTACHMENT_STORAGE_ACCESS_KEY_ID` | R2 Access Key ID |
| `ATTACHMENT_STORAGE_SECRET_ACCESS_KEY` | R2 Secret Access Key |

以上金鑰只應填入 Render Environment，不要提交到 GitHub、程式碼、Issue 或對話。端點必須使用 HTTPS。尚未設定儲存環境時，附件上傳及讀取 API 會回覆 503，不會退回 Render 本機磁碟。

## API

- `POST /attachments?family_id=<id>&bill_id=<id>`：上傳帳單圖片（multipart 欄位名稱 `file`）。
- `POST /attachments?family_id=<id>&transaction_id=<id>`：上傳交易圖片。
- `GET /attachments?family_id=<id>&bill_id=<id>`：列出帳單附件。
- `GET /attachments?family_id=<id>&transaction_id=<id>`：列出交易附件。
- `GET /attachments/<attachment_id>?family_id=<id>`：取得附件中繼資料。
- `GET /attachments/<attachment_id>/content?family_id=<id>`：授權後讀取圖片。
- `DELETE /attachments/<attachment_id>?family_id=<id>&reason=<reason>`：作廢附件，保留物件。

## 備份與保留

目前 Neon 備份只涵蓋資料庫，不會自動備份 R2 物件。正式啟用附件前，必須另外建立物件儲存備份／版本保留策略，並定期演練資料庫與物件的共同還原。不要只依賴資料庫備份。

## OCR

本階段先建立安全附件基礎。OCR 任務佇列、辨識供應商、人工校正及帳單欄位確認會在後續 G-01-06 OCR 子階段實作；目前不會假裝已辨識圖片或自動建立帳單。
