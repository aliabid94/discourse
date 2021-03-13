import sqlite_utils
db = sqlite_utils.Database("discourse.db")

schemas = {
    "articles": {
        "schema": {
            "id": int,
            "headline": str,
            "summary": str,
            "url": str,
            "submitter": str,
            "time_created": int,
            "upvotes": int,
            "comments": int,
            "power": int,
        },
        "pk": "id"
    },
    "comments": {
        "schema": {
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
            "power": int
        },
        "pk": "id"
    },
    "meta_comments": {
        "schema": {
            "comment_id": int,
            "src_username": str,
            "dest_username": str,
            "time_created": int,
            "agreement": int,  # -1 is disagree, 1 is agree
            "low_quality": bool,
            "violation": bool
        },
        "pk": ("comment_id", "src_username")
    },
    "users": {
        "schema": {
            "username": str,
            "password_hash": str,
            "type": str,
        },
        "pk": "username"
    },
    "upvotes": {
        "schema": {
            "article_id": int,
            "username": str,
        },
        "pk": ("article_id", "username")
    },
}

def create_tables():
    tables = db.table_names()
    for table, schema in schemas.items():
        if table not in tables:
            db[table].create(schema["schema"], pk=schema["pk"])
