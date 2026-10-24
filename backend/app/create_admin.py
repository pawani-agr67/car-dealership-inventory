"""Provision an administrator explicitly; registration always creates buyers."""
import getpass
import sqlite3

from app.main import db, hash_password, initialize


def main():
    initialize()
    email = input("Admin email: ").strip().lower()
    if "@" not in email:
        raise SystemExit("Enter a valid email address")
    password = getpass.getpass("Admin password (at least 8 characters): ")
    if len(password) < 8:
        raise SystemExit("Password must have at least 8 characters")
    with db() as connection:
        try:
            connection.execute("INSERT INTO users(email, password_hash, role) VALUES(?, ?, 'admin')", (email, hash_password(password)))
        except sqlite3.IntegrityError:
            raise SystemExit("That email is already registered")
    print("Admin created. You can now log in.")


if __name__ == "__main__":
    main()
