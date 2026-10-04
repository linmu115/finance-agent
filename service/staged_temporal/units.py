"""Staged scalar unit extension; production unit_info is unchanged."""
from decimal import Decimal
from service.normalization import compact,unit_info


def extended_unit_info(text,metric=None):
    if compact(text).lower() in {"年","year","years"}:return str(text).strip(),Decimal(1),"years"
    return unit_info(text,metric)
