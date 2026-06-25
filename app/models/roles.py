import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.users import User


class Role(Base):
    """Database representation of a user role.

    Defines specific authorization permissions or access levels (e.g., 'admin', 'user')
    that can be assigned to users in the system.
    """

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("name", name="uq_roles_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    user_roles: Mapped[list[UserRole]] = relationship(
        "UserRole",
        back_populates="role",
        cascade="all, delete-orphan",
    )
    users: Mapped[list[User]] = relationship(
        "User",
        secondary="user_roles",
        back_populates="roles",
        overlaps="user_roles,user,role",
    )


class UserRole(Base):
    """Association model representing the many-to-many relationship between users and
    roles.

    Links a specific user to a specific role, tracking assignment timestamps.
    """

    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_id_role_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    user: Mapped[User] = relationship("User", back_populates="user_roles")
    role: Mapped[Role] = relationship("Role", back_populates="user_roles")
