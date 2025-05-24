import streamlit_authenticator as stauth

from auto_vpn.core.settings import Settings


class AuthManager:
    """Handles authentication-related functionality"""

    COOKIE_NAME = "vpn_auth_cookie"
    COOKIE_KEY = "signature_key"
    COOKIE_EXPIRY_DAYS = 30

    def __init__(self, settings: Settings):
        self.settings: Settings = settings
        self.authenticator = self._init_authenticator()

    def _get_credentials_config(self) -> dict:
        """Generate credentials configuration"""
        return {
            "credentials": {
                "usernames": {
                    self.settings.USERNAME: {
                        "email": "admin@example.com",
                        "failed_login_attempts": 0,
                        "first_name": "Admin",
                        "last_name": "User",
                        "logged_in": False,
                        "password": self.settings.PASSWORD,
                        "roles": ["admin"],
                    }
                }
            },
            "cookie": {
                "expiry_days": self.COOKIE_EXPIRY_DAYS,
                "key": self.COOKIE_KEY,
                "name": self.COOKIE_NAME,
            },
        }

    def _init_authenticator(self) -> stauth.Authenticate:
        """Initialize the authenticator"""
        config = self._get_credentials_config()
        return stauth.Authenticate(
            credentials=config["credentials"],
            cookie_name=config["cookie"]["name"],
            key=config["cookie"]["key"],
            cookie_expiry_days=config["cookie"]["expiry_days"],
            auto_hash=True,
        )
