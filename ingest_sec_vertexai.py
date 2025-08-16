import os
import time
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from google.cloud.sql.connector import Connector
from sqlalchemy import create_engine, text

if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
    del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    print("Using Application Default Credentials")

load_dotenv()
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "ai-financial-agent-467005")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
INSTANCE_CONNECTION_NAME = os.getenv("CLOUD_SQL_CONNECTION_NAME")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "prologis_db")

if not all([INSTANCE_CONNECTION_NAME, DB_PASSWORD, GOOGLE_API_KEY]):
    raise ValueError("Missing CLOUD_SQL_CONNECTION_NAME, DB_PASSWORD, or GOOGLE_API_KEY in .env")

# Using Google Generative AI Embeddings
embedder = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001",            # Model with 1536 Dimsensions
    google_api_key=GOOGLE_API_KEY
)

# Debug Statments
# test_vectors = embedder.embed_documents(["test"], 
#                                         output_dimensionality=1536, 
#                                         task_type="RETRIEVAL_DOCUMENT")
# print(f"Using GoogleGenerativeAIEmbeddings with {len(test_vectors[0])} dimensions")

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

load_pdf_kt = PyPDFLoader
splitter_txt = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

def clean_text(text: str) -> str:
    return text.replace("\x00", " ").strip()

def process_pdf(path: str) -> list[dict]:
    docs = load_pdf_kt(path).load()
    chunks = []
    for doc in docs:
        for idx, chunk in enumerate(splitter_txt.split_documents([doc])):
            text = clean_text(chunk.page_content)
            if not text:
                continue
            chunks.append({
                "source_file": os.path.basename(path),
                "page": doc.metadata.get("page"),
                "chunk_index": idx,
                "content": text
            })
    return chunks

DATA_DIR = "data"     # The directory containing SEC PDF
my_rec = []

pdf_files = [f for f in os.listdir(DATA_DIR) if f.lower().endswith(".pdf")]
total_files = len(pdf_files)

for file_idx, fname in enumerate(pdf_files, 1):
    pdf_path = os.path.join(DATA_DIR, fname)
    print(f"Processing {fname} ({file_idx}/{total_files})")
    chunks = process_pdf(pdf_path)
    texts = [c["content"] for c in chunks]

    # Generate embeddings with Google GenAI
    vectors = embedder.embed_documents(
        texts,
        output_dimensionality=1536,
        task_type="RETRIEVAL_DOCUMENT"
    )

    for c, emb in zip(chunks, vectors):
        if emb:
            my_rec.append({**c, "embedding": emb})

BATCH_SIZE = 20
insert_sql = """
            INSERT INTO sec_reports (source_file, page, chunk_index, content, embedding)
            VALUES (:source_file, :page, :chunk_index, :content, :embedding)
            """
successful_batches = 0
for i in range(0, len(my_rec), BATCH_SIZE):
    batch = my_rec[i:i + BATCH_SIZE]
    try:
        with engine.begin() as conn:
            for record in batch:
                conn.execute(text(insert_sql), {
                    "source_file": record["source_file"],
                    "page": record["page"],
                    "chunk_index": record["chunk_index"],
                    "content": record["content"],
                    "embedding": str(record["embedding"])
                })
        successful_batches += 1
    except Exception as e:
        print(f"  Error with batch {i//BATCH_SIZE + 1}: {e}")
    time.sleep(0.2)

with engine.connect() as conn:
    result = conn.execute(text("SELECT COUNT(*) FROM sec_reports"))
    count = result.scalar()
    print(f"Final count: {count} records in database")

connector.close()
print("SEC PDFs Ingestion completed!")