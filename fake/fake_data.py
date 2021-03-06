import sqlite_utils
import random
import json 
with open("fake/words.json") as f:
    words = json.load(f)

articles, comments = [], []
comment_id = 101
for i in range(100):
    comment_count = int(i / 20) + random.randint(1,400)
    article_id = 100 + i
    article = {
            "id": article_id,
            "title": (" ".join(random.sample(words, random.randint(6, 14)))).capitalize(),
            "summary": " ".join(random.sample(words, random.randint(24, 60))),
            "link": "#" + str(i),
            "time_created": 0,
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
            "time_created": 0,
            "agrees": random.randint(1, 25),
            "disagrees": random.randint(1, 25),
            "low_qualities": 0,
            "violations": 0,
        }
        comments.append(comment)
        comment_id += 1
        
    articles.append(article)

db = sqlite_utils.Database("discourse.db")
db["articles"].upsert_all(articles, pk="id")
db["comments"].upsert_all(comments, pk="id")