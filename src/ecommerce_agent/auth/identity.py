from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Identity:
    user_id: str
    role: str
    data_scope: str
    channel: str


class IdentityError(ValueError):
    pass


class DevIdentityProvider:
    def __init__(self, config_path: Path):
        self.users = yaml.safe_load(config_path.read_text(encoding="utf-8"))["users"]

    def resolve(self, user_id: str, *, channel: str = "cli") -> Identity:
        configured = self.users.get(user_id)
        if configured is None:
            raise IdentityError(f"unknown development identity: {user_id}")
        return Identity(
            user_id=user_id,
            role=configured["role"],
            data_scope=configured["data_scope"],
            channel=channel,
        )

