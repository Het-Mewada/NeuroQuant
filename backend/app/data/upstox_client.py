import httpx
from typing import Dict, Any, Optional
from app.core.config import settings


class UpstoxClient:
    """
    Upstox API V3 Client for real-time options chain and Greeks.
    """

    BASE_URL = "https://api.upstox.com/v2"

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token
        self.api_key = settings.UPSTOX_API_KEY
        self.api_secret = settings.UPSTOX_API_SECRET
        self.redirect_uri = settings.UPSTOX_REDIRECT_URI

    def get_login_url(self) -> str:
        return f"{self.BASE_URL}/login/authorization/dialog?response_type=code&client_id={self.api_key}&redirect_uri={self.redirect_uri}"

    async def get_access_token(self, auth_code: str) -> Optional[str]:
        url = f"{self.BASE_URL}/login/authorization/token"
        headers = {"accept": "application/json", "Api-Version": "2.0"}
        data = {
            "code": auth_code,
            "client_id": self.api_key,
            "client_secret": self.api_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code"
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, data=data)
            if resp.status_code == 200:
                json_data = resp.json()
                self.access_token = json_data.get("access_token")
                return self.access_token
        return None

    async def get_option_chain(self, instrument_key: str, expiry_date: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves live option chain with native Delta, Gamma, Theta, Vega from Upstox.
        """
        if not self.access_token:
            return None

        url = f"{self.BASE_URL}/option/chain"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }
        params = {
            "instrument_key": instrument_key,
            "expiry_date": expiry_date
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                return resp.json().get("data", {})
        return None
