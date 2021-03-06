from flask import Flask, request, render_template, send_from_directory, redirect, abort
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
import os
import hashlib
import sqlite_utils

ARTICLES_PER_PAGE = 25

app = Flask(__name__)
app.secret_key = 'secret'
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)
db = sqlite_utils.Database("discourse.db")


def create_tables():
    tables = db.table_names()
    if "articles" not in tables:
        db["articles"].create({
            "id": int,
            "title": str,
            "summary": str,
            "link": str,
            "time_created": int,
            "upvotes": int,
            "comments": int,
        }, pk="id")
    if "comments" not in tables:
        db["comments"].create({
            "id": int,
            "content": str,
            "parent_id": int,
            "author": str,
            "article_id": int,
            "time_created": int,
            "agrees": int,
            "disagrees": int,
            "low_qualities": int,
            "violations": int,
        }, pk="id")
    if "meta_comments" not in tables:
        db["meta_comments"].create({
            "comment_id": int,
            "src_user": str,
            "dest_user": str,
            "time_created": int,
            "agreement": int,  # -1 is disagree, 1 is agree
            "low_quality": bool,
            "violation": bool
        }, pk=("comment_id", "src_user"))
    if "users" not in tables:
        db["users"].create({
            "username": str,
            "password_hash": str,
        }, pk="username")


@app.route('/')
def homepage():
    p = int(request.args.get("p", 1))
    db = sqlite_utils.Database("discourse.db")
    offset = (p - 1) * ARTICLES_PER_PAGE
    top_articles = db["articles"].rows_where(order_by="upvotes desc",
                                             limit=ARTICLES_PER_PAGE, offset=offset)
    return render_template("index.html", articles=list(top_articles), p=p, offset=offset,
                           current_user=current_user)


@app.route('/<int:article_id>')
def article(article_id):
    db = sqlite_utils.Database("discourse.db")
    article = db["articles"].get(article_id)
    comments = db["comments"].rows_where(
        "article_id = ?", [article_id], order_by="id asc")
    return render_template("article.html", article=article, comments=list(comments), current_user=current_user)


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico')


class User:
    def __init__(self, id):
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False
        self.id = id

    def get_id(self):
        return self.id


@app.route('/login', methods=["GET", "POST"])
def login():
    redirect_url = request.args.get("redirect", "/")
    if request.method == "GET":
        return render_template("login.html", current_user=current_user, redirect=redirect_url)
    elif request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        password_hash = hashlib.md5(password.encode()).hexdigest()
        db = sqlite_utils.Database("discourse.db")
        try:
            user = db["users"].get(username)
        except sqlite_utils.db.NotFoundError:
            return abort(401)
        if password_hash == user["password_hash"]:
            login_user(User(username))
            return redirect(redirect_url)
        else:
            return abort(401)


@app.route('/signup', methods=["POST"])
def signup():
    username = request.form.get("username")
    password = request.form.get("password")
    password_hash = hashlib.md5(password.encode()).hexdigest()
    db = sqlite_utils.Database("discourse.db")
    try:
        user = db["users"].get(username)
        return abort(403, "User exists")
    except sqlite_utils.db.NotFoundError:
        pass
    user = {"username": username, "password_hash": password_hash}
    db["users"].insert(user)
    login_user(User(username))
    return redirect("/")


@login_manager.user_loader
def load_user(_id):
    return User(_id)


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    logout_user()
    redirect_url = request.args.get("redirect", "/")
    return redirect(redirect_url)


@app.route('/comment', methods=["POST"])
@login_required
def submit_comment():
    data = request.get_json(force=True)
    db = sqlite_utils.Database("discourse.db")
    data.update({
        "author": current_user.id,
        "agrees": 0,
        "disagrees": 0,
        "low_qualities": 0,
        "violations": 0,
    })
    db["comments"].insert(data)
    return {"success": True}


@app.route('/meta_comment', methods=["POST"])
@login_required
def submit_meta_comment():
    data = request.get_json(force=True)
    agreement = data.get("agreement")
    assert agreement in [-1, 1, None]
    db = sqlite_utils.Database("discourse.db")
    comment = db["comments"].get(data["comment_id"])
    try:
        existing_data = db["meta_comments"].get(
            (data["comment_id"], "user_id"))
    except sqlite_utils.db.NotFoundError:
        existing_data = {}
    if agreement is not None:
        if existing_data.get("agreement") == 1:
            comment["agrees"] -= 1
        elif existing_data.get("agreement") == -1:
            comment["disagrees"] -= 1
        if agreement == 1:
            comment["agrees"] += 1
        elif agreement == -1:
            comment["disagrees"] += 1
    if not existing_data.get("low_quality") and data.get("low_quality"):
        comment["low_qualities"] += 1
    if not existing_data.get("violation") and data.get("violation"):
        comment["violations"] += 1
    db["comments"].upsert(comment, pk="id")
    data["src_user"] = current_user.id
    data["dest_user"] = comment["author"]
    db["meta_comments"].upsert(data, pk=("comment_id", "src_user"))
    return {"success": True}


if __name__ == "__main__":
    create_tables()
    app.run()
