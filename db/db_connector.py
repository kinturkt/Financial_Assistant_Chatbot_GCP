import os
from dotenv import load_dotenv
from google.cloud.sql.connector import Connector
# Load the .env variables
load_dotenv()

# Cloud SQL connection parameters
INSTANCE_CONNECTION_NAME = os.getenv("CLOUD_SQL_CONNECTION_NAME")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "prologis_db")

if not all([INSTANCE_CONNECTION_NAME, DB_PASSWORD]):
    raise RuntimeError(
        "Please set CLOUD_SQL_CONNECTION_NAME and DB_PASSWORD in your .env file."
    )

def run_sql_query(query: str):
    try:
        connector = Connector()
        conn = connector.connect(
            INSTANCE_CONNECTION_NAME,
            "pg8000",
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
            enable_iam_auth=False,
            timeout=30
        )
        
        with conn:
            cursor = conn.cursor()
            cursor.execute(query)
            
            if cursor.description:
                cols = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                # Return as list of dictionaries
                return [dict(zip(cols, row)) for row in rows]
            else:
                return {"status": "query executed successfully"}
                
    except Exception as e:
        return {"error": str(e)}
    finally:
        connector.close()

# Testing the connection
def test_connection():
    try:
        result = run_sql_query("SELECT 1 as test_value")
        if isinstance(result, dict) and "error" in result:
            return False, result["error"]
        return True, "Connection successful"
    except Exception as e:
        return False, str(e)

if __name__ == "__main__":
    success, message = test_connection()
    if success:
        print(f"Database connection test passed: {message}")
    else:
        print(f"Database connection test failed: {message}")