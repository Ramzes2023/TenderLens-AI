"""Strict factual extraction schema."""
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.currency import normalize_currency_code

Text = Annotated[str, Field(max_length=3000)]
Items = Annotated[list[Text], Field(max_length=50)]
Amount = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Percent = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]


class TenderAnalysis(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    title: Text | None = None
    tender_number: Text | None = None
    customer: Text | None = None
    initial_price: Amount | None = None
    currency: Text | None = None
    submission_deadline: Text | None = None
    contract_term: Text | None = None
    delivery_region: Text | None = None
    delivery_address: Text | None = None
    bid_security_amount: Amount | None = None
    bid_security_percent: Percent | None = None
    contract_security_amount: Amount | None = None
    contract_security_percent: Percent | None = None
    procurement_object: Text | None = None
    quantity: Text | None = None
    participant_requirements: Items = Field(default_factory=list)
    required_documents: Items = Field(default_factory=list)
    technical_requirements: Items = Field(default_factory=list)
    risks: Items = Field(default_factory=list)
    important_conditions: Items = Field(default_factory=list)
    missing_information: Items = Field(default_factory=list)


    @field_validator(
        "currency",
        mode="before",
    )
    @classmethod
    def normalize_currency(
        cls,
        value,
    ):
        if (
            value is None
            or isinstance(value, str)
        ):
            return normalize_currency_code(
                value
            )

        return value
