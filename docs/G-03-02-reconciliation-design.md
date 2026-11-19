# G-03-02 銀行／信用卡對帳工作區設計

狀態：設計基線（供後續 G-03-02 API、Migration、UI 與測試實作依據）  
基準主線：`66204cbb0cecc2ba9ba315881a532ce3af723d76`（G-03-01）

## 1. 目標與邊界

G-03-01 負責將 CSV 保存為銀行／信用卡原始對帳明細。人工確認時預設只確認匯入明細、不建立正式交易；只有使用者明確選擇時才同步建立交易。疑似重複明細仍保留在對帳來源中。G-03-02 負責將銀行／信用卡對帳單資料與家庭既有正式交易核對，並保存核對關係、差異與稽核軌跡。

本階段不負責：
- 不直接修改或刪除銀行匯入原始資料。
- 不因為配對而新增、修改、作廢正式交易。
- 不自動建立「補帳」交易；未登記交易只列為待處理，後續另由使用者透過正式交易流程建立。
- 不將信用卡消費明細與信用卡繳款混為同一筆；依帳戶與實際對帳單來源分別核對。

## 2. 核心資料關係

### 2.1 reconciliation_sessions（對帳批次／期間）

每個家庭、帳戶、對帳期間建立一個對帳工作階段。建議欄位：
- id、family_id、account_id
- period_start、period_end（以帳戶所在地日期語意解讀）
- status：draft、in_progress、completed、cancelled
- source_batch_id（可空；關聯 G-03-01 匯入批次）
- opening_balance、closing_balance（可空；只有來源提供時才填）
- statement_row_count、matched_row_count、difference_row_count
- created_by、created_at、completed_by、completed_at、updated_at

同一家庭、同一帳戶、相同期間不得存在多筆未取消工作階段。已完成工作階段不可直接編輯；如需更正，建立明確的重新開啟／更正流程並留下稽核紀錄。

### 2.2 reconciliation_matches（銀行列與帳務交易配對明細）

配對表採「一筆銀行對帳列可配對多筆正式交易」設計，支援拆分入帳。建議欄位：
- id、family_id、session_id、batch_id、bank_import_row_id、transaction_id
- allocated_amount（Numeric(20,4)，必須大於 0）
- status：active、voided
- matched_by、matched_at、voided_by、voided_at、void_reason

必要約束：
- 所有關聯均以 family_id 複合外鍵隔離家庭資料。
- 同一正式交易最多只能有一筆有效配對，避免一筆帳務交易被重複核銷。
- 同一銀行列與正式交易不可重複建立有效配對。
- 同一對帳工作階段不得重複納入同一銀行列。
- allocated_amount 不可超過銀行列剩餘未配對金額。
- 銀行列與交易必須屬於相同家庭、相同帳戶、相同幣別及相同收支方向。
- 配對金額總和不可超過來源銀行列金額；完成核對時必須精確相等。
- 已作廢交易不可配對；已匯入來源列必須屬於該對帳批次。

資料庫負責可表達的唯一性、外鍵與正數約束；跨多筆合計及狀態轉移由交易鎖定與服務層在同一資料庫交易中驗證。

## 3. 核對狀態與差異

銀行列核對狀態由有效配對總額推導，不以使用者任意輸入狀態作為唯一依據：
- unmatched：尚無有效配對。
- partially_matched：有效配對總額大於 0 但小於銀行列金額。
- matched：有效配對總額精確等於銀行列金額。
- excluded：經具備權限者排除，必須填理由；排除不會刪除原始資料。

差異類型至少包含：
- bank_only：銀行有、帳務沒有。
- ledger_only：帳務有、銀行沒有。
- amount_mismatch：金額不一致或部分配對。
- date_mismatch：日期落差，保留提示但不自動改日期。
- duplicate_suspected：疑似重複，需人工判斷。
- excluded_with_reason：經人工排除並記錄原因。

「日期差異」與「金額差異」屬提示／例外，不應在不符合帳戶、幣別、方向及金額規則時強行配對。

## 4. 自動比對建議

自動比對只產生候選建議，不自動建立有效配對。候選分數與理由應可解釋：
1. 銀行外部參考號與交易 external_reference 完全一致。
2. 帳戶、幣別、方向及金額一致。
3. 日期相同或在可設定的小範圍內。
4. 摘要正規化後相似，僅作輔助，不可單獨確認。

候選結果需標示「高／中／低信心」與命中條件。多筆同分或疑似重複時，維持待人工確認。

## 5. API 建議

路由前綴：`/reconciliations`

第一版端點：
- `POST /sessions`：建立對帳期間。
- `GET /sessions`：查詢家庭對帳工作階段（分頁、帳戶、期間、狀態）。
- `GET /sessions/{session_id}`：摘要、銀行列狀態與差異。
- `POST /sessions/{session_id}/suggestions`：產生候選配對（唯讀計算，不寫入配對）。
- `POST /sessions/{session_id}/matches`：人工建立一筆配對；可多次呼叫完成拆分。
- `DELETE /sessions/{session_id}/matches/{match_id}`：作廢配對，需理由，不刪除歷史。
- `POST /sessions/{session_id}/exclude`：排除銀行列，需理由。
- `POST /sessions/{session_id}/complete`：檢查所有銀行列均已 matched 或 excluded，再完成對帳。
- `POST /sessions/{session_id}/reopen`：受限更正流程；需權限、理由與完整稽核。

每個端點都必須驗證家庭成員資格、功能權限、資料範圍（own/family）、帳戶歸屬與工作階段狀態。跨家庭 ID 一律回傳不洩漏存在性的 404。

## 6. 權限與稽核

沿用既有權限目錄及角色資料範圍，新增權限代碼：
- reconciliation.view
- reconciliation.create
- reconciliation.match
- reconciliation.unmatch
- reconciliation.exclude
- reconciliation.close
- reconciliation.reopen

資料範圍以 reconciliation 資源或明確映射至 accounts／transactions 的 own/family 規則實作，不可只檢查 imports 權限。配對建立、解除、排除、完成及重新開啟均寫入 audit_logs，保存操作者、時間、對象、舊值／新值及原因。

## 7. 併發與交易安全

- 配對與解除配對時，對 session、bank_import_row 及涉及 transaction 使用一致順序的資料列鎖定。
- 同一資料庫交易內重新計算已分配總額、驗證剩餘金額、寫入配對及稽核紀錄。
- 唯一索引作為防止交易重複配對的最後防線；IntegrityError 必須 rollback 並轉成可理解的 409。
- 完成對帳時鎖定 session，重新驗證每筆銀行列狀態後才標記 completed。
- completed session 不接受一般配對變更；reopen 必須經明確權限與理由。
- 所有金額使用 Decimal／Numeric(20,4)，禁止浮點數運算。

## 8. 前端工作區

新增「銀行對帳」工作區：
- 帳戶與對帳期間選擇、批次建立。
- KPI：銀行列總數、已核對、部分核對、待核對、差異、排除。
- 左側銀行明細、右側家庭帳務候選交易；手機版改為上下堆疊。
- 支援搜尋、日期範圍、金額、方向、狀態篩選。
- 顯示配對金額、剩餘金額、候選原因與差異提示。
- 一筆銀行列可逐筆選取多筆交易，直到分配總額等於銀行金額。
- 完成前顯示未核對／排除清單與確認摘要。

## 9. 測試驗收標準

### 模型與 Migration
- family/account/session/import row/transaction 複合外鍵有效。
- 同一 transaction 不可同時配對兩筆銀行列。
- 同一銀行列不可重複配對相同 transaction。
- downgrade 只移除本次新增物件，不動既有交易及匯入資料。

### API 與安全
- 跨家庭讀取、建立、配對、解除、排除、完成均拒絕。
- 無權限、own/family 範圍、停用帳戶、作廢交易、已完成 session 均有測試。
- 金額超額、幣別不符、帳戶不符、方向不符、重複配對均拒絕。
- 多筆交易拆分配對可成功；分配總額未相等不可完成。
- 配對／解除／排除／完成均產生稽核紀錄。
- 併發配對不得超額或重複配對。

### Web
- 導覽、權限顯示、列表、篩選、配對、解除、排除、完成及手機版 smoke tests。
- 不具權限時不顯示操作入口，API 仍須獨立驗權。

## 10. 實作切分

- G-03-02-01：資料模型、Migration、權限目錄與模型測試。
- G-03-02-02：對帳 Session API、資料範圍及稽核測試。
- G-03-02-03：人工配對／解除／排除 API 與併發測試。
- G-03-02-04：候選比對建議與可解釋分數。
- G-03-02-05：完成／重新開啟流程及稽核。
- G-03-02-06：響應式對帳工作區與端對端測試。

第一版以人工核對與資料完整性為優先，自動比對僅提供建議，避免錯誤配對影響家庭帳務。
