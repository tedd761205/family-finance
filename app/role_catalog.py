
"""
家庭記帳系統：預設角色及權限配置

每個家庭建立時，會依照此清單初始化自己的角色。
角色與權限分開管理，資料範圍則使用 role_data_scopes。
"""

from app.permission_catalog import PERMISSION_CATALOG


# 家庭管理員：擁有全部系統權限
ADMIN_PERMISSIONS = [
    item["code"]
    for item in PERMISSION_CATALOG
]


# 財務管理員：負責家庭財務及帳務管理
FINANCE_PERMISSIONS = [
    "dashboard.view",

    "transactions.view",
    "transactions.create",
    "transactions.update",
    "transactions.void",

    "accounts.view",
    "accounts.create",
    "accounts.update",
    "accounts.void",
    "accounts.transfer",

    "categories.view",
    "categories.create",
    "categories.update",
    "categories.void",

    "recurring_bills.view",
    "bills.view",
    "recurring_bills.create",
    "bills.create",
    "recurring_bills.update",
    "bills.update",
    "recurring_bills.void",
    "bills.void",

    "payments.view",
    "payments.create",
    "payments.update",
    "payments.void",

    "reconciliation.view",
    "reconciliation.create",
    "reconciliation.match",
    "reconciliation.unmatch",
    "reconciliation.close",

    "reports.view",
    "reports.export",
    "notifications.view",
    "exports.view", "exports.create", "exports.update", "exports.publish",
    "exports.schedule", "exports.download", "exports.dashboard",
    "notifications.view",
    "exports.view", "exports.create", "exports.update", "exports.publish",
    "exports.schedule", "exports.download", "exports.dashboard",

    "imports.view",
    "imports.create",
    "imports.confirm",
    "imports.void",

    "attachments.view",
    "attachments.upload",
    "attachments.void",

    "ocr.view",
    "ocr.create",
    "ocr.retry",
    "ocr.confirm",

    "family.view",
    "audit_logs.view",
    "audit_logs.export",
    "notifications.view", "notifications.manage",
    "exports.view", "exports.create", "exports.update", "exports.publish",
    "exports.schedule", "exports.download", "exports.dashboard",
    "notifications.view",
    "notifications.manage",
    "exports.view", "exports.create", "exports.update", "exports.publish",
    "exports.schedule", "exports.download", "exports.dashboard",

    "backups.view",
    "backups.create",
    "backups.download",

    "exchange_rates.view",
    "exchange_rates.update",
]


# 一般成員：以自己的帳務管理為主
MEMBER_PERMISSIONS = [
    "dashboard.view",

    "transactions.view",
    "transactions.create",
    "transactions.update",
    "transactions.void",

    "accounts.view",
    "accounts.transfer",

    "categories.view",

    "recurring_bills.view",
    "bills.view",
    "recurring_bills.create",
    "bills.create",
    "recurring_bills.update",
    "bills.update",
    "recurring_bills.void",
    "bills.void",

    "payments.view",
    "payments.create",
    "payments.update",
    "payments.void",

    "reports.view",
    "notifications.view",
    "exports.view", "exports.create", "exports.download",

    "imports.view",
    "imports.create",
    "imports.confirm",

    "attachments.view",
    "attachments.upload",

    "ocr.view",
    "ocr.create",
    "ocr.confirm",

    "family.view",
    "members.view",
    "exchange_rates.view",
]


# 記帳人員：負責全家庭帳務登錄及維護
BOOKKEEPER_PERMISSIONS = [
    "dashboard.view",

    "transactions.view",
    "transactions.create",
    "transactions.update",
    "transactions.void",

    "accounts.view",
    "categories.view",

    "recurring_bills.view",
    "bills.view",
    "recurring_bills.create",
    "bills.create",
    "recurring_bills.update",
    "bills.update",

    "payments.view",
    "payments.create",
    "payments.update",

    "reconciliation.view",
    "reconciliation.create",
    "reconciliation.match",
    "reconciliation.unmatch",

    "reports.view",
    "notifications.view", "exports.view", "exports.create", "exports.download",

    "imports.view",
    "imports.create",
    "imports.confirm",
    "imports.void",

    "attachments.view",
    "attachments.upload",

    "ocr.view",
    "ocr.create",
    "ocr.retry",
    "ocr.confirm",

    "family.view",
    "notifications.view",
    "exports.view", "exports.create", "exports.download",
    "exchange_rates.view",
]


# 檢視人員：只能查看，不可新增、修改或作廢
VIEWER_PERMISSIONS = [
    "dashboard.view",
    "transactions.view",
    "accounts.view",
    "categories.view",
    "recurring_bills.view",
    "bills.view",
    "payments.view",
    "reconciliation.view",
    "reports.view",
    "notifications.view", "exports.view",
    "attachments.view",
    "ocr.view",
    "family.view",
    "members.view",
    "exchange_rates.view",
]


# 資料範圍設定
# own：只能操作自己建立的資料
# family：可操作全家庭資料
ADMIN_SCOPES = {
    "transactions": "family",
    "accounts": "family",
    "categories": "family",
    "recurring_bills": "family",
    "bills": "family",
    "payments": "family",
    "reconciliation": "family",
    "reports": "family",
    "exports": "family",
    "exports": "family",
    "exports": "family",
    "imports": "family",
    "attachments": "family",
    "ocr": "family",
    "audit_logs": "family",
    "exports": "family",
}

FINANCE_SCOPES = {
    "transactions": "family",
    "accounts": "family",
    "categories": "family",
    "recurring_bills": "family",
    "bills": "family",
    "payments": "family",
    "reconciliation": "family",
    "reports": "family",
    "imports": "family",
    "attachments": "family",
    "ocr": "family",
    "audit_logs": "family",
    "exports": "family",
}

MEMBER_SCOPES = {
    "transactions": "own",
    "accounts": "family",
    "categories": "family",
    "recurring_bills": "own",
    "bills": "own",
    "payments": "own",
    "reports": "own",
    "exports": "own",
    "exports": "own",
    "imports": "own",
    "attachments": "own",
    "ocr": "own",
}

BOOKKEEPER_SCOPES = {
    "transactions": "family",
    "accounts": "family",
    "categories": "family",
    "recurring_bills": "family",
    "bills": "family",
    "payments": "family",
    "reconciliation": "family",
    "reports": "family",
    "imports": "family",
    "attachments": "family",
    "ocr": "family",
}

VIEWER_SCOPES = {
    "transactions": "family",
    "accounts": "family",
    "categories": "family",
    "recurring_bills": "family",
    "bills": "family",
    "payments": "family",
    "reconciliation": "family",
    "reports": "family",
    "attachments": "family",
    "ocr": "family",
}


# 預設角色清單
DEFAULT_ROLES = [
    {
        "name": "家庭管理員",
        "description": "管理家庭、成員、帳務及全部系統功能",
        "is_system": True,
        "permissions": ADMIN_PERMISSIONS,
        "data_scopes": ADMIN_SCOPES,
    },
    {
        "name": "財務管理員",
        "description": "管理全家庭財務、帳務、對帳及報表",
        "is_system": True,
        "permissions": FINANCE_PERMISSIONS,
        "data_scopes": FINANCE_SCOPES,
    },
    {
        "name": "一般成員",
        "description": "管理自己的帳務及查看授權的家庭資料",
        "is_system": True,
        "permissions": MEMBER_PERMISSIONS,
        "data_scopes": MEMBER_SCOPES,
    },
    {
        "name": "記帳人員",
        "description": "負責全家庭帳務登錄、付款及資料匯入",
        "is_system": True,
        "permissions": BOOKKEEPER_PERMISSIONS,
        "data_scopes": BOOKKEEPER_SCOPES,
    },
    {
        "name": "檢視人員",
        "description": "只能查看授權範圍內的家庭財務資料",
        "is_system": True,
        "permissions": VIEWER_PERMISSIONS,
        "data_scopes": VIEWER_SCOPES,
    },
]
