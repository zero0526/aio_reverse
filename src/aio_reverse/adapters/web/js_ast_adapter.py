"""JavaScript Bundle AST Parser Adapter."""

from aio_reverse.domain.entities.endpoint import ApiEndpoint
from aio_reverse.domain.entities.crypto import CryptoRoutine


class JsAstAdapter:
    """Parses JavaScript bundles to find API fetch/axios endpoints and crypto algorithms."""

    def extract_endpoints_from_bundle(self, bundle_content: str) -> list[ApiEndpoint]:
        # Skeleton: Walks AST for fetch(), axios(), XMLHttpRequest calls
        return []

    def extract_signing_functions(self, bundle_content: str) -> list[CryptoRoutine]:
        # Skeleton: Detects CryptoJS, subtle.crypto, or custom hash loops
        return []
