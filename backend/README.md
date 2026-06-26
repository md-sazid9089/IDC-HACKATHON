---
title: CareerPath Backend
sdk: docker
app_port: 7860
---

# CareerPath Backend

FastAPI backend for the CareerPath AI career guidance platform.

## Features

- CV/resume parsing and analysis
- AI-powered career roadmap generation
- Interview question generation and mock interviews
- RAG-based career Q&A chatbot (ChromaDB + sentence-transformers)
- Face expression analysis
- Job recommendations

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/health/dependencies` | GET | Dependency status |
| `/docs` | GET | Interactive API docs (Swagger) |
| `/summarize-cv` | POST | Parse and analyse a PDF CV |
| `/roadmap` | POST | Generate a career roadmap |
| `/interview/questions` | POST | Generate interview questions |
| `/interview/evaluate` | POST | Evaluate interview answer |
| `/chat` | POST | RAG chatbot |
| `/face-expression` | POST | Analyse facial expression |
| `/job-recommendations` | POST | Job recommendations |

## Environment Variables (set as Space Secrets)

| Variable | Required | Description |
|----------|----------|-------------|
| `HF_TOKEN` | Yes | Hugging Face API token for inference |
| `ENABLE_LLM_GENERATOR` | No | Set `false` to disable local LLM (default: `false`) |
| `USE_LOCAL_EMBEDDINGS` | No | Set `true` to use baked-in sentence-transformers (default: `true`) |

## Local Development

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 7860
```
