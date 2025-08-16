import os
from agent_files.txt_to_sql import generate_sql_from_prompt
from db.db_connector import run_sql_query
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

# Load environment
load_dotenv()

def _init_llm():
    return ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.1
    )

def generate_sql_response(user_question: str) -> str:
    try:
        raw_sql = generate_sql_from_prompt(user_question)
        print("Generated raw SQL:\n", raw_sql)

        sql = raw_sql.strip()
        if sql.startswith("```"):
            sql = "\n".join(sql.splitlines()[1:])
        if sql.endswith("```"):
            sql = "\n".join(sql.splitlines()[:-1])
        sql = sql.strip()

        if sql.upper().startswith("-- ERROR") or not sql.lower().startswith("select"):
            return "Sorry, I couldn't generate a valid SQL query for your question."

        results = run_sql_query(sql)
        if isinstance(results, dict) and "error" in results:
            return f"Database error occurred: {results['error']}"
        if not results:
            return "Nothing found"

        rows_as_text = "\n".join([str(row) for row in results])
        llm = _init_llm()
        formatting_prompt = f"""
        You are a helpful AI financial assistant. Answer the user's question based on the SQL results below.

        User question: {user_question}

        SQL results:
        {rows_as_text}

        Provide a clear, concise answer in plain English (2–4 sentences). Do not mention SQL or technical details.
        """
        response = llm.invoke(formatting_prompt)
        return response.content.strip()

    except Exception as e:
        return f"I encountered an unexpected error: {e}"