from flask import Flask, request, render_template, send_from_directory, redirect, abort, jsonify
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
import os
import hashlib
import sqlite_utils
import tables
import time
from urllib.parse import urlparse

ARTICLES_PER_PAGE = 25

app = Flask(__name__)
app.secret_key = 'secret'
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

def get_age(now, timestamp):
    diff = now - timestamp
    if diff < 60:
        return "just now"
    elif diff < 60 * 60:
        unit = "minute"
        diff /= 60
    elif diff < 60 * 60 * 24:
        unit = "hour"
        diff /= (60 * 60)
    else:
        unit = "day"
        diff /= (60 * 60 * 24)
    diff = int(diff)
    if diff != 1:
        unit += "s"
    return str(int(diff)) + " " + unit + " ago"

def get_host(url):
    url = urlparse(url).netloc
    if url.startswith("www."):
        url = url[4:]
    return url

@app.route('/')
def homepage():
    p = int(request.args.get("p", 1))
    db = sqlite_utils.Database("discourse.db")
    offset = (p - 1) * ARTICLES_PER_PAGE
    top_articles = db["articles"].rows_where(order_by="upvotes desc",
                                             limit=ARTICLES_PER_PAGE, offset=offset)
    articles = list(top_articles)
    article_ids = [article["id"] for article in articles]
    return render_template("index.html", articles=articles, article_ids=article_ids, p=p, offset=offset,
                           current_user=current_user, now=time.time(), get_age=get_age, get_host=get_host)


@app.route('/<int:article_id>')
def article(article_id):
    db = sqlite_utils.Database("discourse.db")
    article = db["articles"].get(article_id)
    comments = db["comments"].rows_where(
        "article_id = ?", [article_id], order_by="id asc")
    comments=list(comments)
    now = time.time()
    for comment in comments:
        comment["age"] = get_age(now, comment["time_created"])
    return render_template("article.html", article=article, comments=comments, 
        current_user=current_user, host=get_host(article["url"]))


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


@app.route('/submit', methods=["GET", "POST"])
def submit():
    if request.method == "GET":
        return render_template("submit.html", current_user=current_user)
    elif request.method == "POST":
        db = sqlite_utils.Database("discourse.db")
        articles_table = db["articles"]
        url = request.form.get("url")
        if not url.startswith("http://") and (not url.startswith("https://")):
            url = "http://" + url
        article = {
            "headline": request.form.get("headline"),
            "summary": request.form.get("summary"),
            "url": url,
            "submitter": current_user.id,
            "time_created": int(time.time()),
            "upvotes": 0,
            "comments": 0,
        }
        articles_table.insert(article)
        return redirect("/" + str(articles_table.last_pk))


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
@login_required
def signup():
    username = request.form.get("username")
    password = request.form.get("password")
    password_hash = hashlib.md5(password.encode()).hexdigest()
    db = sqlite_utils.Database("discourse.db")
    users_table = db["users"]
    try:
        user = users_table.get(username)
        return abort(403, "User exists")
    except sqlite_utils.db.NotFoundError:
        pass
    user = {"username": username, "password_hash": password_hash}
    users_table.insert(user)
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
        "time_created": int(time.time()),
        "agrees": 0,
        "disagrees": 0,
        "low_qualities": 0,
        "violations": 0,
    })
    articles_table = db["articles"]
    comments_table = db["comments"]
    comments_table.insert(data)
    article = articles_table.get(data["article_id"])
    article["comments"] += 1
    articles_table.upsert(article, pk="id")
    return {"success": True}

@app.route('/upvote', methods=["GET", "POST"])
@login_required
def upvote():
    db = sqlite_utils.Database("discourse.db")
    upvotes_table = db["upvotes"]
    if request.method == "GET":
        article_ids = request.args.getlist("article_ids")
        upvotes = upvotes_table.rows_where(
            "username = ? and article_id in (" + ", ".join(["?"] * len(article_ids)) + ")", 
            [current_user.id] + article_ids)
        return jsonify([item["article_id"] for item in upvotes])
    elif request.method == "POST":
        data = request.get_json(force=True)
        article_id = int(data["article_id"])
        try:
            upvotes_table.get((article_id, current_user.id))
            return {"success": True}
        except sqlite_utils.db.NotFoundError:
            pass
        upvotes_table.insert({
            "username": current_user.id,
            "article_id": article_id
        }, pk=("article_id", "username"))
        articles_table = db["articles"]
        article = articles_table.get(article_id)
        article["upvotes"] += 1
        articles_table.upsert(article, pk="id")
        return {"success": True}


@app.route('/meta_comment', methods=["POST"])
@login_required
def submit_meta_comment():
    data = request.get_json(force=True)
    agreement = data.get("agreement")
    assert agreement in [-1, 1, None]
    db = sqlite_utils.Database("discourse.db")
    comments_table = db["comments"]
    meta_comments_table = db["meta_comments"]
    comment = comments_table.get(data["comment_id"])
    try:
        existing_data = meta_comments_table.get(
            (data["comment_id"], current_user.id))
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
    comments_table.upsert(comment, pk="id")
    data["src_username"] = current_user.id
    data["dest_username"] = comment["author"]
    meta_comments_table.upsert(data, pk=("comment_id", "src_username"))
    return {"success": True}


if __name__ == "__main__":
    tables.create_tables()
    app.run(port=5099)
