"""D-153: a managed database's URL (Neon) as asyncpg takes it."""

import ssl

from autora.db.session import connection_url
from autora.infra.settings import load_settings

NEON = (
    "postgresql://neondb_owner:secret@ep-calm-hill-a.c-3.ap-southeast-1.aws.neon.tech/aisiwhale"
    "?sslmode=require&channel_binding=require"
)


def test_neon_s_url_is_taken_as_it_is_given():
    settings = load_settings(_env_file=None, database_url=NEON)
    assert settings.database_url.startswith("postgresql+asyncpg://neondb_owner:")
    url, connect_args = connection_url(settings.database_url)
    assert url.drivername == "postgresql+asyncpg"
    assert url.database == "aisiwhale" and dict(url.query) == {}
    # encrypted and checked: the server's certificate against known roots, and its name
    context = connect_args["ssl"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname


def test_postgres_scheme_too_and_a_local_url_is_left_alone():
    settings = load_settings(_env_file=None, database_url="postgres://u:p@h/db")
    assert settings.database_url == "postgresql+asyncpg://u:p@h/db"
    url, connect_args = connection_url("postgresql+asyncpg://autora:autora@localhost:5434/autora")
    assert connect_args == {} and url.port == 5434
