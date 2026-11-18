# OCR 任務設定與使用

## 功能範圍

OCR 使用 Google Cloud Vision 的文件文字辨識功能。系統將結果保存為待人工核對的建議，不會自動新增或修改帳單、付款、交易或帳戶餘額。

## Render 環境變數

設定下列環境變數後，OCR 才能實際呼叫辨識服務：

- `GOOGLE_CLOUD_VISION_API_KEY`：Google Cloud Vision API Key。

請在 Google Cloud 專案啟用 Cloud Vision API，限制 API Key 僅能呼叫 Cloud Vision API，並設定合理的配額與帳單預算。API Key 只能放在 Render Environment，不可提交到 GitHub、前端或資料庫。

附件物件儲存仍需另外完成 R2/S3 私有 Bucket 設定。OCR 會從私有物件儲存讀取附件，不會使用公開 URL。

## API 流程

1. 先使用附件 API 上傳 JPEG、PNG 或 WebP 圖片。
2. `POST /ocr/tasks?family_id={family_id}&attachment_id={attachment_id}` 建立任務。
3. `POST /ocr/tasks/{task_id}/process?family_id={family_id}` 執行辨識。
4. `GET /ocr/tasks/{task_id}?family_id={family_id}` 讀取辨識結果。
5. 人工核對後，才呼叫 `POST /ocr/tasks/{task_id}/confirm?family_id={family_id}` 確認結果。

失敗任務可使用 `POST /ocr/tasks/{task_id}/retry?family_id={family_id}` 重新排入佇列；最多執行五次。

## 狀態

- `queued`：等待執行。
- `processing`：正在呼叫 OCR 服務。
- `succeeded`：已取得文字與欄位候選值。
- `failed`：辨識失敗，可在次數限制內重試。
- `confirmed`：使用者已人工確認辨識結果。

## 安全與帳務原則

- OCR 只讀取已通過附件完整性檢查的圖片。
- 依 OCR、附件及帳單/交易各自的權限與資料範圍進行檢查。
- OCR 文字及候選欄位視為不可信輸入。
- 確認 OCR 只代表人工核對完成，不會自動建立或更新帳單；帳單建立仍需透過既有帳單 API 明確提交。
- 不記錄 API Key，也不將供應商回應原文直接寫入錯誤訊息。
