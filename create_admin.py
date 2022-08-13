from app import app, db, User
from getpass import getpass
import sys

def create_admin():
    with app.app_context():
        user_id = input("ログインIDを入力してください：")
        password = getpass("パスワードを入力してください：")
        admin_user = User(user_id=user_id, password=password, print_name="YANSハッカソン運営委員", is_admin=True)
        db.session.add(admin_user)
        db.session.commit()
        print(f"admin アカウントを追加しました。user_id={user_id}")


if __name__ == "__main__":
    sys.exit(create_admin())