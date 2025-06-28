class CEOAgent:
    """Stub agent for high-level decisions."""

    def decide(self, question: str) -> str:
        result = f"[CEOAgent] Approving: {question}"
        print(result)
        return "approved"
