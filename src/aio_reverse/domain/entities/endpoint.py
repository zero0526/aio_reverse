"""Network API Endpoint entity."""

from dataclasses import dataclass, field
from enum import Enum


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    OPTIONS = "OPTIONS"
    HEAD = "HEAD"


@dataclass(frozen=True)
class ApiEndpoint:
    """Represents a reverse-engineered network API endpoint."""

    url: str
    method: HttpMethod
    headers: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    signature_headers: list[str] = field(default_factory=list)
    is_authenticated: bool = False
