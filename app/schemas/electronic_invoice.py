from datetime import date, datetime
from decimal import Decimal
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ElectronicInvoiceItemImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_name: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(max_digits=20, decimal_places=2)


    @field_validator("item_name")
    @classmethod
    def clean_item_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("商品名稱不可空白")
        return value


class ElectronicInvoiceImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_date: date
    invoice_number: str = Field(min_length=10, max_length=10)
    merchant_tax_id: str | None = Field(default=None, max_length=8)
    merchant_name: str = Field(min_length=1, max_length=200)
    total_amount: Decimal = Field(ge=0, max_digits=20, decimal_places=2)
    invoice_status: str | None = Field(default=None, max_length=60)
    carrier_type: str | None = Field(default=None, max_length=100)
    duplicate_in_source: bool = False
    items: list[ElectronicInvoiceItemImport] = Field(default_factory=list, max_length=1000)

    @field_validator("invoice_number")
    @classmethod
    def normalize_invoice_number(cls, value: str) -> str:
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}[0-9]{8}", value):
            raise ValueError("發票號碼格式必須為兩個英文字母加八位數字")
        return value

    @field_validator("merchant_tax_id")
    @classmethod
    def normalize_tax_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not re.fullmatch(r"[0-9]{8}", value):
            raise ValueError("商店統一編號必須為八位數字")
        return value

    @field_validator("merchant_name")
    @classmethod
    def clean_merchant_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("商店名稱不可空白")
        return value

    @field_validator("invoice_status", "carrier_type")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ElectronicInvoiceImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_filename: str = Field(min_length=1, max_length=255)
    invoices: list[ElectronicInvoiceImportItem] = Field(min_length=1, max_length=1000)

    @field_validator("source_filename")
    @classmethod
    def clean_filename(cls, value: str) -> str:
        value = value.replace("\\", "/").split("/")[-1].strip()
        if not value:
            raise ValueError("來源檔名不可空白")
        return value[:255]

    @model_validator(mode="after")
    def validate_total_items(self):
        total_items = sum(len(invoice.items) for invoice in self.invoices)
        if total_items > 20000:
            raise ValueError("單批商品明細不可超過 20,000 筆")
        return self


class ElectronicInvoiceImportResponse(BaseModel):
    success: bool = True
    message: str
    batch_id: int
    received_count: int
    saved_count: int
    duplicate_count: int
    detail_count: int


class ElectronicInvoiceItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_name: str
    amount: Decimal
    sort_order: int


class ElectronicInvoiceListItem(BaseModel):
    id: int
    family_id: int
    import_batch_id: int
    invoice_date: date
    invoice_period: str
    invoice_number: str
    merchant_tax_id: str | None
    merchant_name: str
    total_amount: Decimal
    detail_total_amount: Decimal | None
    difference_amount: Decimal | None
    currency_code: str
    invoice_status: str | None
    carrier_type: str | None
    validation_status: str
    duplicate_in_source: bool
    linked_transaction_id: int | None
    is_voided: bool
    created_by: int
    created_at: datetime
    item_count: int


class ElectronicInvoiceDetail(ElectronicInvoiceListItem):
    items: list[ElectronicInvoiceItemResponse]


class ElectronicInvoiceListResponse(BaseModel):
    success: bool = True
    total: int
    skip: int
    limit: int
    invoices: list[ElectronicInvoiceListItem]


class ElectronicInvoiceVoidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None
