"""Pushes items to the external inventory service."""

import requests


def push_items(items: list[dict]) -> int:
    response = requests.post("https://api.example.com/items", json=items)
    return response.status_code
