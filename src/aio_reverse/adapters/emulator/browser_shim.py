"""Browser environment shimming for emulated JS execution."""

from typing import Any


class BrowserEnvironmentShim:
    """Provides mock objects (window, navigator, document, location, crypto) for JS sandboxes."""

    @staticmethod
    def generate_shim_code(custom_headers: dict[str, str] | None = None) -> str:
        """Returns standard browser mock headers & globals."""
        ua = (custom_headers or {}).get(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        return f"""
        var window = globalThis;
        var navigator = {{
            userAgent: "{ua}",
            platform: "Win32",
            languages: ["en-US", "en"],
            webdriver: false
        }};
        var location = {{
            href: "https://target.local/",
            origin: "https://target.local",
            protocol: "https:",
            host: "target.local",
            hostname: "target.local",
            pathname: "/"
        }};
        var document = {{
            cookie: "",
            referrer: ""
        }};
        """
