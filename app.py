from flask import Flask, request, render_template, send_from_directory, redirect, abort, jsonify
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from flask_cachebuster import CacheBuster
import os
import hashlib
import sqlite_utils
import tables
import scrape_suggestions
import time
from urllib.parse import urlparse
import random
import json

ARTICLES_PER_PAGE = 30
with open("fake/users.json") as f:
    PSEUDO_USERS = json.load(f)

app = Flask(__name__)
app.secret_key = 'secret'
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)
cache_buster = CacheBuster(
    config={'extensions': ['.js', '.css'], 'hash_size': 5})
cache_buster.init_app(app)


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

DEFAULT_POWER = 60

def get_power(now, time_created, upvotes, comments):
    time_diff_in_hours = max(1, (now - time_created) / 3600)
    return round(10 * (upvotes + comments + 6) / time_diff_in_hours ** 0.75)


def update_powers():
    now = int(time.time())
    db = sqlite_utils.Database("discourse.db")
    articles_table = db["articles"]
    articles = articles_table.rows_where(select="id, time_created, upvotes, comments",
                                         where="power is null or power > 0")
    articles = list(articles)
    for article in articles:
        article["power"] = get_power(
            now, article["time_created"], article["upvotes"], article["comments"])
    articles_table.upsert_all(articles, pk="id")


@app.route('/')
def homepage():
    p = int(request.args.get("p", 1))
    db = sqlite_utils.Database("discourse.db")
    offset = (p - 1) * ARTICLES_PER_PAGE
    top_articles = db["articles"].rows_where(
        where="deleted is null",
        order_by="power desc, time_created desc",
        limit=ARTICLES_PER_PAGE, offset=offset)
    articles = list(top_articles)
    article_ids = [article["id"] for article in articles]
    return render_template("index.html", articles=articles, article_ids=article_ids,
                           p=p, offset=offset,
                           current_user=current_user, is_admin=is_admin(
                               current_user),
                           now=time.time(), get_age=get_age, get_host=get_host)


@app.route('/<int:article_id>')
def article(article_id):
    db = sqlite_utils.Database("discourse.db")
    article = db["articles"].get(article_id)
    comments = db["comments"].rows_where(
        "article_id = ?", [article_id], order_by="id asc")
    comments = list(comments)
    now = time.time()
    for comment in comments:
        comment["age"] = get_age(now, comment["time_created"])
    return render_template("article.html", article=article, comments=comments,
                           current_user=current_user, is_admin=is_admin(current_user), host=get_host(article["url"]))


def create_how_article():
    db = sqlite_utils.Database("discourse.db")
    articles_table = db["articles"]
    try:
        article = articles_table.get(0)
    except sqlite_utils.db.NotFoundError:
        db["articles"].insert({
            "id": 0,
            "headline": "How Discourse works.",
            "summary": "Discourse is a news forum built to host discussion between many political viewpoints. Most discussion forums are organized using a 'like' or 'upvote/downvote' system where comments with the most votes rise to the top. This system causes the most popular viewpoints to drown out all others. Discourse instead uses an 'agree/disagree' system where users identify which comments they agree with. With this data, Discourse can identify comments that represent distinct viewpoints and organize the comments on each page to present many diverse viewpoints at the top of the discussion. \n \nDiscourse relies on the community to create a welcoming environment for open discussion. When replying with disagreement, assume good faith and the most charitable interpretation of the comment you respond to. Keep the temperature low! Do not criticize or dismiss a commentor or a political group - instead, explain why you disagree with the logic of the comment or perspective itself. Discourse is a moderated community that relies on its users for self-moderation and quality discussion.",
            "url": "#",
            "submitter": "mod",
            "time_created": 0,
            "upvotes": 0,
            "comments": 0,
        }, pk="id")


@app.route('/how')
def how():
    return article(0)


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico')


def is_admin(user):
    return user.is_authenticated and user.type in ("pseudo", "mod")


class User:
    def __init__(self, id):
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False
        self.id = id
        db = sqlite_utils.Database("discourse.db")
        try:
            user = db["users"].get(id)
            self.type = user["type"]
        except sqlite_utils.db.NotFoundError:
            self.type = None

    def get_id(self):
        return self.id


@app.route('/submit', methods=["GET", "POST", "DELETE"])
def submit():
    def url_format(url):
        if not url.startswith("http://") and (not url.startswith("https://")):
            url = "http://" + url
        return url
    if request.method == "GET":
        article_id = request.args.get("id")
        article = None
        suggestions = []
        if article_id is not None:
            db = sqlite_utils.Database("discourse.db")
            articles_table = db["articles"]
            article = articles_table.get(article_id)
        elif is_admin(current_user):
            SUGGESTIONS_TO_QUERY = 100
            db = sqlite_utils.Database("discourse.db")
            suggested_articles_table = db["suggested_articles"]
            top_articles = suggested_articles_table.rows_where(
                "used != 1 AND approved = 1", order_by="time_created desc", limit=SUGGESTIONS_TO_QUERY)
            suggestions = list(top_articles)
        return render_template("submit.html", current_user=current_user,
                               suggestions=suggestions,
                               article=article,
                               now=time.time(), get_age=get_age, get_host=get_host)
    elif request.method == "POST":
        db = sqlite_utils.Database("discourse.db")
        articles_table = db["articles"]
        article_id = request.form.get("id")
        if article_id is None:
            article = {
                "headline": request.form.get("headline"),
                "summary": request.form.get("summary"),
                "url": url_format(request.form.get("url")),
                "submitter": current_user.id,
                "time_created": int(time.time()),
                "upvotes": 0,
                "comments": 0,
                "power": DEFAULT_POWER
            }
            if current_user.type == "pseudo":
                article["submitter"] = random.choice(PSEUDO_USERS)
            articles_table.insert(article)
            suggested_articles_table = db["suggested_articles"]
            if suggested_articles_table.get(article["url"]):
                suggested_articles_table.update(article["url"], {"used": 1})
            return redirect("/" + str(articles_table.last_pk))
        else:
            article_id = int(article_id)
            article = articles_table.get(article_id)
            assert current_user.id == article["submitter"] or is_admin(
                current_user)
            article["headline"] = request.form.get("headline")
            article["summary"] = request.form.get("summary")
            article["url"] = url_format(request.form.get("url"))
            articles_table.upsert(article, pk="id")
            return redirect("/" + str(article_id))
    elif request.method == "DELETE":
        assert is_admin(current_user)
        db = sqlite_utils.Database("discourse.db")
        articles_table = db["articles"]
        article_id = request.get_json(force=True).get("id")
        article = articles_table.get(article_id)
        article["deleted"] = 1
        articles_table.upsert(article, pk="id")
        return {"success": True}


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
    users_table = db["users"]
    if username in PSEUDO_USERS:
        return abort(403, "User exists")
    try:
        user = users_table.get(username)
        return abort(403, "User exists")
    except sqlite_utils.db.NotFoundError:
        pass
    now = int(time.time())
    user = {"username": username,
            "password_hash": password_hash, "time_created": now}
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


@app.route('/comment', methods=["POST", "PATCH", "DELETE"])
@login_required
def submit_comment():
    data = request.get_json(force=True)
    db = sqlite_utils.Database("discourse.db")
    if request.method == "POST":
        data.update({
            "author": current_user.id,
            "time_created": int(time.time()),
            "agrees": 0,
            "disagrees": 0,
            "low_qualities": 0,
            "violations": 0,
        })
        if current_user.type == "pseudo":
            data["author"] = random.choice(PSEUDO_USERS)
        articles_table = db["articles"]
        comments_table = db["comments"]
        comments_table.insert(data)
        article = articles_table.get(data["article_id"])
        article["comments"] += 1
        articles_table.upsert(article, pk="id")
        return {"comment_id": comments_table.last_pk}
    elif request.method == "PATCH":
        comments_table = db["comments"]
        comment = comments_table.get(data["id"])
        assert comment["author"] == current_user.id or is_admin(current_user)
        comment["content"] = data["content"]
        now = int(time.time())
        if now - comment["time_created"] < 5 * 60:
            comment["edited"] = True
        comments_table.upsert(comment, pk="id")
        return {"success": True}
    elif request.method == "DELETE":
        comments_table = db["comments"]
        comment = comments_table.get(data["id"])
        if current_user.type not in ("pseudo", "mod"):
            assert comment["author"] == current_user.id
        comment["deleted"] = True
        comments_table.upsert(comment, pk="id")
        return {"success": True}


@app.route('/upvote', methods=["GET", "POST"])
@login_required
def upvote():
    db = sqlite_utils.Database("discourse.db")
    upvotes_table = db["upvotes"]
    if request.method == "GET":
        article_ids = request.args.getlist("article_ids")
        upvotes = upvotes_table.rows_where(
            "username = ? and article_id in (" +
            ", ".join(["?"] * len(article_ids)) + ")",
            [current_user.id] + article_ids)
        return jsonify([item["article_id"] for item in upvotes])
    elif request.method == "POST":
        data = request.get_json(force=True)
        article_id = int(data["article_id"])
        if current_user.type != "pseudo":
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
    if current_user.type == "pseudo":
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


@app.route('/suggestions', methods=["GET", "POST"])
@login_required
def suggestions():
    assert current_user.type == "mod"
    if request.method == "GET":
        approval = int(request.args.get("approval", 0))
        db = sqlite_utils.Database("discourse.db")
        suggested_articles_table = db["suggested_articles"]
        SUGGESTIONS_TO_QUERY = 50
        top_articles = suggested_articles_table.rows_where(
            "used != 1 AND approved = ?", (approval,),
            order_by="time_created desc", limit=SUGGESTIONS_TO_QUERY)
        suggestions = list(top_articles)
        return render_template("suggestions.html", current_user=current_user,
                               suggestions=suggestions,
                               now=time.time(), get_age=get_age, get_host=get_host)
    elif request.method == "POST":
        data = request.get_json(force=True)
        db = sqlite_utils.Database("discourse.db")
        suggestions_table = db["suggested_articles"]
        suggestions_table.upsert(data, pk="url")
        return {"success": True}


@app.route('/scrape_suggestions', methods=["GET"])
def scrape_suggestions_endpt():
    source = request.args.get("source")
    success, fail = scrape_suggestions.scrape_all(source_name=source)
    return {"success": success, "fail": fail}


if __name__ == "__main__":
    tables.create_tables()
    create_how_article()
    update_powers()
    app.run(port=5099, debug=True)
