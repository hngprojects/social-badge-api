from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Base declarative class for SQLAlchemy ORM models.

    Serves as the common registry for metadata, schema definitions,
    and database model mappings across the application.
    """

    pass
