import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

def generate_sql_from_prompt(user_question: str) -> str:
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0.1
        )

        prompt = f"""
            You are a PostgreSQL expert. Generate ONLY the raw SQL (no explanation or markdown).

            Schema public.properties(
            property_id INTEGER,
            property_name TEXT,
            property_address TEXT,
            metro_area TEXT,
            square_foot_sf NUMERIC,
            property_type TEXT
            )

            Schema public.financials(
            id INTEGER,
            property_id INTEGER,
            year INTEGER,
            revenue NUMERIC,
            net_income_usd NUMERIC
            )

            IMPORTANT: Use these EXACT column names (no quotes needed):
            - square_foot_sf (not "Square_Foot (SF)")
            - net_income_usd (not "Net_Income ($)")
            - property_name, property_address, metro_area, property_type
            - revenue, year, property_id

            Example:
            -- question: List the top 5 properties by revenue in 2023
            SELECT p.property_name, f.revenue
            FROM public.properties AS p
            JOIN public.financials AS f
                ON p.property_id = f.property_id
            WHERE f.year = 2023
            ORDER BY f.revenue DESC
            LIMIT 5;

            Example:
            -- question: How many properties do we have?
            SELECT COUNT(*) as total_properties
            FROM public.properties;

            Example:
            -- question: Show me properties in Texas
            SELECT property_name, property_address, square_foot_sf
            FROM public.properties
            WHERE property_address LIKE '%Texas%' OR metro_area LIKE '%Texas%';

            Now, generate SQL for the following question.
            -- question: {user_question}
            -- SQL:
            """

        response = llm.invoke(prompt)
        sql = response.content.strip()
        if sql.startswith("```"):
            sql = "\n".join(sql.splitlines()[1:])
        if sql.endswith("```"):
            sql = "\n".join(sql.splitlines()[:-1])
        sql = sql.strip()
        
        return sql

    except Exception as e:
        err = f"ERROR: {str(e)}"
        return err