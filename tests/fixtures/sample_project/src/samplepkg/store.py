"""Token persistence."""


class TokenStore:
    """Keeps tokens in memory."""

    def __init__(self) -> None:
        self.tokens: list[str] = []

    def save_token(self, token: str) -> None:
        self.tokens.append(token)
