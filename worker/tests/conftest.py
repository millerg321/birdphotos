from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db import Base


@pytest.fixture(scope="session")
def db_engine() -> Generator[Engine, None, None]:
    """Creates all tables once against TEST_DATABASE_URL for the test session."""
    engine = create_engine(settings.test_database_url)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(db_engine: Engine) -> Generator[Session, None, None]:
    """Each test runs inside a transaction that's rolled back afterwards,
    so tests don't leak state into one another.

    Uses a nested SAVEPOINT rather than relying solely on the outer
    transaction: code under test is allowed to call session.commit()
    (a legitimate pattern here — e.g. import_from_staged_upload commits
    per photo so one bad file in a batch doesn't roll back the ones
    that already succeeded), and a plain commit() would otherwise end
    the outer transaction itself, silently breaking rollback-based
    isolation. Verified this was a real gap, not a hypothetical: before
    this fix, a commit()-calling test produced `SAWarning: transaction
    already deassociated from connection` and leaked committed rows
    into the shared test database for the rest of the run. The listener
    restarts a fresh savepoint every time the current one ends, so
    commit() inside tested code only releases the savepoint — the outer
    transaction, and thus full rollback at teardown, is unaffected.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess: Session, trans: object) -> None:
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()
