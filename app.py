from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, current_user, logout_user
from forms import LoginForm, UploadForm
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_admin import Admin, expose, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from sqlalchemy.sql.functions import current_timestamp
from sqlalchemy import event
from pytz import timezone
from werkzeug.security import generate_password_hash, check_password_hash
from dateutil import parser
import plotly.graph_objects as go
import plotly
import json
import os
import pandas as pd
from calc_score import calc_ndcg, convert_to_submit_format

try:
    from local_settings import SECRET_KEY
except ImportError:
    import os
    SECRET_KEY = os.urandom(24)

base_dir = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
login_manager = LoginManager()
login_manager.init_app(app)
app.secret_key = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///{host}/{name}'.format(**{
    'host': base_dir,
    'name': 'db.sqlite3'
})
# app.config['FLASK_ADMIN_SWATCH'] = 'United'
db = SQLAlchemy(app)
migrate = Migrate(app, db)


def utc_to_jst(timestring):
    date = parser.parse(
        timestring,
        default=parser.parse('00:00Z')
    ).astimezone(timezone("Asia/Tokyo"))
    return date.strftime("%Y-%m-%d %H:%M")


app.jinja_env.filters['utc_to_jst'] = utc_to_jst


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


class Score(db.Model):
    __tablename__ = "scores"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.TIMESTAMP, server_default=current_timestamp())
    user_primary_key = db.Column(db.Integer, db.ForeignKey('users.id'))
    comment = db.Column(db.String(256), unique=False, nullable=True)
    ndcg = db.Column(db.Float, nullable=False)
    user = db.relationship("User")

    def __init__(self, result_dict):
        self.user_primary_key = result_dict['user_primary_key']
        self.comment = result_dict['comment']
        self.ndcg = result_dict['ndcg']


db.create_all()


@event.listens_for(User.password, 'set', retval=True)
def hash_user_password(target, value, oldvalue, initiator):
    if value != oldvalue:
        return generate_password_hash(value)
    return value


class ScoreView(ModelView):
    def is_accessible(self):
        return current_user.is_admin


class UserView(ModelView):
    column_exclude_list = ['scores']

    def is_accessible(self):
        return current_user.is_admin


class MyAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        if not current_user.is_admin:
            return redirect(url_for('index'))
        return super(MyAdminIndexView, self).index()


admin = Admin(app, index_view=MyAdminIndexView(), template_mode='bootstrap3')
admin.add_view(ScoreView(Score, db.session))
admin.add_view(UserView(User, db.session))


@login_manager.user_loader
def user_loader(user_id):
    return db.session.query(User).filter_by(user_id=user_id).first()


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return redirect(url_for('index'))
    elif request.method == 'POST':
        user_id = request.form['user_id']
        password = request.form['password']
        user_info = db.session.query(User).filter_by(user_id=user_id).first()

        if user_info is not None and check_password_hash(user_info.password, password):
            # ログイン成功
            user = user_info
            login_user(user, remember=True)
            return redirect(url_for('index'))

    flash("ログインに失敗しました．", "failed")
    return redirect(url_for('index'))


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/', methods=['GET'])
def index():
    login_form = LoginForm()
    upload_form = UploadForm()
    columns = ['print_name', 'created_at', 'comment', 'ndcg', 'n_submit']
    sort_key = 'ndcg'
    ascending = False
    sql_text = "select {} from scores as s".format(', '.join(columns)) \
        + " inner join users on s.user_primary_key = users.id " \
        + " where not exists (select 1 from scores as t where s.user_primary_key" \
        + " = t.user_primary_key and s.created_at < t.created_at )" \
        + " order by {} {}".format(sort_key, 'ASC' if ascending else 'DESC')
    results = db.session.execute(sql_text)
    score_table = list(map(dict, results.fetchall()))

    return render_template(
        './index.html', login_form=login_form, upload_form=upload_form,
        current_user=current_user, score_table=score_table)


@app.route('/history', methods=['GET'])
def visualize():
    columns = ['print_name', 'created_at', 'comment', 'ndcg']
    sql_text = "select {} from scores as s".format(', '.join(columns)) \
        + " inner join users on s.user_primary_key = users.id " \
        + " order by created_at DESC"
    results = db.session.execute(sql_text)
    df_all = pd.DataFrame(list(map(dict, results.fetchall())))
    fig = go.Figure(layout_yaxis_range=[0, 1])
    for group_name, df in df_all.groupby("print_name"):
        if group_name == "YANSハッカソン運営委員":
            for _, row in df.iterrows():
                fig.add_hline(y=row["ndcg"], annotation_text=row.comment, line=dict(
                    width=1, dash="dot"), annotation_position="bottom left")
        else:
            fig.add_scatter(
                x=df.created_at.values, y=df.ndcg.values,
                text=df.comment,
                # visible='legendonly',
                name=group_name, mode="lines+markers",
                line=dict(
                    width=1,
                )
            )
    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    return render_template('history.html', graphJSON=graphJSON)


@app.route('/upload', methods=['POST'])
def upload_and_evaluate():
    upload_form = UploadForm()
    description = upload_form.description.data
    submission_data = upload_form.submission_file.data

    try:
        df_true = pd.read_json(os.path.join(base_dir + "/data/leader_board.jsonl"), orient="records", lines=True)
    except:
        flash("正解データの読み込みに失敗しました。お手数ですが運営委員までご連絡ください。", "failed")
        return redirect(url_for('index'))

    try:
        df_pred = pd.read_json(submission_data, orient="records", lines=True)
        df_true = df_true[df_true["sets"] == "leader_board-private"]
        df_true = convert_to_submit_format(df_true, "helpful_votes", "true")
        result = {
            "ndcg": calc_ndcg(df_true, df_pred)["ndcg@5"],
            "user_primary_key": current_user.id,
            "comment": str(description),
        }
        score_record = Score(result)
    except:
        flash("評価スクリプトが異常終了しました。提出ファイルのフォーマット等を見直してください。", "failed")
        return redirect(url_for('index'))

    try:
        db.session.add(score_record)
        user_record = db.session.query(User).filter_by(id=current_user.id).first()
        user_record.n_submit += 1
        db.session.commit()
    except:
        flash("データベースへの登録に失敗しました。お手数ですが運営委員までご連絡ください。", "failed")
        return redirect(url_for('index'))

    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8001, debug=True)
