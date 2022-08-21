from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, current_user, logout_user
from forms import LoginForm, UploadForm
from flask_migrate import Migrate
from flask_admin import Admin, expose, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from pytz import timezone
from werkzeug.security import check_password_hash
from dateutil import parser
import plotly.graph_objects as go
import plotly
import json
import os
import pandas as pd
from model import db, Score, User
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
db.init_app(app)
migrate = Migrate(app, db)

with app.app_context():
    db.create_all()


def utc_to_jst(timestring):
    date = parser.parse(
        timestring,
        default=parser.parse('00:00Z')
    ).astimezone(timezone("Asia/Tokyo"))
    return date.strftime("%Y-%m-%d %H:%M")


app.jinja_env.filters['utc_to_jst'] = utc_to_jst


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
    metrics_name_dict = Score.metrics_name_dict
    sort_key = Score.sort_key
    columns = [
                  'users.user_id', 'print_name', 'created_at', 'comment', 'n_submit', sort_key + '_max'
              ] + list(metrics_name_dict.keys())
    ascending = False
    sql_text = f"""
        with max_scores as (
            select 
                {sort_key} as {sort_key}_max, 
                user_primary_key
            from scores
            inner join users on scores.user_primary_key = users.id
            where not exists (
                select 1 from scores as t 
                where
                    scores.user_primary_key = t.user_primary_key and
                    scores.{sort_key} {">" if ascending else "<"} t.{sort_key}
            )
        )
        select {', '.join(columns)} from scores as s
        inner join users on s.user_primary_key = users.id 
        inner join max_scores on s.user_primary_key = max_scores.user_primary_key
        where not exists (
            select 1 from scores as t 
            where
                s.user_primary_key = t.user_primary_key and
                s.created_at < t.created_at
        )
        order by {sort_key} {'ASC' if ascending else 'DESC'}"""
    results = db.session.execute(sql_text)
    score_table = list(map(dict, results.fetchall()))

    return render_template(
        './index.html', login_form=login_form, upload_form=upload_form,
        current_user=current_user, score_table=score_table, sort_key=sort_key, metrics_name_dict=metrics_name_dict)


@app.route('/history', methods=['GET'])
def visualize():
    sort_key = Score.sort_key
    focus_id = request.args.get("id")
    columns = ['users.user_id', 'print_name', 'created_at', 'comment', sort_key]
    sql_text = f"select {', '.join(columns)} from scores as s" \
               + " inner join users on s.user_primary_key = users.id " \
               + " order by created_at DESC"
    results = db.session.execute(sql_text)
    df_all = pd.DataFrame(list(map(dict, results.fetchall())))
    fig = go.Figure(layout_yaxis_range=[0, 1])

    if len(df_all) > 0:
        for group_name, df in df_all.groupby("print_name"):
            if group_name == "YANSハッカソン運営委員":
                row = df.iloc[0]
                fig.add_hline(
                    y=row[sort_key], annotation_text=row.comment,
                    line=dict(width=1, dash="dot"), annotation_position="bottom left"
                )
            else:
                fig.add_scatter(
                    x=df.created_at.values, y=df[sort_key].values,
                    text=df.comment,
                    visible=True if (focus_id is None) or (df["user_id"].iloc[0] == focus_id) else 'legendonly',
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
        print(calc_ndcg(df_true, df_pred))
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
