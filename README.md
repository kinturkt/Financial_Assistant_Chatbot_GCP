# Prologis Financial Assistant Chatbot

AI-powered financial assistant for Prologis data analysis using Vertex AI and Cloud SQL.

## Live URL:

https://prologis-assistant-98045253150.us-central1.run.app/

## Architecture

The system processes three data sources:

1. **PDF Documents and Press Releases** - Ingested through text chunking and converted to embeddings using Vertex AI, stored in Cloud SQL with pgvector extension
2. **Structured Data Tables** - Imported directly into Cloud SQL, accessed via SQL Agent that generates queries using Gemini LLM
3. **User Query Processing** - Intent detection routes queries to appropriate data source, vector search retrieves relevant information, final response generated using Gemini 1.5 Flash

Also, refer to the Flowchart.jpeg image for the flow of the project

## Data Flow

User Query → Intent Detection (Vertex AI) → Vector Search (Cloud SQL) → Response Generation (Gemini 1.5 Flash) → Chatbot Output

## Setup and Run Locally

### Prerequisites
- Python 3.9+
- Google Cloud Account with Cloud SQL and Vertex AI enabled

### Installation
```bash
git clone https://github.com/kinturkt/Prologis_Financial_Assistant_Chatbot.git
cd Prologis_Financial_Assistant_Chatbot
pip install -r requirements.txt
```

### Configuration
1. Create `.env` file:
```
CLOUD_SQL_CONNECTION_NAME=your-project:region:instance
DB_USER=postgres
DB_PASSWORD=your-password
DB_NAME=prologis_db
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_API_KEY=your-api-key
```

2. Set up service account credentials:
```bash
export GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account-key.json
```

### Run Application
```bash
streamlit run app.py
```

## Cloud Deployment

### Build and Deploy to Google Cloud Run
```bash
# Build container
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/prologis-assistant

# Deploy to Cloud Run
gcloud run deploy prologis-assistant --image gcr.io/YOUR_PROJECT_ID/prologis-assistant --platform managed --region us-central1 --allow-unauthenticated --memory=2Gi --set-env-vars="CLOUD_SQL_CONNECTION_NAME=your-connection-name,DB_USER=postgres,DB_PASSWORD=your-password,DB_NAME=prologis_db,GOOGLE_CLOUD_PROJECT=your-project-id,GOOGLE_CLOUD_LOCATION=us-central1,GOOGLE_API_KEY=your-api-key"
```

### Data Ingestion
```bash
# Ingest SEC reports
python ingest_vector_store.py

# Ingest press releases
python ingest_all_pages_press_releases.py
```

## Requirements
See `requirements.txt` for complete dependencies.
