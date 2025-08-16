Live URL: https://prologis-assistant-98045253150.us-central1.run.app






Commands for GCP Deployment:

Run below 2 commands on your project directory root in CMD

# 1st Command - Build and push
gcloud builds submit --tag gcr.io/ai-financial-agent-467005/prologis-assistant

# 2nd Command - Deploy
gcloud run deploy prologis-assistant --image gcr.io/ai-financial-agent-467005/prologis-assistant --platform managed --region us-central1 --allow-unauthenticated --memory=2Gi

# To check the logs
gcloud run logs read --service=prologis-assistant --region=us-central1