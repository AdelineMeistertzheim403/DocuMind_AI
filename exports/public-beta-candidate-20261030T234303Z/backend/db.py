from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.engine import make_url


class Base(DeclarativeBase):
    pass


def make_engine(url):
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    return engine


def make_sessions(engine):
    return sessionmaker(engine, expire_on_commit=False)


def make_authentication_engine(url, application_engine):
    # SQLite must share the application's database (including an in-memory database).
    if make_url(url).get_backend_name() != 'postgresql':
        return application_engine
    return create_engine(url, pool_size=2, max_overflow=0, pool_timeout=1, pool_pre_ping=False,
                         connect_args={'connect_timeout': 1, 'options': '-c statement_timeout=1000'})
