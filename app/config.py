from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str
    db_path: str = "./reminders.db"
    default_tz: str = "Europe/Moscow"


settings = Settings()
