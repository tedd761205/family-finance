# G-03-03-03 對帳差異處理

## 分類
- bank_only：銀行明細獨有
- ledger_only：帳務交易獨有
- amount_mismatch：金額不一致（必須連結銀行明細及正式交易）
- date_mismatch：日期不一致（必須連結銀行明細及正式交易）
- pending：待確認
- explained：已說明但仍保留為差異紀錄

## 狀態與歷史
- open：待處理
- resolved：已結案，必須填寫處理說明
- 建立及結案操作寫入既有 audit_logs，保留操作者、時間、舊值與新值。
- 差異紀錄不會刪除；來源銀行明細與正式交易均採關聯，不複製或改寫來源資料。
- 只允許進行中的對帳工作階段新增或結案差異。
- 金額／日期差異必須同時連結銀行明細及正式交易；銀行獨有與帳務獨有分別要求對應來源。
- 帳務交易差異需 family 層級交易資料範圍，避免只用個人資料判斷全帳戶。
- 不會因差異分類或結案自動建立、修改、作廢正式交易。

## API
- GET /reconciliations/sessions/{session_id}/issues
- POST /reconciliations/sessions/{session_id}/issues
- POST /reconciliations/sessions/{session_id}/issues/{issue_id}/resolve

Migration：a6b8c0d2e4f6（僅隨 PR 提交；未套用至 Neon production）。
