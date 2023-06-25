from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy.sql.functions import current_timestamp
from sqlalchemy import event
from werkzeug.security import generate_password_hash, check_password_hash


db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(256), unique=True,
                        nullable=False)
    print_name = db.Column(db.String(256), unique=False, nullable=False)
    password = db.Column(db.String(256), unique=False, nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False)
    n_submit = db.Column(db.Integer, default=0)
    scores = db.relationship("Score", backref="users")

    def __init__(self, user_id, password, print_name, is_admin=False):
        self.user_id = user_id
        self.password = password
        self.print_name = print_name
        self.is_admin = is_admin

    def __repr__(self):
        return self.user_id

    def get_id(self):
        return (self.user_id)


@event.listens_for(User.password, 'set', retval=True)
def hash_user_password(target, value, oldvalue, initiator):
    if value != oldvalue:
        return generate_password_hash(value)
    return value


class Score(db.Model):
    __tablename__ = "scores"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.TIMESTAMP, server_default=current_timestamp())
    user_primary_key = db.Column(db.Integer, db.ForeignKey('users.id'))
    comment = db.Column(db.String(256), unique=False, nullable=True)
    user = db.relationship("User")

    # 複数の評価指標を表示したい場合以下に適宜追加
    bleu = db.Column(db.Float, nullable=False)
    rouge = db.Column(db.Float, nullable=False)
    kwd = db.Column(db.Float, nullable=False)
    overall = db.Column(db.Float, nullable=False)

    # 各評価指標の変数名と表示名のマッピング。
    metrics_name_dict = {
        "bleu": "BLEU-4",
        "rouge": "Rouge-1",
        "kwd": "Kwd",
        "overall": "Overall"
    }

    # ソートに用いる（最終評価に用いる）評価指標を変数名で指定
    sort_key = "Overall"
    # ソートを昇順で行いたい場合は True にしておく
    ascending = False

    def __init__(self, result_dict):
        self.user_primary_key = result_dict['user_primary_key']
        self.comment = result_dict['comment']

        for var_name in self.metrics_name_dict.keys():
            self.__dict__[var_name] = result_dict[var_name]

