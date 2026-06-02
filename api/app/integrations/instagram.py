from __future__ import annotations

import logging
from typing import Any

import httpx

from .exceptions import ConnectorAuthError, ConnectorError, ConnectorNotFoundError, ConnectorRateLimitError

logger = logging.getLogger("jeeves.instagram")

_IG_GRAPH_API = "https://graph.facebook.com/v22.0"


class InstagramConnector:
    """Instagram Business Account connector via Meta Graph API.

    Requires a Facebook App with Instagram Graph API + Instagram Manage Messages.
    Config keys: access_token, business_page_id, instagram_account_id.
    """

    provider = "instagram"
    phi_safe = True

    def __init__(self, config: dict[str, Any]) -> None:
        self.access_token = str(config.get("access_token", ""))
        self.business_page_id = str(config.get("business_page_id", ""))
        self.instagram_account_id = str(config.get("instagram_account_id", ""))

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{_IG_GRAPH_API}{path}"
        params = kwargs.pop("params", {})
        params["access_token"] = self.access_token
        try:
            r = httpx.request(method, url, headers=self._headers(), params=params, **kwargs, timeout=30)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            logger.error("Instagram API error %s %s: %s", method, path, e)
            if e.response.status_code in (401, 403):
                raise ConnectorAuthError("instagram", method, "Invalid or expired access token")
            if e.response.status_code == 404:
                raise ConnectorNotFoundError("instagram", method, "Resource not found")
            if e.response.status_code == 429:
                raise ConnectorRateLimitError("instagram", method, "Rate limited")
            raise ConnectorError("instagram", method, f"HTTP {e.response.status_code}: {e.response.text[:200]}")
        except httpx.RequestError as e:
            raise ConnectorError("instagram", "request", str(e))

    def test_connection(self) -> bool:
        try:
            data = self._request("GET", f"/{self.instagram_account_id}", params={"fields": "name"})
            return "name" in data
        except Exception:
            return False

    def get_profile(self, ig_user_id: str) -> dict[str, Any] | None:
        try:
            return self._request("GET", f"/{ig_user_id}", params={"fields": "id,name,username,profile_picture_url"})
        except ConnectorNotFoundError:
            return None

    def send_message(self, recipient_id: str, text: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/{self.instagram_account_id}/messages",
            json={
                "recipient": {"id": recipient_id},
                "message": {"text": text},
            },
        )

    def get_conversations(self) -> list[dict[str, Any]]:
        data = self._request(
            "GET",
            f"/{self.instagram_account_id}/conversations",
            params={"platform": "instagram", "fields": "id,participants,messages"},
        )
        return data.get("data", [])

    def get_conversation_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        data = self._request(
            "GET",
            f"/{conversation_id}/messages",
            params={"fields": "id,from,to,message,created_time"},
        )
        return data.get("data", [])
