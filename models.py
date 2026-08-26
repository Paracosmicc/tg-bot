"""
MongoDB Data Models & Schemas.
"""
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UserModel:
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class GroupModel:
    chat_id: int
    title: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class GroupMemberModel:
    chat_id: int
    user_id: int
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MessageModel:
    chat_id: int
    role: str
    content: str
    user_id: Optional[int] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CoupleModel:
    chat_id: int
    user_id_1: int
    user_id_2: int
    love_score: int
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    broken_up_at: Optional[datetime] = None


@dataclass
class LoveStatsModel:
    chat_id: int
    user_id: int
    times_matched: int = 0
    times_broken_up: int = 0
    compliments_received: int = 0
    roasts_received: int = 0
