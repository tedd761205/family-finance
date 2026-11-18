
"""
家庭記帳系統：系統功能權限清單

此檔案定義全系統共用的功能權限。
permissions 資料表保存權限定義；
role_permissions 負責角色與功能權限的對應。
"""

PERMISSION_CATALOG = [
    # 儀表板
    {
        "code": "dashboard.view",
        "name": "查看儀表板",
        "description": "查看家庭財務總覽及儀表板資訊",
        "category": "dashboard",
    },

    # 帳務紀錄
    {
        "code": "transactions.view",
        "name": "查看帳務",
        "description": "查看收入、支出及轉帳紀錄",
        "category": "transactions",
    },
    {
        "code": "transactions.create",
        "name": "新增帳務",
        "description": "新增收入、支出及帳務紀錄",
        "category": "transactions",
    },
    {
        "code": "transactions.update",
        "name": "修改帳務",
        "description": "修改既有帳務紀錄",
        "category": "transactions",
    },
    {
        "code": "transactions.void",
        "name": "作廢帳務",
        "description": "作廢帳務紀錄並保留歷史資料",
        "category": "transactions",
    },

    # 帳戶管理
    {
        "code": "accounts.view",
        "name": "查看帳戶",
        "description": "查看銀行、現金及信用卡帳戶",
        "category": "accounts",
    },
    {
        "code": "accounts.create",
        "name": "新增帳戶",
        "description": "建立銀行、現金及信用卡帳戶",
        "category": "accounts",
    },
    {
        "code": "accounts.update",
        "name": "修改帳戶",
        "description": "修改帳戶資料及設定",
        "category": "accounts",
    },
    {
        "code": "accounts.void",
        "name": "停用帳戶",
        "description": "停用不再使用的帳戶並保留歷史紀錄",
        "category": "accounts",
    },
    {
        "code": "accounts.transfer",
        "name": "帳戶轉帳",
        "description": "執行家庭內帳戶間的資金轉移",
        "category": "accounts",
    },

    # 分類管理
    {
        "code": "categories.view",
        "name": "查看分類",
        "description": "查看收入及支出分類",
        "category": "categories",
    },
    {
        "code": "categories.create",
        "name": "新增分類",
        "description": "新增收入及支出分類",
        "category": "categories",
    },
    {
        "code": "categories.update",
        "name": "修改分類",
        "description": "修改分類名稱及設定",
        "category": "categories",
    },
    {
        "code": "categories.void",
        "name": "停用分類",
        "description": "停用分類並保留既有帳務關聯",
        "category": "categories",
    },

    # 帳單管理
    {
        "code": "bills.view",
        "name": "查看帳單",
        "description": "查看家庭帳單及應繳義務",
        "category": "bills",
    },
    {
        "code": "bills.create",
        "name": "新增帳單",
        "description": "建立家庭帳單",
        "category": "bills",
    },
    {
        "code": "bills.update",
        "name": "修改帳單",
        "description": "修改尚未作廢的帳單",
        "category": "bills",
    },
    {
        "code": "bills.void",
        "name": "作廢帳單",
        "description": "作廢帳單並保留歷史紀錄",
        "category": "bills",
    },

    # 定期帳單
    {
        "code": "recurring_bills.view",
        "name": "查看定期帳單",
        "description": "查看固定週期的帳單及提醒",
        "category": "recurring_bills",
    },
    {
        "code": "recurring_bills.create",
        "name": "新增定期帳單",
        "description": "建立定期帳單及繳費週期",
        "category": "recurring_bills",
    },
    {
        "code": "recurring_bills.update",
        "name": "修改定期帳單",
        "description": "修改定期帳單內容及週期",
        "category": "recurring_bills",
    },
    {
        "code": "recurring_bills.void",
        "name": "停用定期帳單",
        "description": "停止定期帳單並保留歷史紀錄",
        "category": "recurring_bills",
    },

    # 付款管理
    {
        "code": "payments.view",
        "name": "查看付款",
        "description": "查看帳單付款及繳費紀錄",
        "category": "payments",
    },
    {
        "code": "payments.create",
        "name": "新增付款",
        "description": "新增帳單付款及繳費紀錄",
        "category": "payments",
    },
    {
        "code": "payments.update",
        "name": "修改付款",
        "description": "修改付款資料",
        "category": "payments",
    },
    {
        "code": "payments.void",
        "name": "作廢付款",
        "description": "作廢付款紀錄並保留歷史資料",
        "category": "payments",
    },

    # 對帳管理
    {
        "code": "reconciliation.view",
        "name": "查看對帳",
        "description": "查看帳戶對帳及差異紀錄",
        "category": "reconciliation",
    },
    {
        "code": "reconciliation.create",
        "name": "建立對帳",
        "description": "建立新的對帳作業",
        "category": "reconciliation",
    },
    {
        "code": "reconciliation.match",
        "name": "執行配對",
        "description": "將帳務與銀行或信用卡明細配對",
        "category": "reconciliation",
    },
    {
        "code": "reconciliation.unmatch",
        "name": "取消配對",
        "description": "取消既有對帳配對",
        "category": "reconciliation",
    },
    {
        "code": "reconciliation.close",
        "name": "完成對帳",
        "description": "確認並完成對帳作業",
        "category": "reconciliation",
    },

    # 報表分析
    {
        "code": "reports.view",
        "name": "查看報表",
        "description": "查看家庭收入、支出及財務報表",
        "category": "reports",
    },
    {
        "code": "reports.export",
        "name": "匯出報表",
        "description": "匯出家庭財務報表及統計資料",
        "category": "reports",
    },

    # 資料匯入
    {
        "code": "imports.view",
        "name": "查看匯入紀錄",
        "description": "查看銀行及信用卡資料匯入紀錄",
        "category": "imports",
    },
    {
        "code": "imports.create",
        "name": "匯入資料",
        "description": "上傳銀行或信用卡 CSV、Excel 資料",
        "category": "imports",
    },
    {
        "code": "imports.confirm",
        "name": "確認匯入",
        "description": "確認匯入資料並正式建立帳務",
        "category": "imports",
    },
    {
        "code": "imports.void",
        "name": "作廢匯入",
        "description": "作廢尚未正式入帳或可撤銷的匯入批次",
        "category": "imports",
    },

    # 附件管理
    {
        "code": "attachments.view",
        "name": "查看附件",
        "description": "查看帳單照片及相關附件",
        "category": "attachments",
    },
    {
        "code": "attachments.upload",
        "name": "上傳附件",
        "description": "上傳帳單照片及其他財務附件",
        "category": "attachments",
    },
    {
        "code": "attachments.void",
        "name": "停用附件",
        "description": "停用附件並保留必要的操作紀錄",
        "category": "attachments",
    },

    # OCR 辨識
    {
        "code": "ocr.view",
        "name": "查看 OCR 辨識",
        "description": "查看帳單圖片文字辨識結果",
        "category": "ocr",
    },
    {
        "code": "ocr.create",
        "name": "建立 OCR 辨識",
        "description": "建立並執行帳單圖片文字辨識",
        "category": "ocr",
    },
    {
        "code": "ocr.retry",
        "name": "重試 OCR 辨識",
        "description": "重試失敗的文字辨識工作",
        "category": "ocr",
    },
    {
        "code": "ocr.confirm",
        "name": "確認 OCR 結果",
        "description": "人工確認 OCR 擷取結果",
        "category": "ocr",
    },

    # 家庭設定
    {
        "code": "family.view",
        "name": "查看家庭設定",
        "description": "查看家庭基本資料及設定",
        "category": "family",
    },
    {
        "code": "family.update",
        "name": "修改家庭設定",
        "description": "修改家庭名稱及基本設定",
        "category": "family",
    },

    # 家庭成員管理
    {
        "code": "members.view",
        "name": "查看家庭成員",
        "description": "查看家庭成員及其狀態",
        "category": "members",
    },
    {
        "code": "members.invite",
        "name": "邀請家庭成員",
        "description": "邀請新成員加入家庭",
        "category": "members",
    },
    {
        "code": "members.update",
        "name": "修改成員資料",
        "description": "修改家庭成員相關設定",
        "category": "members",
    },
    {
        "code": "members.remove",
        "name": "移除家庭成員",
        "description": "停用成員的家庭參與資格並保留歷史紀錄",
        "category": "members",
    },

    # 角色及權限管理
    {
        "code": "roles.view",
        "name": "查看角色",
        "description": "查看家庭角色及其權限設定",
        "category": "roles",
    },
    {
        "code": "roles.create",
        "name": "新增角色",
        "description": "建立家庭自訂角色",
        "category": "roles",
    },
    {
        "code": "roles.update",
        "name": "修改角色",
        "description": "修改自訂角色及其權限",
        "category": "roles",
    },
    {
        "code": "roles.void",
        "name": "停用角色",
        "description": "停用不再使用的自訂角色",
        "category": "roles",
    },
    {
        "code": "roles.assign",
        "name": "指派角色",
        "description": "將角色指派給家庭成員",
        "category": "roles",
    },

    # 操作紀錄
    {
        "code": "audit_logs.view",
        "name": "查看操作紀錄",
        "description": "查看家庭成員的操作及異動紀錄",
        "category": "audit_logs",
    },
    {
        "code": "audit_logs.export",
        "name": "匯出操作紀錄",
        "description": "匯出家庭操作紀錄",
        "category": "audit_logs",
    },

    # 備份管理
    {
        "code": "backups.view",
        "name": "查看備份",
        "description": "查看資料庫及附件備份紀錄",
        "category": "backups",
    },
    {
        "code": "backups.create",
        "name": "建立備份",
        "description": "建立家庭資料備份",
        "category": "backups",
    },
    {
        "code": "backups.download",
        "name": "下載備份",
        "description": "下載已建立的備份檔案",
        "category": "backups",
    },
    {
        "code": "backups.restore",
        "name": "還原備份",
        "description": "還原家庭資料及相關備份",
        "category": "backups",
    },

    # 匯率管理
    {
        "code": "exchange_rates.view",
        "name": "查看匯率",
        "description": "查看外幣及匯率資料",
        "category": "exchange_rates",
    },
    {
        "code": "exchange_rates.update",
        "name": "修改匯率",
        "description": "更新外幣匯率資料",
        "category": "exchange_rates",
    },
    # 家庭協作、通知與匯出
    {"code": "notifications.view", "name": "查看通知", "description": "查看本人收到的家庭通知", "category": "notifications"},
    {"code": "notifications.manage", "name": "管理通知", "description": "管理家庭通知及通知狀態", "category": "notifications"},
    {"code": "exports.view", "name": "查看匯出範本與紀錄", "description": "查看家庭匯出範本、排程及匯出紀錄", "category": "exports"},
    {"code": "exports.create", "name": "建立匯出範本", "description": "建立家庭共用匯出範本", "category": "exports"},
    {"code": "exports.update", "name": "修改匯出範本", "description": "修改草稿匯出範本及手動合併版本", "category": "exports"},
    {"code": "exports.publish", "name": "發布匯出範本", "description": "發布及停用家庭共用匯出範本", "category": "exports"},
    {"code": "exports.schedule", "name": "管理定期匯出", "description": "建立、修改及停用定期匯出排程", "category": "exports"},
    {"code": "exports.download", "name": "下載匯出檔案", "description": "下載本人資料範圍內且仍有權限的匯出檔案", "category": "exports"},
    {"code": "exports.dashboard", "name": "查看匯出管理統計", "description": "查看家庭匯出執行統計及管理追蹤", "category": "exports"},
]
