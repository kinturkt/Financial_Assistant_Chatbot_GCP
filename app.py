import asyncio
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import streamlit as st
import vertexai
import os
from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from vertexai.language_models import TextEmbeddingModel
from google.cloud.sql.connector import Connector
from sqlalchemy import create_engine, text
from db.db_connector import run_sql_query
from agent_files.sql_agent import generate_sql_response

load_dotenv()

print("Starting Prologis Financial Assistant Chatbot")

@st.cache_resource
def init_clients():
    # Initialize Vertex AI with ADC
    vertexai.init(
        project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("GOOGLE_CLOUD_LOCATION")
    )
    INSTANCE_CONNECTION_NAME = os.getenv("CLOUD_SQL_CONNECTION_NAME")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_NAME = os.getenv("DB_NAME", "prologis_db")

    try:
        connector = Connector()
        def getconn():
            return connector.connect(
                INSTANCE_CONNECTION_NAME,
                "pg8000",
                user=DB_USER,
                password=DB_PASSWORD,
                db=DB_NAME,
            )
        engine = create_engine(
            "postgresql+pg8000://", 
            creator=getconn,
        )
        with engine.connect() as conn:
            print(f"Database connected successfully.")

    except Exception as e:
        print(f"Cloud SQL connection failed: {e}")
        st.error(f"Database connection failed: {e}")
        st.stop()

    # Initialize embedding models
    emb_pr = TextEmbeddingModel.from_pretrained("text-embedding-004")
    emb_sec = GoogleGenerativeAIEmbeddings(
        model="gemini-embedding-001",
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.1
    )
    return engine, emb_pr, emb_sec, llm

engine, emb_pr, emb_sec, llm = init_clients()

# Search press releases (768-dim)
def search_press_releases(query, limit=20):
    embeddings = emb_pr.get_embeddings([query])
    press_qr_vec = embeddings[0].values       
    press_vec_str = '[' + ','.join(map(str, press_qr_vec)) + ']'

    sql = f"""
        SELECT source_url, title, content
        FROM press_releases
        WHERE 1 - (embedding <=> '{press_vec_str}'::vector) > 0.02
        ORDER BY embedding <=> '{press_vec_str}'::vector
        LIMIT {limit}
        """
    press_res = run_sql_query(sql)
    if isinstance(press_res, dict) and "error" in press_res:
        return [], "press_releases"
    return press_res, "press_releases"

# Search SEC reports (1536-dim)
def search_sec_reports(query, limit=10):
    sec_qr_vec = emb_sec.embed_query(
        query,
        output_dimensionality=1536,
        task_type="RETRIEVAL_DOCUMENT"
        )        
    sec_vec_str = '[' + ','.join(map(str, sec_qr_vec)) + ']'

    sql = f"""
        SELECT source_file, page, content
        FROM sec_reports
        WHERE 1 - (embedding <=> '{sec_vec_str}'::vector) > 0.02
        ORDER BY embedding <=> '{sec_vec_str}'::vector
        LIMIT {limit}
        """
    sec_results = run_sql_query(sql)
    if isinstance(sec_results, dict) and "error" in sec_results:
        return [], "sec_reports"
    return sec_results, "sec_reports"

# Search structured data
def query_structured_data(query):
    query_kt_res = generate_sql_response(query)
    return query_kt_res, "structured_data"

# GCP Vertex AI-powered intent detection
def det_int_vertexai(query):
    routing_prompt = f"""
    You are a financial data routing expert for Prologis. Analyze the user's query and determine which data source would provide the BEST answer.

    USER QUERY: "{query}"

    AVAILABLE DATA SOURCES:
    1. "press_releases" - Recent company announcements, earnings reports, quarterly results, financial highlights, liquidity updates, dividend declarations
    2. "sec_reports" - SEC filings (10-K, 10-Q), compliance documents, detailed risk factors, comprehensive financial statements  
    3. "structured_data" - Financial metrics database, property information, revenue by location, asset details, square footage

    ROUTING RULES:
    - For RECENT quarterly earnings, financial performance, liquidity updates → press_releases
    - For DETAILED regulatory filings, risk analysis, compliance → sec_reports  
    - For PROPERTY data, calculations, specific metrics → structured_data

    Your response (one word only):
    """
    try:
        response = llm.invoke(routing_prompt)
        intent = response.content.strip().lower()
        # For Recent Quarterly Data
        query_lower = query.lower()
        if any(term in query_lower for term in ['q1 2024', 'q2 2024', 'q3 2024', 'q4 2024', 'q1 2025', 'q2 2025']):
            if any(term in query_lower for term in ['earnings', 'results', 'performance', 'liquidity', 'revenue']):
                return "press_releases"
        valid_intents = ["press_releases", "sec_reports", "structured_data"]
        if intent in valid_intents:
            print(f"Routed to: {intent}")
            return intent
        else:
            return "structured_data"
    except Exception as e:
        return det_int_fb(query)

# Simple intent detection fallback using keyword matching
def det_int_fb(query):
    query_lower = query.lower()
    press_keywords = ['dividend', 'earnings', 'quarter', 'announcement', 'press', 'news', 'declared']
    sec_keywords = ['filing', 'sec', 'annual', 'report', '10-k', '10-q', 'compliance', 'risk']
    financial_keywords = ['revenue', 'profit', 'assets', 'properties', 'property', 'financial', 'income', 'square', 'metro', 'address']
    
    press_score = sum(1 for keyword in press_keywords if keyword in query_lower)
    sec_score = sum(1 for keyword in sec_keywords if keyword in query_lower)
    financial_score = sum(1 for keyword in financial_keywords if keyword in query_lower)
    
    if press_score >= sec_score and press_score >= financial_score:
        return "press_releases"
    elif sec_score >= financial_score:
        return "sec_reports"
    else:
        return "structured_data"

def generate_answer(query, context, source_type):
    if len(context.strip()) < 50:
        return f"Found limited relevant information in {source_type}. Please try rephrasing your question or check if the data exists for that time period."
    
    prompt = f"""
    You are a helpful financial assistant for Prologis. Answer the user's question based on the provided context.
    
    Context from {source_type}:
    {context}
    
    User Question: {query}
    
    IMPORTANT:
    - Only answer if the context directly relates to the question
    - If the context doesn't contain the specific information requested, say so clearly
    - Be specific about time periods and numbers when available
    - If you see unrelated content (like dividend info when asked about revenue), ignore it
    
    Provide a clear, concise answer in plain English.
    """
    try:
        response = llm.invoke(prompt)
        return response.content
    except Exception as e:
        return f"Sorry, I encountered an error: {str(e)}"

st.set_page_config(
    page_title="Prologis Financial Assistant Chatbot",
    layout="wide"
)
st.title("Prologis Financial Assistant Chatbot")
st.markdown("*Powered by GCP Vertex AI:*")
st.markdown("Ask questions about Prologis financials,properties, press releases, and SEC reports")

with st.sidebar:
    st.header("Data Sources:")
    st.markdown("""
    **A): SEC Reports:** 16 PDFs  
    **B): Structured Data:** Properties & Financials tables  
    **C): Press Releases:** Web-scraped 387 articles  
    """)
    st.markdown("---")
    st.markdown("**AI Technology:**")
    st.markdown("""
    - **Query Routing:** GCP Vertex AI
    - **Embeddings:** Google Generative AI and Vertex AI
    - **LLM:** Gemini 1.5 Flash
    - **Database:** Cloud SQL with pgvector
    """)

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask about Prologis..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing with Vertex AI..."):
            intent = det_int_vertexai(prompt)
            if intent == "press_releases":
                results, source = search_press_releases(prompt)
                if results:
                    context = "\n\n".join([r.get('content', '') for r in results if isinstance(r, dict) and r.get('content')])
                    answer = generate_answer(prompt, context, "Press Releases")
                else:
                    answer = "No relevant press releases found."

            elif intent == "sec_reports":
                results, source = search_sec_reports(prompt)
                if results:
                    context = "\n\n".join([str(r.get('content', '')) for r in results])
                    answer = generate_answer(prompt, context, "SEC Reports")
                else:
                    answer = "No relevant SEC reports found."

            else:
                answer, source = query_structured_data(prompt)

            st.markdown(answer)
            st.caption(f"Vertex AI Routing: {intent}")
            st.session_state.messages.append({
                "role": "assistant", 
                "content": answer
            })