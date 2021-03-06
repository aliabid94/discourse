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
            "deleted": bool
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
            "power": int,
            "edited": bool,
            "deleted": bool
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
            "time_created": int,
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
    "analytics": {
        "schema": {
            "key_type": str,
            "key_value": str,
            "visitors": int,
        },
        "pk": ("key_type", "key_value")
    },
    "suggested_articles": {
        "schema": {
            "headline": str,
            "summary": str,
            "original_text": str,
            "url": str,
            "time_created": int,
            "approved": bool,
            "used": bool,
            "scrape_source": str
        },
        "pk": "url"
    },
}

def create_tables():
    tables = db.table_names()
    for table, schema in schemas.items():
        if table not in tables:
            db[table].create(schema["schema"], pk=schema["pk"])

if __name__ == "__main__":
    create_tables()