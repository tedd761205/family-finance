from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReconciliationSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: int = Field(gt=0)
    source_batch_id: int = Field(gt=0)
    period_start: date
    period_end: date
    opening_balance: Decimal | None = Field(default=None, max_digits=20, decimal_places=4)
    closing_balance: Decimal | None = Field(default=None, max_digits=20, decimal_places=4)

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end < self.period_start:
            raise ValueError("對帳結束日期不可早於開始日期")
        return self


class ReconciliationMatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bank_import_row_id: int = Field(gt=0)
    transaction_id: int = Field(gt=0)
    allocated_amount: Decimal = Field(gt=0, max_digits=20, decimal_places=4)


class ReconciliationMatchVoid(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_reason(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("解除配對必須填寫原因")
        return self


class ReconciliationExcludeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bank_import_row_id: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_reason(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("排除明細必須填寫原因")
        return self


class ReconciliationExclusionVoid(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_reason(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("解除排除必須填寫原因")
        return self


class ReconciliationLifecycleReason(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_reason(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("此操作必須填寫原因")
        return self


class ReconciliationIssueCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bank_import_row_id: int | None = Field(default=None, gt=0)
    transaction_id: int | None = Field(default=None, gt=0)
    category: str = Field(pattern="^(bank_only|ledger_only|amount_mismatch|date_mismatch|pending|explained)$")
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_issue(self):
        if self.bank_import_row_id is None and self.transaction_id is None:
            raise ValueError("差異至少需要關聯一筆銀行明細或正式交易")
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("差異原因不可空白")
        if self.category == "bank_only" and self.bank_import_row_id is None:
            raise ValueError("銀行獨有差異必須關聯銀行明細")
        if self.category == "ledger_only" and self.transaction_id is None:
            raise ValueError("帳務獨有差異必須關聯正式交易")
        return self


class ReconciliationIssueResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution_note: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_note(self):
        self.resolution_note = self.resolution_note.strip()
        if not self.resolution_note:
            raise ValueError("結案說明不可空白")
        return self
