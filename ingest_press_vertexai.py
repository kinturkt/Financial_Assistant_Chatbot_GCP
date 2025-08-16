import os
import re
import requests
from datetime import datetime
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from langchain.text_splitter import RecursiveCharacterTextSplitter
import vertexai
from vertexai.language_models import TextEmbeddingModel
from google.cloud.sql.connector import Connector
from sqlalchemy import create_engine, text
import time

if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
    del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    print("Using Application Default Credentials")

load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "ai-financial-agent-467005")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
INSTANCE_CONNECTION_NAME = os.getenv("CLOUD_SQL_CONNECTION_NAME")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "prologis_db")

if not all([INSTANCE_CONNECTION_NAME, DB_PASSWORD]):
    raise ValueError("Missing .env variabebles")

# Using Vertex AI Embeddings
vertexai.init(project=PROJECT_ID, location=LOCATION)
emb = TextEmbeddingModel.from_pretrained("text-embedding-004")   # Model with 768 dimensions

connector = Connector()
def getconn():
    return connector.connect(
        INSTANCE_CONNECTION_NAME,
        "pg8000",
        user=DB_USER,
        password=DB_PASSWORD,
        db=DB_NAME
    )

engine = create_engine("postgresql+pg8000://", creator=getconn)
splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=80)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
BASE = "https://ir.prologis.com"

def fetch_all_release_urls():
    urls = set()
    for page in range(1, 21):    # Adjusted the page range to reduce load
        try:
            if page == 1:
                page_url = f"{BASE}/press-releases"
            else:
                page_url = f"{BASE}/press-releases?page={page}"
            print(f"Scraping page {page}...")
            r = requests.get(page_url, headers=HEADERS, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            links = soup.find_all("a", href=re.compile(r"/press-releases/detail/"))

            for link in links:
                href = link.get("href")
                if href:
                    full_url = href if href.startswith("http") else BASE + href
                    urls.add(full_url)
                time.sleep(0.3)
        except requests.RequestException as e:
            print(f"Error scraping page {page}: {e}")
            continue
    return sorted(urls)

def extract_text_content(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        title_elem = soup.find("h1") or soup.find("title")
        title = title_elem.get_text().strip() if title_elem else "No Title"
        date_elem = soup.find("time") 

        published_at = None
        if date_elem:
            date_text = date_elem.get("datetime") or date_elem.get_text()
            try:
                published_at = datetime.strptime(date_text.strip(), "%Y-%m-%d").date()
            except:
                published_at = datetime.now().date()
        else:
            published_at = datetime.now().date()

        content_selectors = [
            "div.content",
            "div.press-release-content", 
            "article",
            "div.main-content",
            ".content-body"
        ]
        content = ""
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                content = content_elem.get_text(separator="\n").strip()
                break
        
        if not content:
            paragraphs = soup.find_all("p")
            content = "\n".join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
        return title, published_at, content
    except requests.RequestException as e:
        print(f"Error extracting content from {url}: {e}")
        return None, None, None

def ingest_press_release(url: str, url_index: int, total_urls: int):
    print(f"Processing press release {url_index}/{total_urls}")
    title, published_at, content = extract_text_content(url)
    if not content:
        print(f"No content found, skipping")
        return
    chunks = splitter.split_text(content)

    if not chunks:
        print(f"No chunks created, skipping")
        return
    try:
        vect_list = []
        batch_size = 5
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            try:
                emb_response = emb.get_embeddings(batch)
                batch_embeddings = [emb.values for emb in emb_response]
                vect_list.extend(batch_embeddings)
                time.sleep(1)
            except Exception as e:
                vect_list.extend([[] for _ in batch])

        # Insert records into table
        insert_sql = """
                INSERT INTO press_releases (source_url, published_at, title, chunk_index, content, embedding)
                VALUES (:source_url, :published_at, :title, :chunk_index, :content, :embedding)
        """

        with engine.begin() as conn:
            for i, (chunk, vector) in enumerate(zip(chunks, vect_list)):
                if vector:
                    conn.execute(text(insert_sql), {
                        "source_url": url,
                        "published_at": published_at.isoformat() if published_at else None,
                        "title": title,
                        "chunk_index": i,
                        "content": chunk,
                        "embedding": str(vector)
                    })
    except Exception as e:
        print(f"Error ingesting {url_index}/{total_urls}: {e}")

if __name__ == "__main__":
    print("Starting press release ingestion...")

    all_urls = fetch_all_release_urls()
    print(f"Found {len(all_urls)} press release URLs")

    if not all_urls:
        print("No URLs found. Please check the website structure.")
        exit(1)

    for i, url in enumerate(all_urls, 1):
        ingest_press_release(url, i, len(all_urls))
        time.sleep(1)
    connector.close()
    print("Press release ingestion finished successfully!")