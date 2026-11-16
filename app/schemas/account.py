
"""
家庭記帳系統：帳戶管理資料結構

負責：
1. 新增帳戶資料驗證
2. 修改帳戶資料驗證
3. 帳戶資料回傳
4. 帳戶清單回傳

支援：
銀行、定期存款、現金、信用卡、
電子支付及其他帳戶。
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


AccountType = Literal[
    "bank",
    "time_deposit",
    "cash",
    "credit_card",
    "e_wallet",
    "other",
]


class AccountBase(BaseModel):
    """帳戶基本資料"""

    name: str = Field(
        min_length=1,
        max_length=100,
        description="帳戶名稱",
    )

    account_type: AccountType = Field(
        description="帳戶類型",
    )

    currency_code: str = Field(
        default="TWD",
        min_length=3,
        max_length=3,
        description="幣別，例如 TWD、USD、JPY",
    )

    institution_name: str | None = Field(
        default=None,
        max_length=100,
        description="銀行或金融機構名稱",
    )

    account_number_last4: str | None = Field(
        default=None,
        min_length=4,
        max_length=4,
        pattern=r"^\d{4}$",
        description="帳號末四碼",
    )

    credit_limit: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=20,
        decimal_places=4,
        description="信用卡額度",
    )

    statement_day: int | None = Field(
        default=None,
        ge=1,
        le=31,
        description="信用卡結帳日",
    )

    payment_due_day: int | None = Field(
        default=None,
        ge=1,
        le=31,
        description="信用卡繳款截止日",
    )

    note: str | None = Field(
        default=None,
        max_length=500,
        description="帳戶備註",
    )

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, value: str) -> str:
        value = value.strip().upper()

        if not value.isalpha():
            raise ValueError("幣別只能使用英文字母")

        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("帳戶名稱不可為空白")

        return value

    @field_validator("institution_name", "note")
    @classmethod
    def normalize_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_credit_card_fields(self):
        has_credit_card_fields = any(
            value is not None
            for value in (
                self.credit_limit,
                self.statement_day,
                self.payment_due_day,
            )
        )

        if (
            has_credit_card_fields
            and self.account_type != "credit_card"
        ):
            raise ValueError(
                "信用卡額度、結帳日及繳款日只能用於信用卡帳戶"
            )

        return self


class AccountCreate(AccountBase):
    """新增帳戶請求"""

    pass


class AccountUpdate(BaseModel):
    """修改帳戶請求"""

    model_config = ConfigDict(
        extra="forbid",
    )

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    account_type: AccountType | None = None

    currency_code: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
    )

    institution_name: str | None = Field(
        default=None,
        max_length=100,
    )

    account_number_last4: str | None = Field(
        default=None,
        min_length=4,
        max_length=4,
        pattern=r"^\d{4}$",
    )

    credit_limit: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=20,
        decimal_places=4,
    )

    statement_day: int | None = Field(
        default=None,
        ge=1,
        le=31,
    )

    payment_due_day: int | None = Field(
        default=None,
        ge=1,
        le=31,
    )

    note: str | None = Field(
        default=None,
        max_length=500,
    )

    is_active: bool | None = None

    @field_validator(
        "name",
        "account_type",
        "currency_code",
        "is_active",
        mode="before",
    )
    @classmethod
    def reject_null_required_fields(cls, value):
        if value is None:
            raise ValueError("此欄位不可為 null")

        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("帳戶名稱不可為空白")

        return value

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, value: str) -> str:
        value = value.strip().upper()

        if not value.isalpha():
            raise ValueError("幣別只能使用英文字母")

        return value

    @field_validator("institution_name", "note")
    @classmethod
    def normalize_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_update_fields(self):
        if not self.model_fields_set:
            raise ValueError("至少需要提供一個修改欄位")

        has_credit_card_fields = any(
            value is not None
            for value in (
                self.credit_limit,
                self.statement_day,
                self.payment_due_day,
            )
        )

        if (
            has_credit_card_fields
            and self.account_type is not None
            and self.account_type != "credit_card"
        ):
            raise ValueError(
                "信用卡專用欄位不能搭配非信用卡帳戶類型"
            )

        return self


class AccountResponse(BaseModel):
    """帳戶資料回傳"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    family_id: int
    name: str
    account_type: str
    currency_code: str
    institution_name: str | None = None
    account_number_last4: str | None = None
    credit_limit: Decimal | None = None
    statement_day: int | None = None
    payment_due_day: int | None = None
    note: str | None = None
    is_active: bool
    created_by: int
    created_at: datetime
    updated_at: datetime


class AccountListResponse(BaseModel):
    """帳戶清單回傳"""

    success: bool
    total: int
    accounts: list[AccountResponse]


class AccountMessageResponse(BaseModel):
    """帳戶操作結果"""

    success: bool
    message: str
    account: AccountResponse | None = None
