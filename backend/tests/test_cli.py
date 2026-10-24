from sqlalchemy.orm import Session

from app.cli import create_admin_interactive
from app.models.user import User, UserRole


def test_create_admin_activates_existing_inactive_admin(db_session: Session) -> None:
    user = User(
        full_name="Pending Admin",
        email="pending-admin-cli@example.com",
        password_hash="existing-password-hash",
        role=UserRole.ADMIN,
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    result = create_admin_interactive(
        db=db_session,
        full_name="Pending Admin",
        email="PENDING-ADMIN-CLI@example.com",
    )

    db_session.refresh(user)
    assert result == 0
    assert user.role == UserRole.ADMIN
    assert user.is_active is True


def test_create_admin_leaves_existing_active_admin_unchanged(db_session: Session) -> None:
    user = User(
        full_name="Existing Admin",
        email="active-admin-cli@example.com",
        password_hash="existing-password-hash",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    result = create_admin_interactive(
        db=db_session,
        full_name="Existing Admin",
        email="active-admin-cli@example.com",
    )

    db_session.refresh(user)
    assert result == 0
    assert user.is_active is True
