from __future__ import annotations
import getpass
from app.user_store import create_user, initialize_user_database


def main():
    print("Create the first DevOps Portal administrator")
    email=input("Mashreq email: ").strip().lower()
    password=getpass.getpass("Password (minimum 10 characters): ")
    confirm=getpass.getpass("Confirm password: ")
    if password != confirm: raise SystemExit("Passwords do not match")
    initialize_user_database()
    user=create_user(email,password,"devops",True)
    print(f"Created DevOps administrator: {user.email}")

if __name__ == "__main__": main()
