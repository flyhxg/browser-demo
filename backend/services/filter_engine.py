"""Signal filtering engine with configurable rules."""
from typing import Any

from services.database import get_db


class FilterRule:
    """Represents a single filter rule."""

    def __init__(self, name: str, field: str, operator: str, value: Any):
        self.name = name
        self.field = field
        self.operator = operator
        self.value = value

    def evaluate(self, data: dict[str, Any]) -> bool:
        """Evaluate rule against data."""
        actual = data.get(self.field)
        if actual is None:
            return True  # Missing data passes

        try:
            if self.operator == ">":
                return float(actual) > float(self.value)
            elif self.operator == "<":
                return float(actual) < float(self.value)
            elif self.operator == ">=":
                return float(actual) >= float(self.value)
            elif self.operator == "<=":
                return float(actual) <= float(self.value)
            elif self.operator == "==":
                return str(actual) == str(self.value)
            elif self.operator == "!=":
                return str(actual) != str(self.value)
            elif self.operator == "in":
                return actual in self.value
            else:
                return True
        except (ValueError, TypeError):
            return True


def get_default_rules() -> list[FilterRule]:
    """Get default filtering rules."""
    return [
        FilterRule("max_market_cap_rank", "cg_market_cap_rank", "<", 500),
        FilterRule("min_confidence", "confidence", ">=", 0.7),
        FilterRule("max_funding_rate", "okx_funding_rate", "<", 0.05),
        FilterRule("min_24h_change", "cg_price_change_24h", ">", -30),
        FilterRule("max_24h_change", "cg_price_change_24h", "<", 50),
    ]


def validate_signal(signal_data: dict[str, Any], rules: list[FilterRule] | None = None) -> dict[str, Any]:
    """Validate a signal against filtering rules.

    Returns:
        Dict with validation_result ("pass" or "fail") and fail_reason.
    """
    if rules is None:
        rules = get_default_rules()

    failed_rules = []
    for rule in rules:
        if not rule.evaluate(signal_data):
            failed_rules.append(rule.name)

    if failed_rules:
        return {
            "validation_result": "fail",
            "fail_reason": f"Failed rules: {', '.join(failed_rules)}",
        }

    return {
        "validation_result": "pass",
        "fail_reason": None,
    }
