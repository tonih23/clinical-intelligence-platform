"""
Configuración de la aplicación.

Usamos pydantic-settings para que las variables de entorno se conviertan en
un objeto tipado y validado. Si falta una variable obligatoria o tiene un
tipo incorrecto, la app falla al arrancar (fail-fast), no en runtime.

Esto es lo que en empresas serias hace que un deploy roto se note en CI
y no a las 3 AM con alarmas.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings centralizados, leídos de variables de entorno y `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Postgres ---
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "cip"
    postgres_user: str = "cip"
    postgres_password: str = "cip_dev_password"

    # --- S3 / MinIO ---
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "pubmed-raw"
    s3_region: str = "us-east-1"

    # --- PubMed ---
    pubmed_api_key: str = ""
    pubmed_tool_name: str = "clinical-intelligence-platform"
    pubmed_email: str = "anonymous@example.com"

    # --- Misc ---
    log_level: str = "INFO"
    api_port: int = 8000

    @property
    def postgres_dsn(self) -> str:
        """DSN async (asyncpg) para SQLAlchemy."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_dsn_sync(self) -> str:
        """DSN sync (psycopg2) para scripts de migración / inicialización."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Devuelve un singleton de Settings.

    Usar `get_settings()` en lugar de instanciar `Settings()` directamente
    permite cachear el resultado y, en tests, hacer override fácilmente.
    """
    return Settings()
