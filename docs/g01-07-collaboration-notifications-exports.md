# G-01-07 家庭協作、通知與匯出

## 功能範圍

- 家庭內通知：只允許有效家庭成員讀取自己的通知；已讀時間及讀取操作寫入 audit_logs。
- 共用匯出範本：draft / published / disabled；每次更新建立不可覆寫的版本快照。
- 版本衝突：更新及發布必須傳入 expected_version；版本過期回傳 HTTP 409 與最新版本摘要。手動合併時，先檢視最新版本，再以最新 expected_version 提交合併後的完整設定。
- 排程：daily / weekly / monthly，固定使用 Asia/Taipei；資料庫 next_run_at 以 UTC 儲存。
- 匯出檔案：目前支援 transactions 與 bills CSV，檔案放在私有物件儲存，保存 SHA-256、大小及範本版本快照。
- 權限：每次排程執行重新檢查建立者的有效家庭成員狀態、exports.schedule、exports.create、資料檢視權限及 own/family 範圍；下載時重新驗證下載權限與資料範圍。
- 管理統計：exports.dashboard 獨立授權，可依台灣日期區間與狀態篩選，輸出每日趨勢與失敗警示。
- 家庭隔離：所有範本、排程、執行紀錄均以 family_id 限定；跨家庭關聯由複合外鍵保護。

## API

- GET /notifications?family_id=...
- POST /notifications/{notification_id}/read?family_id=...
- GET /exports/templates?family_id=...
- POST /exports/templates?family_id=...
- PUT /exports/templates/{template_id}?family_id=...（body 必須含 expected_version）
- POST /exports/templates/{template_id}/publish?family_id=...&expected_version=...
- POST /exports/templates/{template_id}/disable?family_id=...&expected_version=...
- GET /exports/templates/{template_id}/versions?family_id=...
- POST /exports/schedules?family_id=...
- GET /exports/schedules?family_id=...
- POST /exports/schedules/{schedule_id}/disable?family_id=...
- POST /exports/templates/{template_id}/run?family_id=...
- GET /exports/runs?family_id=...
- GET /exports/runs/{run_id}/download?family_id=...
- GET /exports/dashboard?family_id=...&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&status=...

## 範本 config 範例

```json
{
  "dataset": "transactions",
  "columns": ["id", "occurred_on", "type", "amount", "currency_code", "description"]
}
```

允許 dataset：transactions、bills。欄位必須是 API schema 中的白名單；不接受任意 SQL、任意欄位或前端提供查詢片段。

## 定期匯出 worker

已提供執行入口：

```bash
python -m scripts.run_scheduled_exports
```

worker 每次最多處理 25 筆到期排程，使用資料庫列鎖避免多個 worker 重複領取。啟用週期觸發器屬 G-01-08 部署整合工作；目前尚未修改 Render 服務、建立付費排程服務或執行正式 Neon migration。

## 安全與部署界線

- migration 只在 GitHub Actions 的隔離 PostgreSQL 18 測試資料庫驗證。
- 不會自動執行正式 Neon migration。
- 不會變更 Render 環境變數。
- 匯出檔案存於私有 Neon Object Storage；下載時透過 API 驗證權限，不公開 bucket。
