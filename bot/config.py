import os
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    PAYMENT_PROVIDER_TOKEN: str = ""
    ADMIN_IDS: str = ""
    CHANNEL_INVITE_LINK: str = "https://t.me/"
    CHANNEL_ID: str = ""
    DB_NAME: str = "bot_database.db"
    PROXY_URL: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def admin_id_list(self) -> List[int]:
        """Возвращает список ID администраторов как целые числа."""
        if not self.ADMIN_IDS:
            return []
        result = []
        for admin_id in self.ADMIN_IDS.split(","):
            admin_id = admin_id.strip()
            if admin_id.isdigit():
                result.append(int(admin_id))
        return result


config = Settings()
