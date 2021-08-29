from bs4 import BeautifulSoup
import urllib.request
import sqlite_utils
import time
import json
import random
from sqlite_utils.db import DEFAULT

from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer as Summarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words

with open("fake/users.json") as f:
    PSEUDO_USERS = json.load(f)
DEFAULT_POWER = 60

def summarize(text):
    LANGUAGE = "english"
    SENTENCES_COUNT = 4
    parser = PlaintextParser.from_string(text, Tokenizer(LANGUAGE))
    stemmer = Stemmer(LANGUAGE)
    summarizer = Summarizer(stemmer)
    summarizer.stop_words = get_stop_words(LANGUAGE)
    return " ".join([str(sentence) for sentence in
                     summarizer(parser.document, SENTENCES_COUNT)])


def scrape_all(auto_submit=True, source_name=None):
    sources = ScrapeSource.__subclasses__()
    if source_name is not None:
        sources = [source for source in sources if source.__name__ == source_name]
        assert len(sources) == 1
    db = sqlite_utils.Database("discourse.db")
    articles_table = db["articles"]
    suggested_articles_table = db["suggested_articles"]
    success, fail = 0, 0
    for source in sources:
        try:
            count = 0
            for link in source.generate_links():
                if count >= source.LIMIT:
                    break
                # print(f"trying scrape with {source.__name__}, limit {source.LIMIT}")
                existing_articles = articles_table.rows_where(
                    "url = ?", [link])
                existing_suggested = suggested_articles_table.rows_where(
                    "url = ?", [link])
                if len(list(existing_articles)) > 0 or len(list(existing_suggested)) > 0:
                    # print(link, "exists, skipping..")
                    continue
                try:
                    headline, original_text = source.scrape(link)
                except Exception as e:
                    print(f"failed scrape with {source.__name__}, {link}: \n{str(e)}")
                    fail += 1
                    continue
                summary = summarize(original_text)
                if auto_submit:
                    articles_table.insert({
                        "headline": headline,
                        "summary": summary,
                        "url": link,
                        "submitter": random.choice(PSEUDO_USERS),
                        "time_created": int(time.time()) - random.randint(0, 3 * 60 * 60),
                        "upvotes": 1,
                        "comments": 0,
                        "power": DEFAULT_POWER
                    })
                else:
                    suggested_articles_table.insert({
                        "headline": headline,
                        "summary": summary,
                        "original_text": original_text,
                        "url": link,
                        "time_created": int(time.time()),
                        "used": 0,
                        "approved": 0,
                        "scrape_source": source.__name__
                    })
                success += 1
                count += 1
        except Exception as e:
            print(f"failed generation with {source.__name__}")
            fail += 1
    return success, fail


class ScrapeSource:
    @staticmethod
    def generate_links():
        raise NotImplementedError

    @staticmethod
    def scrape():
        raise NotImplementedError


class CNN(ScrapeSource):
    LIMIT = 3
    @staticmethod
    def generate_links():
        source = urllib.request.urlopen('https://lite.cnn.com/en', timeout=5).read()
        soup = BeautifulSoup(source, features="html.parser")
        for url in soup.find_all("a"):
            href = url.get("href")
            if href.startswith("/en/article"):
                yield "https://lite.cnn.com" + href

    @staticmethod
    def scrape(url):
        source = urllib.request.urlopen(url, timeout=5).read()
        soup = BeautifulSoup(source, features="html.parser")
        headline = soup.find("h2").text
        article_ps = soup.find(id="byline").parent.find_all("p")
        text = []
        for article_p in article_ps:
            if article_p.get("id") is None:
                text.append(article_p.text)
        return headline, " ".join(text)


class NPR(ScrapeSource):
    LIMIT = 3
    @staticmethod
    def generate_links():
        source = urllib.request.urlopen('https://text.npr.org/', timeout=5).read()
        soup = BeautifulSoup(source, features="html.parser")
        for url in soup.select_one(".topic-container").find_all("a"):
            href = url.get("href")
            yield "https://text.npr.org" + href

    @staticmethod
    def scrape(url):
        source = urllib.request.urlopen(url, timeout=5).read()
        soup = BeautifulSoup(source, features="html.parser")
        text = []
        headline = soup.find("h1").text
        article_ps = soup.select_one(".paragraphs-container").find_all("p")
        text = [article_p.text for article_p in article_ps]
        return headline, " ".join(text)

class Politico(ScrapeSource):
    LIMIT = 3
    @staticmethod
    def generate_links():
        source = urllib.request.urlopen('https://www.politico.com/', timeout=5).read()
        soup = BeautifulSoup(source, features="html.parser")
        for url in soup.select_one(".js-quick-pops .media-item-list").find_all("a"):
            href = url.get("href")
            yield href

    @staticmethod
    def scrape(url):
        source = urllib.request.urlopen(url, timeout=5).read()
        soup = BeautifulSoup(source, features="html.parser")
        text = []
        headline = soup.select_one("h2.headline").text
        article_ps = soup.select(".story-text p")
        text = [article_p.text for article_p in article_ps]
        return headline, " ".join(text)

class Reuters(ScrapeSource):
    LIMIT = 3
    @staticmethod
    def generate_links():
        source = urllib.request.urlopen('https://www.reuters.com/', timeout=5).read()
        soup = BeautifulSoup(source, features="html.parser")
        for url in soup.find_all("a"):
            href = url.get("href")
            if (href.startswith("/world/") or href.startswith("/business/")) and len(href) > 15:
                yield 'https://www.reuters.com' + href

    @staticmethod
    def scrape(url):
        source = urllib.request.urlopen(url, timeout=5).read()
        soup = BeautifulSoup(source, features="html.parser")
        text = []
        headline = soup.select_one("header h1").text
        article_ps = soup.select("article p")
        text = [article_p.text for article_p in article_ps if "Reuters" not in article_p.text]
        return headline, " ".join(text)

