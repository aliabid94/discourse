import sqlite_utils
import random
import json
import time
import hashlib

username, password = "aliabid94", "yoohoo00"

with open("fake/words.json") as f:
    words = json.load(f)
news_sites = ["cnn.com", "time.com", "foxnews.com", "abc.com", "reuters.com", "aljazeera.com", "theguardian.net"]
news_starter = ["https://", "http://", "http://www."]

now = int(time.time())
articles, comments, upvotes = [], [], []
comment_id = 101
for i in range(100):
    comment_count = int(i / 20) + random.randint(1,400)
    article_id = 100 + i
    article = {
            "id": article_id,
            "headline": (" ".join(random.sample(words, random.randint(6, 14)))).capitalize(),
            "summary": " ".join(random.sample(words, random.randint(24, 60))),
            "submitter": random.choice(words),
            "url": random.choice(news_starter) + random.choice(news_sites) + "/" + str(random.randint(1000,  9999)),
            "time_created": now - random.randint(30, 60 * 60  * 24 * 5),
            "upvotes": int(i / 10),
            "comments": comment_count,
        }
    for j in range(comment_count):
        parent_id = None
        if j > 0 and random.random() < 0.6:
            parent_id = comment_id - random.randint(1, j)
        comment = {
            "id": comment_id,
            "content": " ".join(random.sample(words, random.randint(5,50))),
            "parent_id": parent_id,
            "author": random.choice(words),
            "article_id": article_id,
            "time_created": now - random.randint(30, 60 * 60  * 24 * 5),
            "agrees": random.randint(1, 25),
            "disagrees": random.randint(1, 25),
            "low_qualities": 0,
            "violations": 0,
        }
        comments.append(comment)
        comment_id += 1     
    if random.random() < 0.3:
        upvotes.append({
            "article_id": article_id,
            "username": username,
        })
    articles.append(article)

db = sqlite_utils.Database("discourse.db")
user = {
    "username": username,
    "password_hash": hashlib.md5(password.encode()).hexdigest()
}
db["users"].upsert_all([user], pk="username")
db["articles"].upsert_all(articles, pk="id")
db["comments"].upsert_all(comments, pk="id")
db["upvotes"].insert_all(upvotes)
