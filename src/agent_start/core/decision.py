"""Rule-based decision engine."""
from __future__ import annotations

from typing import Callable, Any, List


class Rule:
    def __init__(self, check: Callable[[Any], bool], action: Callable[[Any], Any]):
        self.check = check
        self.action = action


class DecisionEngine:
    def __init__(self) -> None:
        self.rules: List[Rule] = []

    def add_rule(self, rule: Rule) -> None:
        self.rules.append(rule)

    def decide(self, context: Any) -> Any:
        for rule in self.rules:
            if rule.check(context):
                return rule.action(context)
        return None
