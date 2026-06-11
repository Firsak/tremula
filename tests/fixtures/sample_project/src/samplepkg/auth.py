"""Authentication for the sample app."""

from .store import TokenStore


def login(user: str) -> str:
    """Log a user in and persist the token."""
    store = TokenStore()
    token = f"token-{user}"
    store.save_token(token)
    return token


def logout(user: str) -> None:
    """Drop the user's token."""
    TokenStore().save_token("")


def _helper() -> None:
    pass
