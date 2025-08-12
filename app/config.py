from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, Field
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

def read_secret(file_path: str) -> str:
    """Чтение секрета из файла (для Docker Secrets)"""
    try:
        with open(file_path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

class Settings(BaseSettings):
    # Секреты из Docker Secrets
    FATHERBOT_TOKEN: str = Field(default="", env="FATHERBOT_TOKEN")
    YCLIENTS_USER_TOKEN: str = Field(default="", env="YCLIENTS_USER_TOKEN")
    YCLIENTS_PARTNER_TOKEN: str = Field(default="", env="YCLIENTS_PARTNER_TOKEN")
    POSTGRES_USER: str = Field(default="postgres", env="POSTGRES_USER")
    POSTGRES_PASSWORD: str = Field(default="", env="POSTGRES_PASSWORD")
    POSTGRES_DB: str = Field(default="loyalty_db", env="POSTGRES_DB")
    ADMIN_IDS: List[int] = Field(default=[], env="ADMINS_IDS")

    # Остальные настройки из .env
    COMPANY_ID: int = Field(default=0, env="COMPANY_ID")
    YCLIENTS_BOOK_URL: AnyHttpUrl = Field(default="https://example.com", env="YCLIENTS_BOOK_URL")
    SUPPORT_PHONE: str = Field(default="", env="SUPPORT_PHONE")
    COMPANY_YMAPS_LINK: str = Field(default="", env="COMPANY_YMAPS_LINK")
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@db:5432/{self.POSTGRES_DB}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        secrets_dir = "/run/secrets"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Проверяем Docker Secrets
        if os.path.exists(self.Config.secrets_dir):
            self.FATHERBOT_TOKEN = read_secret(f"{self.Config.secrets_dir}/fatherbot_token") or self.FATHERBOT_TOKEN
            self.YCLIENTS_USER_TOKEN = read_secret(f"{self.Config.secrets_dir}/yclients_user_token") or self.YCLIENTS_USER_TOKEN
            self.YCLIENTS_PARTNER_TOKEN = read_secret(f"{self.Config.secrets_dir}/yclients_partner_token") or self.YCLIENTS_PARTNER_TOKEN
            self.POSTGRES_USER = read_secret(f"{self.Config.secrets_dir}/postgres_user") or self.POSTGRES_USER
            self.POSTGRES_PASSWORD = read_secret(f"{self.Config.secrets_dir}/postgres_password") or self.POSTGRES_PASSWORD
            self.POSTGRES_DB = read_secret(f"{self.Config.secrets_dir}/postgres_db") or self.POSTGRES_DB

            # <-- добавь вот это:
            admin_ids_str = read_secret(f"{self.Config.secrets_dir}/admins_ids")
            if admin_ids_str:
                try:
                    self.ADMIN_IDS = list(map(int, admin_ids_str.split(",")))
                except ValueError:
                    print("Ошибка разбора admins_ids, требуется проверить формат файла")


settings = Settings()
