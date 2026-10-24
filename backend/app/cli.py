import argparse
import getpass
import sys
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.user import User, UserRole


def create_admin_interactive(
    db: Session,
    full_name: str | None = None,
    email: str | None = None,
    password: str | None = None,
) -> int:
    """Creates or promotes an admin user interactively without hardcoded secrets."""
    print("=" * 60)
    print("       Multi-Role RAG Chatbot - Admin Bootstrap CLI")
    print("=" * 60)

    # 1. Full Name
    if not full_name:
        while True:
            full_name = input("Enter Admin Full Name: ").strip()
            if full_name:
                break
            print("Error: Full name cannot be blank.")
    else:
        full_name = full_name.strip()
        if not full_name:
            print("Error: Full name cannot be blank.")
            return 1

    # 2. Email (Normalized case-insensitively)
    if not email:
        while True:
            email_input = input("Enter Admin Email: ").strip().lower()
            if email_input and "@" in email_input and "." in email_input:
                email = email_input
                break
            print("Error: Please enter a valid email address.")
    else:
        email = email.strip().lower()
        if not email or "@" not in email:
            print("Error: Invalid email address.")
            return 1

    # Check if user already exists
    existing_user = db.scalar(
        select(User).where(func.lower(User.email) == email)
    )

    if existing_user:
        if existing_user.role == UserRole.ADMIN:
            if not existing_user.is_active:
                existing_user.is_active = True
                db.commit()
                print(f"Success: Existing ADMIN '{email}' has been activated.")
                return 0
            print(f"Notice: User with email '{email}' already exists and is already an active ADMIN.")
            return 0
        else:
            confirm = input(
                f"User '{email}' already exists with role '{existing_user.role.value}'. "
                "Promote to ADMIN? (y/N): "
            ).strip().lower()
            if confirm == "y":
                existing_user.role = UserRole.ADMIN
                existing_user.is_active = True
                db.commit()
                print(f"Success: User '{email}' promoted to ADMIN.")
                return 0
            else:
                print("Operation cancelled.")
                return 1

    # 3. Password Prompt (securely masked with getpass)
    if not password:
        while True:
            pw1 = getpass.getpass("Enter Admin Password (min 8 chars): ")
            if len(pw1) < 8:
                print("Error: Password must be at least 8 characters long.")
                continue
            pw2 = getpass.getpass("Confirm Admin Password: ")
            if pw1 != pw2:
                print("Error: Passwords do not match. Please try again.")
                continue
            password = pw1
            break
    else:
        if len(password) < 8:
            print("Error: Password must be at least 8 characters long.")
            return 1

    # 4. Hash password with Argon2 and store in DB
    hashed_password = get_password_hash(password)
    admin_user = User(
        full_name=full_name,
        email=email,
        password_hash=hashed_password,
        role=UserRole.ADMIN,
        is_active=True,
    )

    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)

    print("-" * 60)
    print(f"Success: Admin user '{admin_user.email}' (ID: {admin_user.id}) created successfully.")
    print("=" * 60)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-Role RAG Chatbot CLI management tool")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: create-admin
    admin_parser = subparsers.add_parser("create-admin", help="Bootstrap an administrator account")
    admin_parser.add_argument("--name", help="Admin full name (optional, prompts if omitted)")
    admin_parser.add_argument("--email", help="Admin email (optional, prompts if omitted)")
    admin_parser.add_argument("--password", help="Admin password (optional, prompts if omitted)")

    args = parser.parse_args()

    if args.command == "create-admin":
        db = SessionLocal()
        try:
            exit_code = create_admin_interactive(
                db=db,
                full_name=args.name,
                email=args.email,
                password=args.password,
            )
            sys.exit(exit_code)
        finally:
            db.close()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
