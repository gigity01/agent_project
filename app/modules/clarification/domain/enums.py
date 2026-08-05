"""澄清请求状态。"""

from enum import Enum


class ClarificationStatus(str, Enum):
    OPEN = "open"
    ANSWERED = "answered"
    RESOLVED = "resolved"
    EXPIRED = "expired"
