"""
PostgresSQL connection configuration for PROVIDER simenv.

Usage:
    from db_config import PostgresDBConfig

    cfg = PostgresDBConfig()    # uses defaults below
    cfg = PostgresDBConfig(host="my-server", dbname="provider")

    engine_url = cfg.sqlalchemy_url()
    logging.debug(cfg)      # safe repr, password masked
"""

import os
from dataclasses import dataclass, field

@dataclass
class PostgresDBConfig:
    """
    Holds PostgresSQL connection parameters.

    Defaults point to a local development instance - override per env:
    - local Docker: host="localhost", port=5432
    - palaestrAI: host=<server>, port=<port>, user=<user>, password=<pw>
    """

    host: str = field(default_factory=lambda: os.getenv("PROVIDER_SIMENV_PG_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("PROVIDER_SIMENV_PG_PORT", "5432")))
    dbname: str = field(default_factory=lambda: os.getenv("PROVIDER_SIMENV_PG_DB", "provider_simenv"))
    user: str = field(default_factory=lambda: os.getenv("PROVIDER_SIMENV_PG_USER", "postgres"))
    password: str = field(default_factory=lambda: os.getenv("PROVIDER_SIMENV_PG_PASSWORD", "postgres"))
    postgres_url: str | None = field(default_factory=lambda: os.getenv("PROVIDER_SIMENV_POSTGRES_URL"))

    def sqlalchemy_url(self) -> str:
        """
        Return a SQLAlchemy-compativbe connection URL.

        Example: postgresql+psycopg2://postgres:postgres@localhost:5432/provider_simenv
        """
        if self.postgres_url:
            # Accept either postgresql://... or postgresql+psycopg2://...
            return self.postgres_url

        return (
            f"postgresql+psycopg2://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.dbname}"
        )

    def __repr__(self) -> str:
        """Password is masked in repr to avoid accidental logging."""
        return (
            f"PostgresDBConfig(host={self.host}, port={self.port}, "
            f"dbname={self.dbname}, user={self.user}, password='***')"
        )