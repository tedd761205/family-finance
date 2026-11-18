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
