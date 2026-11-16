
from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class TransferBase(BaseModel):
    """轉帳基本資料"""

    from_account_id: int = Field(gt=0)
    to_account_id: int = Field(gt=0)

    amount: Decimal = Field(
        gt=0,
        max_digits=20,
        decimal_places=4,
    )

    currency_code: str = Field(
        default="TWD",
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
    )

    transfer_date: datetime

    description: str = Field(
        min_length=1,
        max_length=255,
    )

    fee_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=20,
        decimal_places=4,
    )

    fee_account_id: int | None = Field(
        default=None,
        gt=0,
    )

    note: str | None = None

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("轉帳說明不可為空白")

        return value

    @model_validator(mode="after")
    def validate_transfer(self):
        if self.from_account_id == self.to_account_id:
            raise ValueError("轉出帳戶與轉入帳戶不可相同")

        if self.fee_amount > 0 and self.fee_account_id is None:
            raise ValueError("有手續費時必須指定手續費扣款帳戶")

        return self


class TransferCreate(TransferBase):
    """新增轉帳"""

    pass


class TransferUpdate(BaseModel):
    """修改轉帳"""

    from_account_id: int | None = Field(default=None, gt=0)
    to_account_id: int | None = Field(default=None, gt=0)

    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=20,
        decimal_places=4,
    )

    currency_code: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
    )

    transfer_date: datetime | None = None

    description: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    fee_amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=20,
        decimal_places=4,
    )

    fee_account_id: int | None = Field(
        default=None,
        gt=0,
    )

    note: str | None = None

    @field_validator(
        "from_account_id",
        "to_account_id",
        "amount",
        "currency_code",
        "transfer_date",
        "description",
        "fee_amount",
        mode="before",
    )
    @classmethod
    def validate_required_fields_not_null(cls, value):
        if value is None:
            raise ValueError("此欄位不可為 null")

        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("轉帳說明不可為空白")

        return value

    @model_validator(mode="after")
    def validate_transfer_accounts(self):
        if (
            self.from_account_id is not None
            and self.to_account_id is not None
            and self.from_account_id == self.to_account_id
        ):
            raise ValueError("轉出帳戶與轉入帳戶不可相同")

        return self


class TransferResponse(TransferBase):
    """轉帳回應資料"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    family_id: int

    is_voided: bool
    voided_at: datetime | None

    created_by: int
    created_at: datetime
    updated_at: datetime
