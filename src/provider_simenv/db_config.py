"""
PostgresSQL connection configuration for PROVIDER simenv.

Usage:
    from db_config import PostgresDBConfig

    cfg = PostgresDBConfig()    # uses defaults below
    cfg = PostgresDBConfig(host="my-server", dbname="provider")

    engine_url = cfg.sqlalchemy_url()
    print(cfg)      # safe repr, password masked
"""

from dataclasses import dataclass, field

@dataclass
class PostgresDBConfig:
    """
    Holds PostgresSQL connection parameters.

    Defaults point to a local development instance - override per env:
    - local Docker: host="localhost", port=5432
    - palaestrAI: host=<server>, port=<port>, user=<user>, password=<pw>
    """

    host: str = "localhost"
    port: int = 5432
    dbname: str = "provider_simenv"
    user: str = "postgres"
    password: str = "postgres"

    def sqlalchemy_url(self) -> str:
        """
        Return a SQLAlchemy-compativbe connection URL.

        Example: postgresql+psycopg2://postgres:postgres@localhost:5432/provider_simenv
        """
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