from __future__ import annotations


def build_label(text: str, fallback: str = "Unknown") -> str:
    cleaned = text.strip()
    return cleaned or fallback
