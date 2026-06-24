from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Tuple
from dotenv import load_dotenv
import json as _json
from pathlib import Path
from io import BytesIO
from PyPDF2 import PdfReader
from pydantic import BaseModel
import random


# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Configure CORS middleware FIRST (before routes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# CV analysis helpers (no LLM — pure text extraction)
# ---------------------------------------------------------------------------

def _extract_skills_from_text(text: str) -> List[str]:
    """Match known skills against raw CV text (case-insensitive)."""
    known_skills = [
        "Python", "JavaScript", "TypeScript", "React", "Vue", "Angular",
        "Next.js", "Node.js", "Express", "FastAPI", "Django", "Flask",
        "HTML", "CSS", "TailwindCSS", "SQL", "PostgreSQL", "MongoDB",
        "Redis", "Docker", "Kubernetes", "AWS", "GCP", "Azure", "Git",
        "Firebase", "GraphQL", "REST", "TensorFlow", "PyTorch", "Figma",
        "Linux", "CI/CD", "Jenkins", "Terraform", "Pandas", "NumPy",
        "scikit-learn", "Machine Learning", "Deep Learning", "NLP",
        "Communication", "Leadership", "Teamwork", "Problem Solving",
    ]
    text_lower = text.lower()
    return [s for s in known_skills if s.lower() in text_lower]


def _extract_tools_from_text(text: str) -> List[str]:
    """Alias that also catches tool/platform keywords."""
    tools = [
        "VS Code", "IntelliJ", "PyCharm", "Postman", "Jira", "Confluence",
        "Slack", "Notion", "Trello", "GitHub", "GitLab", "Bitbucket",
        "Heroku", "Vercel", "Netlify", "Nginx", "Apache", "RabbitMQ",
        "Kafka", "Elasticsearch", "Celery", "FastAPI", "Streamlit",
    ]
    text_lower = text.lower()
    return [t for t in tools if t.lower() in text_lower]


def _extract_roles_from_text(text: str) -> List[str]:
    """Detect job titles / domain keywords in CV text."""
    roles = [
        "Software Engineer", "Frontend Developer", "Backend Developer",
        "Full Stack Developer", "Data Scientist", "Data Analyst",
        "Machine Learning Engineer", "DevOps Engineer", "Site Reliability Engineer",
        "UI/UX Designer", "Product Manager", "Mobile Developer",
        "Cloud Architect", "Security Engineer", "QA Engineer",
        "Web Development", "Data Engineering", "Artificial Intelligence",
        "Healthcare", "FinTech", "E-commerce",
    ]
    text_lower = text.lower()
    return [r for r in roles if r.lower() in text_lower]


def _summarize_cv_no_llm(full_text: str) -> dict:
    """Return a structured CV dict without any LLM call."""
    return {
        "keySkills": _extract_skills_from_text(full_text),
        "toolsTechnologies": _extract_tools_from_text(full_text),
        "rolesAndDomains": _extract_roles_from_text(full_text),
    }


# ---------------------------------------------------------------------------
# Interview question generation + answer evaluation: DELETED.
# The Mock Interview component now calls Hugging Face Mistral directly from
# the browser via frontend/src/services/interviewAI.js.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Explainability Layer (additive)
# ---------------------------------------------------------------------------
# Data contract — every AI output produced by this backend MUST be wrappable
# in this envelope shape (see README + frontend ReasoningCard):
#
#   ExplainabilityEnvelope = {
#     "output": str | float,
#     "factors": list[Factor],
#     "confidence": "High" | "Medium" | "Low",
#     "basis": str,
#     "signal_types_used": list[SignalType],
#   }
#   Factor = { "label": str, "positive": bool,
#              "signal_type": SignalType, "value"?: float }
#
# Allowed SignalType (do NOT extend):
ALLOWED_SIGNAL_TYPES = {
    "rag_source", "skill_match", "weight_component",
    "profile_field", "interview_metric",
}


def _derive_confidence(factors: List[Dict[str, Any]], used_fallback: bool = False) -> str:
    """Confidence derivation rule (MUST match frontend explainability.js).

    - High:   >= 3 factors AND at least one rag_source or skill_match AND
              no retrieval fallback was used.
    - Medium: 1-2 factors, OR retrieval fallback used, OR only
              weight_component signals present.
    - Low:    0 factors, OR all signals are profile_field only, OR
              keyword fallback was used.
    """
    if not factors:
        return "Low"
    types = {f.get("signal_type") for f in factors if f and f.get("signal_type")}
    if types == {"profile_field"}:
        return "Low"
    if types == {"weight_component"}:
        return "Medium"
    if used_fallback:
        return "Medium"
    if len(factors) < 3:
        return "Medium"
    if "rag_source" in types or "skill_match" in types:
        return "High"
    return "Medium"


def _build_envelope(output: Any, factors: List[Dict[str, Any]], basis: str,
                    used_fallback: bool = False) -> Dict[str, Any]:
    safe = [f for f in (factors or []) if f and f.get("signal_type") in ALLOWED_SIGNAL_TYPES]
    return {
        "output": output,
        "factors": safe,
        "confidence": _derive_confidence(safe, used_fallback),
        "basis": basis or f"{len(safe)} factor(s) evaluated",
        "signal_types_used": sorted({f["signal_type"] for f in safe}),
    }


# ---------------------------------------------------------------------------
# Career DNA category mapping (Feature 2 — documented for judges)
# ---------------------------------------------------------------------------
# Each category lists the skills that map to it. Detection is a simple
# case-insensitive substring match against the user's declared skills.
# Heuristic scoring per category:
#   matched_in_category / total_in_category * 100, clamped to [0, 100]
# This is a deliberately interpretable baseline so every signal is
# traceable to a named skill (signal_type = "skill_match").
CAREER_DNA_CATEGORIES: Dict[str, List[str]] = {
    "Frontend": [
        "javascript", "typescript", "react", "vue", "angular", "html",
        "css", "tailwindcss", "tailwind", "redux", "next.js", "vite",
    ],
    "Backend": [
        "python", "fastapi", "django", "flask", "node.js", "express",
        "java", "spring", "go", "rest", "graphql", "sql", "postgresql",
        "mongodb",
    ],
    "DevOps": [
        "docker", "kubernetes", "terraform", "aws", "gcp", "azure",
        "linux", "ci/cd", "jenkins", "prometheus", "grafana",
    ],
    "AI/ML": [
        "python", "pytorch", "tensorflow", "scikit-learn", "pandas",
        "numpy", "machine learning", "deep learning", "nlp",
        "transformers", "llms", "computer vision",
    ],
    "Communication": [
        "communication", "writing", "presentation", "leadership",
        "teamwork", "mentoring", "public speaking", "documentation",
    ],
}


def _normalize_skill(s: str) -> str:
    return (s or "").strip().lower()


def _score_career_dna(user_skills: List[str]) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    user_norm = {_normalize_skill(s) for s in (user_skills or []) if s}
    scores: Dict[str, int] = {}
    factors: List[Dict[str, Any]] = []
    for category, skills in CAREER_DNA_CATEGORIES.items():
        matched = [s for s in skills if any(s in u or u in s for u in user_norm)]
        total = max(len(skills), 1)
        pct = int(round(len(matched) / total * 100))
        scores[category] = min(pct, 100)
        for s in matched:
            factors.append({
                "label": f"{s.title()} detected in {category} (skill_match)",
                "positive": True,
                "signal_type": "skill_match",
            })
        missing_sample = [s for s in skills if s not in matched][:2]
        for s in missing_sample:
            factors.append({
                "label": f"{s.title()} missing for {category} (skill_match)",
                "positive": False,
                "signal_type": "skill_match",
            })
    return scores, factors


# ---------------------------------------------------------------------------
# Static data caches (career_advice + skill_roadmaps)
# ---------------------------------------------------------------------------
# All RAG / embedding / HF-inference / chat-generation logic is now in the
# browser bundle (frontend/src/services/ragPipeline.js + hfClient.js).
# The backend keeps only the static JSON caches consumed by the data routes
# /career-advice and /skill-roadmap, plus the seed_corpus path used by the
# /health/dependencies endpoint.
# ---------------------------------------------------------------------------
_DATA_DIR = Path(__file__).resolve().parent / "data"
_CORPUS_PATH = _DATA_DIR / "seed_corpus.json"
_ADVICE_PATH = _DATA_DIR / "career_advice.json"
_ROADMAPS_PATH = _DATA_DIR / "skill_roadmaps.json"
_CHUNKS_PATH = _DATA_DIR / "chunks.json"
_EMBEDDINGS_PATH = _DATA_DIR / "corpus_embeddings.json"


def _load_json(path: Path) -> "List[Dict[str, Any]]":
    if not path.exists():
        return []
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


_ADVICE_CACHE: "List[Dict[str, Any]]" = _load_json(_ADVICE_PATH)
_ROADMAPS_CACHE: "List[Dict[str, Any]]" = _load_json(_ROADMAPS_PATH)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "CareerPath RAG Chatbot API is running"}

@app.get("/health/dependencies")
async def health_dependencies():
    hf_token_set = bool(_os.getenv('HF_TOKEN', ''))
    embeddings_loaded = len([
        c for c in _CORPUS_EMBEDDINGS if c.get('embedding')
    ]) > 0

    hf_reachable = False
    try:
        import urllib.request
        urllib.request.urlopen(
            'https://api-inference.huggingface.co',
            timeout=3
        )
        hf_reachable = True
    except Exception:
        pass

    chroma_ok = _CHROMA_COLLECTION is not None
    corpus_ok = len(_CORPUS_EMBEDDINGS) > 0

    if corpus_ok and embeddings_loaded:
        overall = 'ok'
    elif corpus_ok:
        overall = 'degraded'
    else:
        overall = 'critical'

    return {
        'seed_corpus_loaded': corpus_ok,
        'embeddings_loaded': embeddings_loaded,
        'hf_token': 'set' if hf_token_set else 'missing',
        'hf_inference_reachable': hf_reachable,
        'chroma_connected': chroma_ok,
        'chroma_chunks': _CHROMA_COLLECTION.count() if chroma_ok else 0,
        'use_local_embeddings': _USE_LOCAL_EMBEDDINGS,
        'sentence_transformers_installed': _check_st_installed(),
        'overall': overall
    }

def _check_st_installed() -> bool:
    try:
        import sentence_transformers
        return True
    except ImportError:
        return False


@app.options("/summarize-cv")
async def options_summarize_cv():
    return {"message": "OK"}

@app.post("/summarize-cv")
async def summarize_cv(file: UploadFile = File(...)):
    MAX_CV_BYTES = 10 * 1024 * 1024  # 10 MB hard cap (Vercel function memory ~512 MB)
    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith("application/pdf"):
            raise HTTPException(status_code=400, detail="Please upload a PDF file.")

        # Read file content (bounded)
        content = await file.read()
        if len(content) > MAX_CV_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_CV_BYTES // (1024 * 1024)} MB.",
            )

        # Extract text from PDF
        pdf_file = BytesIO(content)
        try:
            reader = PdfReader(pdf_file)
        except Exception:
            raise HTTPException(status_code=400, detail="Could not read PDF. The file may be corrupted or password-protected.")

        full_text = ""

        for page in reader.pages:
            try:
                page_text = page.extract_text()
            except Exception:
                # Skip unreadable pages instead of failing the whole upload
                continue
            if page_text:
                full_text += page_text + "\n"
        
        # Check if text was extracted
        if not full_text.strip():
            raise HTTPException(status_code=400, detail="No text found in PDF.")
        
        # Extract CV data using pure keyword matching (no LLM)
        parsed_data = _summarize_cv_no_llm(full_text)
        return {
            "data": parsed_data,
            "raw_text": full_text
        }
    
    except HTTPException:
        raise
    except Exception as e:
        error_message = f"Error processing CV: {str(e)}"
        raise HTTPException(status_code=500, detail=error_message)

# ---------------------------------------------------------------------------
# /generate-interview-question + /evaluate-interview-answer — DELETED.
# The Mock Interview component now calls Hugging Face Mistral directly
# via frontend/src/services/interviewAI.js.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Feature 2 — Career DNA
# ---------------------------------------------------------------------------
@app.options("/career-dna")
async def options_career_dna():
    return {"message": "OK"}


@app.post("/career-dna")
async def career_dna(req: Dict[str, Any]):
    """Score the user across 5 DNA categories and return a full envelope.

    Accepted request shape (loose — accepts both raw lists and the
    shape returned by /summarize-cv):
      {
        "keySkills":          ["Python", ...],     # optional
        "toolsTechnologies":  ["Docker", ...],     # optional
        "skills":             ["..."]              # optional alias
      }
    """
    skills: List[str] = []
    for key in ("keySkills", "toolsTechnologies", "skills"):
        vals = req.get(key)
        if isinstance(vals, list):
            skills.extend([str(v) for v in vals if v])

    scores, factors = _score_career_dna(skills)

    basis = f"{len(scores)} categories scored \u00b7 {len(skills)} skills evaluated"
    envelope = _build_envelope(scores, factors, basis)
    envelope["scores"] = scores
    return envelope


# ---------------------------------------------------------------------------
# Feature 3 — Career Readiness Score
# ---------------------------------------------------------------------------
# Weighted aggregate (0-100). Weights are documented and MUST appear as
# weight_component / profile_field / interview_metric factors:
#   * Career DNA category average     -> 40% (weight_component)
#   * Profile completion percentage   -> 30% (profile_field)
#   * Latest mock interview score     -> 30% (interview_metric)
READINESS_WEIGHTS = {"dna": 0.40, "profile": 0.30, "interview": 0.30}


@app.options("/readiness-score")
async def options_readiness_score():
    return {"message": "OK"}


@app.post("/readiness-score")
async def readiness_score(req: Dict[str, Any]):
    """Compute a 0-100 readiness score and return a full envelope.

    Request shape:
      {
        "skills":              ["..."]            # used to score DNA
        "dnaScores":           { "Frontend": 82 } # optional override
        "profileCompletion":   0-100              # required
        "interviewScore":      0-100 | null       # optional
      }
    """
    skills: List[str] = []
    for key in ("keySkills", "toolsTechnologies", "skills"):
        vals = req.get(key)
        if isinstance(vals, list):
            skills.extend([str(v) for v in vals if v])

    dna_scores = req.get("dnaScores")
    if not isinstance(dna_scores, dict) or not dna_scores:
        dna_scores, _ = _score_career_dna(skills)
    dna_avg = (sum(dna_scores.values()) / len(dna_scores)) if dna_scores else 0

    try:
        profile_completion = float(req.get("profileCompletion") or 0)
    except (TypeError, ValueError):
        profile_completion = 0.0
    profile_completion = max(0.0, min(100.0, profile_completion))

    interview_raw = req.get("interviewScore")
    try:
        interview = float(interview_raw) if interview_raw is not None else 0.0
    except (TypeError, ValueError):
        interview = 0.0
    interview = max(0.0, min(100.0, interview))
    has_interview = interview_raw is not None

    w = READINESS_WEIGHTS
    score = round(
        dna_avg * w["dna"]
        + profile_completion * w["profile"]
        + interview * w["interview"]
    )

    factors: List[Dict[str, Any]] = [
        {
            "label": f"Skills component: {round(dna_avg)}/100 \u00d7 {int(w['dna']*100)}% (weight_component)",
            "positive": dna_avg >= 50,
            "signal_type": "weight_component",
            "value": round(dna_avg, 1),
        },
        {
            "label": f"Profile {round(profile_completion)}% complete \u00d7 {int(w['profile']*100)}% (profile_field)",
            "positive": profile_completion >= 70,
            "signal_type": "profile_field",
            "value": round(profile_completion, 1),
        },
        {
            "label": (
                f"Interview score: {round(interview)}/100 \u00d7 {int(w['interview']*100)}% (interview_metric)"
                if has_interview
                else f"No interview score yet \u00d7 {int(w['interview']*100)}% (interview_metric)"
            ),
            "positive": has_interview and interview >= 60,
            "signal_type": "interview_metric",
            "value": round(interview, 1),
        },
    ]

    basis = "3 components scored \u00b7 weights: 40/30/30"
    envelope = _build_envelope(score, factors, basis)
    envelope["score"] = score
    envelope["components"] = {
        "dna": round(dna_avg, 1),
        "profileCompletion": round(profile_completion, 1),
        "interview": round(interview, 1),
    }
    return envelope


# ---------------------------------------------------------------------------
# Feature 4 — Explainability wrapper for skill gap + job match
# ---------------------------------------------------------------------------
# These endpoints DO NOT recompute scores — the frontend already does so
# in matchScore.js. They simply take a precomputed match result and wrap
# it into a valid ExplainabilityEnvelope so the same ReasoningCard can
# render it.
@app.options("/explain-match")
async def options_explain_match():
    return {"message": "OK"}


@app.post("/explain-match")
async def explain_match(req: Dict[str, Any]):
    """Wrap an existing job match result into an ExplainabilityEnvelope.

    Request shape:
      {
        "jobTitle": "...",
        "score": 0-100,
        "matchedSkills": ["..."],
        "missingSkills": ["..."],
        "breakdown": { "skillScore": 0-60,
                       "expScore":   0-20,
                       "trackScore": 0-20 }   # optional
      }
    """
    matched = [str(s) for s in (req.get("matchedSkills") or [])]
    missing = [str(s) for s in (req.get("missingSkills") or [])]
    breakdown = req.get("breakdown") or {}
    try:
        score = float(req.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0

    factors: List[Dict[str, Any]] = []
    for s in matched:
        factors.append({
            "label": f"{s} detected (skill_match)",
            "positive": True,
            "signal_type": "skill_match",
        })
    for s in missing:
        factors.append({
            "label": f"{s} missing (skill_match)",
            "positive": False,
            "signal_type": "skill_match",
        })

    if breakdown:
        weight_labels = {
            "skillScore": ("Skills component", 60),
            "expScore":   ("Experience component", 20),
            "trackScore": ("Track component", 20),
        }
        for key, (name, w) in weight_labels.items():
            if key in breakdown and breakdown[key] is not None:
                try:
                    val = float(breakdown[key])
                except (TypeError, ValueError):
                    continue
                factors.append({
                    "label": f"{name}: {round(val)}/{w} \u00d7 {w}% (weight_component)",
                    "positive": val >= (w / 2),
                    "signal_type": "weight_component",
                    "value": round(val, 1),
                })

    basis = (
        f"{len(matched)} skill(s) matched \u00b7 {len(missing)} skill(s) missing"
    )
    envelope = _build_envelope(score, factors, basis)
    envelope["score"] = score
    return envelope


# ---------------------------------------------------------------------------
# Feature 7 — Facial Expression Analysis: DELETED.
# Camera capture + emotion classification runs in the browser. Frontend
# calls trpakov/vit-face-expression on Hugging Face directly from
# frontend/src/components/FaceExpressionOverlay.jsx.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Feature 5 — Career Advice Q&A
# ---------------------------------------------------------------------------
@app.options("/career-advice")
async def options_career_advice():
    return {"message": "OK"}


@app.get("/career-advice")
async def career_advice(q: str = "", tag: str = "", limit: int = 5):
    """Return matching career advice items.

    Query params:
      q     - free-text keyword search against question + answer + tags
      tag   - filter by a specific tag (exact match, case-insensitive)
      limit - max results (default 5, max 20)
    """
    limit = max(1, min(limit, 20))
    items = _ADVICE_CACHE
    if not items:
        raise HTTPException(status_code=503, detail="Career advice data not loaded.")

    results = []
    q_lower = (q or "").lower().strip()
    tag_lower = (tag or "").lower().strip()

    for item in items:
        # Tag filter
        if tag_lower:
            item_tags = [t.lower() for t in item.get("tags", [])]
            if tag_lower not in item_tags:
                continue
        # Keyword filter
        if q_lower:
            haystack = " ".join([
                item.get("question", ""),
                item.get("answer", ""),
                " ".join(item.get("tags", [])),
                " ".join(item.get("related_skills", [])),
            ]).lower()
            if not any(token in haystack for token in q_lower.split() if len(token) > 2):
                continue
        results.append(item)
        if len(results) >= limit:
            break

    return {
        "items": results,
        "total": len(results),
        "query": q,
        "tag": tag,
    }


@app.post("/career-advice")
async def career_advice_post(req: Dict[str, Any]):
    """POST alias for /career-advice — accepts {q, tag, limit} JSON body."""
    q = req.get("q", "")
    tag = req.get("tag", "")
    limit = int(req.get("limit", 5))
    return await career_advice(q=q, tag=tag, limit=limit)


# ---------------------------------------------------------------------------
# Feature 6 — Skill Roadmaps
# ---------------------------------------------------------------------------
@app.options("/skill-roadmap")
async def options_skill_roadmap():
    return {"message": "OK"}


@app.get("/skill-roadmap")
async def skill_roadmap(track: str = ""):
    """Return skill roadmaps, optionally filtered by track.

    Query params:
      track - filter by career track (e.g. Frontend, Backend, DevOps, AI/ML, Communication)
    """
    items = _ROADMAPS_CACHE
    if not items:
        raise HTTPException(status_code=503, detail="Skill roadmap data not loaded.")

    if track:
        track_lower = track.lower()
        items = [r for r in items if track_lower in r.get("track", "").lower()]

    return {
        "roadmaps": items,
        "total": len(items),
        "track_filter": track,
    }


@app.post("/skill-roadmap")
async def skill_roadmap_post(req: Dict[str, Any]):
    """POST alias for /skill-roadmap — accepts {track} JSON body."""
    track = req.get("track", "")
    return await skill_roadmap(track=track)


# ---------------------------------------------------------------------------
# Missing Backend Routes (Phase 2)
# ---------------------------------------------------------------------------

INTERVIEW_QUESTIONS = {
    "beginner": [
        {"question": "What is the difference between let, const, and var in JavaScript?", "difficulty": "beginner"},
        {"question": "Explain what a REST API is and how it works.", "difficulty": "beginner"},
        {"question": "What is version control and why do developers use Git?", "difficulty": "beginner"},
        {"question": "What is the CSS box model?", "difficulty": "beginner"},
        {"question": "What is the difference between SQL and NoSQL databases?", "difficulty": "beginner"},
        {"question": "What does HTML stand for and what is its purpose?", "difficulty": "beginner"},
        {"question": "What is a function in programming and why is it useful?", "difficulty": "beginner"},
        {"question": "What is the difference between frontend and backend development?", "difficulty": "beginner"},
    ],
    "intermediate": [
        {"question": "Explain closures in JavaScript with an example.", "difficulty": "intermediate"},
        {"question": "What is the difference between authentication and authorization?", "difficulty": "intermediate"},
        {"question": "How does React's virtual DOM improve performance?", "difficulty": "intermediate"},
        {"question": "Explain database indexing and when you would use it.", "difficulty": "intermediate"},
        {"question": "What is Docker and what problem does it solve?", "difficulty": "intermediate"},
        {"question": "What is the difference between synchronous and asynchronous code?", "difficulty": "intermediate"},
        {"question": "Explain the MVC architecture pattern.", "difficulty": "intermediate"},
        {"question": "What are HTTP status codes and give examples of 200 400 and 500.", "difficulty": "intermediate"},
        {"question": "What is a foreign key in a relational database?", "difficulty": "intermediate"},
        {"question": "How does JWT authentication work?", "difficulty": "intermediate"},
    ],
    "advanced": [
        {"question": "How would you design a URL shortening service at scale?", "difficulty": "advanced"},
        {"question": "Explain the CAP theorem and its implications for distributed systems.", "difficulty": "advanced"},
        {"question": "How do you optimize a React application that has performance bottlenecks?", "difficulty": "advanced"},
        {"question": "What are the tradeoffs between microservices and monolithic architecture?", "difficulty": "advanced"},
        {"question": "How would you implement a rate limiter for an API?", "difficulty": "advanced"},
        {"question": "Explain eventual consistency in distributed databases.", "difficulty": "advanced"},
        {"question": "How does Kubernetes handle service discovery and load balancing?", "difficulty": "advanced"},
        {"question": "What is a RAG pipeline and how does it reduce LLM hallucination?", "difficulty": "advanced"},
    ]
}

class InterviewQuestionRequest(BaseModel):
    difficulty: str = "intermediate"
    track: str = ""

@app.post("/generate-interview-question")
async def generate_interview_question(request: InterviewQuestionRequest):
    difficulty = request.difficulty.lower()
    if difficulty not in INTERVIEW_QUESTIONS:
        difficulty = "intermediate"
    question_obj = random.choice(INTERVIEW_QUESTIONS[difficulty])
    return {
        "question": question_obj["question"],
        "difficulty": question_obj["difficulty"]
    }

class InterviewEvaluationRequest(BaseModel):
    question: str
    answer: str
    difficulty: str = "intermediate"

@app.post("/evaluate-interview-answer")
async def evaluate_interview_answer(request: InterviewEvaluationRequest):
    question = request.question
    answer = request.answer
    word_count = len(answer.split())

    # Length scoring (40%)
    if word_count < 20:
        length_score = 30
        length_fb = "Answer is too short. Aim for at least 50 words with a clear explanation."
    elif word_count < 50:
        length_score = 65
        length_fb = "Decent length. Elaborate more — add an example or explain your reasoning."
    elif word_count <= 200:
        length_score = 100
        length_fb = "Good length. Clear and concise."
    else:
        length_score = 85
        length_fb = "Slightly long. Focus on the most important points."

    # Keyword relevance scoring (40%)
    q_words = set(question.lower().replace('?','').split())
    a_words = set(answer.lower().split())
    overlap = len(q_words & a_words)
    keyword_score = min(100, overlap * 12)

    # Structure scoring (20%) — checks for examples and structure
    has_example = any(w in answer.lower() for w in [
        "example", "for instance", "such as", "like", "for example",
        "in my experience", "i used", "we built", "i worked"
    ])
    has_structure = any(w in answer.lower() for w in [
        "first", "second", "finally", "additionally", "however",
        "because", "therefore", "this means", "as a result"
    ])
    structure_score = 100 if (has_example and has_structure) else \
                      80 if (has_example or has_structure) else 50

    # Final weighted score
    final_score = round(
        (length_score * 0.40) +
        (keyword_score * 0.40) +
        (structure_score * 0.20)
    )
    final_score = max(0, min(100, final_score))

    # Build strengths and improvements
    strengths = []
    improvements = []

    if word_count >= 50:
        strengths.append("Well-developed answer with sufficient detail")
    else:
        improvements.append("Provide a more detailed answer — aim for 50+ words")

    if has_example:
        strengths.append("Good use of a concrete example")
    else:
        improvements.append("Add a specific example to strengthen your answer")

    if has_structure:
        strengths.append("Clear logical structure in your response")
    else:
        improvements.append("Use structured language: 'First... Then... Finally...'")

    if overlap >= 3:
        strengths.append("Directly addressed the question asked")
    else:
        improvements.append("Make sure to directly answer what was asked")

    if not strengths:
        strengths.append("You attempted the question — keep practicing")

    return {
        "score": final_score,
        "feedback": length_fb,
        "strengths": strengths,
        "improvements": improvements
    }

# ── RAG GLOBALS ──────────────────────────────────────────────
import math
import os as _os
import re
import threading

_CORPUS_EMBEDDINGS = []          # flat file fallback (kept for /health/dependencies)
_CORPUS_CHUNKS = []
_CHROMA_CLIENT = None
_CHROMA_COLLECTION = None
_LOCAL_EMBED_MODEL = None
_USE_LOCAL_EMBEDDINGS = _os.getenv('USE_LOCAL_EMBEDDINGS', 'true').lower() == 'true'
_HF_TOKEN = _os.getenv('HF_TOKEN', '')
_QUERY_CACHE = {}                # query -> (sources, retrieval_path)
_LAST_EMBED_PATH = 'none'

# ── Hybrid Search Globals (Tasks 1-5) ────────────────────────
_HYBRID_CORPUS: List[Dict] = []      # 157 raw items from seed_corpus.json
_HYBRID_READY: bool = False
_DF_CACHE: Dict[str, int] = {}       # token -> document frequency
_AVG_DOC_LEN: float = 0.0
_DOC_LENS: List[int] = []            # token count per item (parallel to _HYBRID_CORPUS)
_ITEM_EMBED_CACHE: Dict[str, List[float]] = {}  # item id -> embedding

# ── Track filter skill sets (closed, not imported) ───────────
FRONTEND_SKILLS = {
    "react", "vue", "angular", "html", "css", "javascript",
    "typescript", "tailwind", "nextjs", "vite", "svelte",
}
BACKEND_SKILLS = {
    "python", "node", "fastapi", "django", "flask", "express",
    "java", "spring", "postgresql", "mysql", "mongodb", "redis",
}
DEVOPS_SKILLS = {
    "docker", "kubernetes", "ci/cd", "terraform", "aws", "gcp",
    "azure", "nginx", "linux", "bash", "ansible", "github actions",
}
AIML_SKILLS = {
    "pytorch", "tensorflow", "scikit-learn", "pandas", "numpy",
    "hugging face", "transformers", "llm", "nlp", "computer vision",
    "ml", "ai", "langchain", "rag", "embeddings",
}

# ── Load corpus embeddings on startup (kept for /health/dependencies) ───
def _load_corpus():
    global _CORPUS_EMBEDDINGS, _CORPUS_CHUNKS
    try:
        if _EMBEDDINGS_PATH.exists():
            _CORPUS_EMBEDDINGS = _load_json(_EMBEDDINGS_PATH)
            count = len([c for c in _CORPUS_EMBEDDINGS if c.get('embedding')])
            print(f'Corpus embeddings loaded: {count} chunks with embeddings')
        else:
            _CORPUS_EMBEDDINGS = []
            print(f'corpus_embeddings.json not found at {_EMBEDDINGS_PATH} — keyword fallback only')

        if _CHUNKS_PATH.exists():
            _CORPUS_CHUNKS = _load_json(_CHUNKS_PATH)
            print(f'Corpus chunks loaded: {len(_CORPUS_CHUNKS)} chunks')
        else:
            _CORPUS_CHUNKS = []
            print(f'chunks.json not found at {_CHUNKS_PATH}')
    except Exception as e:
        print(f'Corpus load error: {e}')


# ── TASK 1 — Hybrid corpus loader ────────────────────────────
def _tokenize(text: str) -> List[str]:
    """Shared tokenizer: lowercase, strip non-alphanum, split."""
    return re.sub(r'[^a-z0-9 ]', ' ', text.lower()).split()


def _load_hybrid_corpus():
    """Load seed_corpus.json into _HYBRID_CORPUS and pre-compute BM25 stats."""
    global _HYBRID_CORPUS, _HYBRID_READY, _DF_CACHE, _AVG_DOC_LEN, _DOC_LENS
    try:
        seed_path = Path(__file__).resolve().parent / 'data' / 'seed_corpus.json'
        raw = _json.loads(seed_path.read_text(encoding='utf-8'))
        if not isinstance(raw, list):
            raise ValueError('seed_corpus.json is not a JSON array')

        _HYBRID_CORPUS = []
        for item in raw:
            # Normalise skills: jobs use skillsRequired, courses use relatedSkills
            skills = (
                item.get('skillsRequired')
                or item.get('relatedSkills')
                or item.get('skills')
                or []
            )
            item = dict(item)           # shallow copy so we don't mutate the source
            item['skills'] = [str(s) for s in skills if s]

            # Pre-compute token set for BM25
            token_text = (
                item.get('title', '') + ' ' +
                ' '.join(item['skills']) + ' ' +
                item.get('description', '')
            )
            item['_tokens'] = set(_tokenize(token_text))
            item['_token_list'] = _tokenize(token_text)   # list for TF counting
            _HYBRID_CORPUS.append(item)

        # Pre-compute per-item document lengths
        _DOC_LENS = [len(item['_token_list']) for item in _HYBRID_CORPUS]
        _AVG_DOC_LEN = sum(_DOC_LENS) / max(len(_DOC_LENS), 1)

        # Pre-compute document-frequency cache
        _DF_CACHE = {}
        for item in _HYBRID_CORPUS:
            for tok in item['_tokens']:
                _DF_CACHE[tok] = _DF_CACHE.get(tok, 0) + 1

        _HYBRID_READY = True
        print(f'[RAG] Hybrid corpus loaded: {len(_HYBRID_CORPUS)} items')
        print(f'[RAG] BM25 index: {len(_DF_CACHE)} unique tokens, avg_doc_len={_AVG_DOC_LEN:.1f}')

        # Eagerly warm the dense embedding cache in a background thread
        t = threading.Thread(target=_warm_embed_cache, daemon=True)
        t.start()

    except Exception as e:
        print(f'[RAG] Hybrid corpus load error: {e}')
        _HYBRID_READY = False


# ── Local embedding model ─────────────────────────────────────
def _get_local_model():
    global _LOCAL_EMBED_MODEL
    if _LOCAL_EMBED_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            _LOCAL_EMBED_MODEL = SentenceTransformer('all-mpnet-base-v2')
            print('Local embedding model loaded')
        except Exception as e:
            print(f'Local model load failed: {e}')
    return _LOCAL_EMBED_MODEL


def _hf_embed(text: str):
    """HF Inference API embedding. Returns None on failure."""
    global _LAST_EMBED_PATH
    if not _HF_TOKEN:
        return None
    try:
        import urllib.request
        url = (
            'https://api-inference.huggingface.co/pipeline/'
            'feature-extraction/sentence-transformers/all-mpnet-base-v2'
        )
        body = _json.dumps({
            'inputs': text,
            'options': {'wait_for_model': True}
        }).encode()
        req = urllib.request.Request(url, data=body, headers={
            'Authorization': f'Bearer {_HF_TOKEN}',
            'Content-Type': 'application/json',
            'X-Wait-For-Model': 'true',
        })
        with urllib.request.urlopen(req, timeout=5) as r:
            result = _json.loads(r.read())
        _LAST_EMBED_PATH = 'hf'
        return result[0] if isinstance(result[0], list) else result
    except Exception as e:
        print(f'HF API embed failed: {e}')
        return None


def _embed(text: str):
    """Get embedding vector for text. Returns None on failure."""
    global _LAST_EMBED_PATH
    _LAST_EMBED_PATH = 'none'

    # Try local model first
    if _USE_LOCAL_EMBEDDINGS or not _HF_TOKEN:
        try:
            m = _get_local_model()
            if m:
                _LAST_EMBED_PATH = 'local'
                return m.encode(text, normalize_embeddings=True).tolist()
        except Exception as e:
            print(f'Local embed failed: {e}')

    # Try HF API fallback
    if _HF_TOKEN:
        try:
            import urllib.request
            url = (
                'https://api-inference.huggingface.co/pipeline/'
                'feature-extraction/sentence-transformers/all-mpnet-base-v2'
            )
            body = _json.dumps({
                'inputs': text,
                'options': {'wait_for_model': True}
            }).encode()
            req = urllib.request.Request(url, data=body, headers={
                'Authorization': f'Bearer {_HF_TOKEN}',
                'Content-Type': 'application/json'
            })
            with urllib.request.urlopen(req, timeout=5) as r:
                result = _json.loads(r.read())
            _LAST_EMBED_PATH = 'hf'
            return result[0] if isinstance(result[0], list) else result
        except Exception as e:
            print(f'HF API embed failed: {e}')

    return None


# ── Warm the dense embedding cache (background thread at startup) ─
def _warm_embed_cache():
    """Embed all corpus items once and cache by item id. Non-blocking."""
    if not _HYBRID_CORPUS:
        return
    model = _get_local_model()
    if model is None:
        print('[RAG] Embedding cache warm skipped — local model unavailable')
        return
    warmed = 0
    for item in _HYBRID_CORPUS:
        item_id = item.get('id') or item.get('title', '')
        if item_id and item_id not in _ITEM_EMBED_CACHE:
            try:
                text = (
                    item.get('title', '') + '. ' +
                    ', '.join(item.get('skills', [])) + '. ' +
                    item.get('description', '')[:200]
                )
                emb = model.encode(text, normalize_embeddings=True).tolist()
                _ITEM_EMBED_CACHE[item_id] = emb
                warmed += 1
            except Exception as e:
                print(f'[RAG] Embed warm error for {item_id}: {e}')
    print(f'[RAG] Embedding cache warmed: {warmed} items')


# ── Cosine similarity (pure Python, no numpy) ─────────────────
def _cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# LEGACY: _keyword_search — used by old retrieve_sources only
def _keyword_search(query: str, top_k: int = 3):
    query_words = set(query.lower().split())
    scored = []
    for chunk in _CORPUS_EMBEDDINGS:
        text = (chunk.get('text', '') + ' ' + chunk.get('title', '')).lower()
        text_words = set(text.split())
        overlap = len(query_words & text_words)
        if overlap > 0:
            scored.append((overlap, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    seen, results = set(), []
    for _, chunk in scored:
        pid = chunk.get('parent_id', '')
        if pid not in seen:
            seen.add(pid)
            results.append(chunk)
        if len(results) == top_k:
            break
    return results


# ── TASK 2 — Profile-aware metadata filter ───────────────────
def _skill_overlaps(item_skills: List[str], skill_set: set) -> bool:
    """Case-insensitive skill overlap against a track skill set."""
    for skill in item_skills:
        norm = re.sub(r'[^a-z0-9 ]', ' ', (skill or '').lower()).strip()
        norm_compact = norm.replace(' ', '')
        tokens = set(norm.split())
        for sk in skill_set:
            sk_norm = re.sub(r'[^a-z0-9 ]', ' ', sk.lower()).strip()
            sk_compact = sk_norm.replace(' ', '')
            if sk_norm in norm or norm in sk_norm:
                return True
            if sk_compact and (sk_compact in norm_compact or norm_compact in sk_compact):
                return True
            if sk_norm in tokens or any(sk_norm == t for t in tokens):
                return True
    return False


def _filter_corpus(
    corpus: List[Dict],
    preferred_track: 'str | None' = None,
    experience_level: 'str | None' = None,
) -> List[Dict]:
    """Narrow corpus by track and experience before scoring."""
    MIN_ITEMS = 10
    filtered = corpus

    if preferred_track and preferred_track.strip().lower() not in ('', 'general'):
        track_key = preferred_track.strip().lower()
        skill_map = {
            'frontend': FRONTEND_SKILLS,
            'backend': BACKEND_SKILLS,
            'devops': DEVOPS_SKILLS,
            'ai/ml': AIML_SKILLS,
        }
        skill_set = skill_map.get(track_key)
        if skill_set:
            candidate = [
                item for item in corpus
                if item.get('type') in ('job', 'course')
                and _skill_overlaps(item.get('skills', []), skill_set)
            ]
            if len(candidate) >= MIN_ITEMS:
                filtered = candidate

    if experience_level:
        lvl = experience_level.strip().lower()
        if lvl == 'beginner':
            filtered = (
                [i for i in filtered if i.get('type') == 'course'] +
                [i for i in filtered if i.get('type') != 'course']
            )
        elif lvl == 'advanced':
            filtered = (
                [i for i in filtered if i.get('type') == 'job'] +
                [i for i in filtered if i.get('type') != 'job']
            )

    return filtered


# ── TASK 3 — Pure-Python BM25 scorer ─────────────────────────
def _bm25_score(
    query_tokens: 'set[str]',
    item: Dict,
    item_idx: int,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """BM25 score for one item given a query token set."""
    N = len(_HYBRID_CORPUS)
    if N == 0:
        return 0.0
    token_list = item.get('_token_list', [])
    doc_len = _DOC_LENS[item_idx] if item_idx < len(_DOC_LENS) else len(token_list)
    avdl = _AVG_DOC_LEN or 1.0

    score = 0.0
    for tok in query_tokens:
        if tok not in item.get('_tokens', set()):
            continue
        # IDF
        df = _DF_CACHE.get(tok, 0)
        idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
        # TF (exact count from token list)
        tf_raw = token_list.count(tok)
        tf = (tf_raw * (k1 + 1)) / (tf_raw + k1 * (1 - b + b * (doc_len / avdl)))
        score += idf * tf
    return score


# ── TASK 4 — Dense scorer with HF API + local fallback ────────
async def _dense_score_all(
    query: str,
    corpus: List[Dict],
) -> List[float]:
    """Return one cosine-similarity score per corpus item."""
    # --- Embed the query ---
    q_emb = None

    # Try HF API first (fast, 5 s timeout)
    if _HF_TOKEN:
        try:
            import urllib.request as _urllib_req
            _hf_url = (
                'https://api-inference.huggingface.co/pipeline/feature-extraction/'
                'sentence-transformers/all-mpnet-base-v2'
            )
            _body = _json.dumps({
                'inputs': query,
                'options': {'wait_for_model': True}
            }).encode()
            _req = _urllib_req.Request(_hf_url, data=_body, headers={
                'Authorization': f'Bearer {_HF_TOKEN}',
                'Content-Type': 'application/json',
                'X-Wait-For-Model': 'true',
            })
            with _urllib_req.urlopen(_req, timeout=5) as _r:
                _result = _json.loads(_r.read())
            q_emb = _result[0] if isinstance(_result[0], list) else _result
        except Exception as _e:
            print(f'[RAG] HF embed failed ({_e}), using local fallback')

    # Local fallback
    if q_emb is None:
        try:
            _m = _get_local_model()
            if _m is not None:
                q_emb = _m.encode(query, normalize_embeddings=True).tolist()
        except Exception as _e:
            print(f'[RAG] Local embed failed: {_e}')

    if q_emb is None:
        # No embedding possible — return zeros
        return [0.0] * len(corpus)

    # --- Score each corpus item ---
    scores = []
    for item in corpus:
        item_id = item.get('id') or item.get('title', '')
        item_emb = _ITEM_EMBED_CACHE.get(item_id)
        if item_emb is None:
            # Lazy embed on first request if cache miss
            try:
                _m = _get_local_model()
                if _m is not None:
                    text = (
                        item.get('title', '') + '. ' +
                        ', '.join(item.get('skills', [])) + '. ' +
                        item.get('description', '')[:200]
                    )
                    item_emb = _m.encode(text, normalize_embeddings=True).tolist()
                    _ITEM_EMBED_CACHE[item_id] = item_emb
            except Exception:
                pass
        scores.append(_cosine(q_emb, item_emb) if item_emb else 0.0)
    return scores


# ── TASK 5 — Hybrid scorer with alpha weighting ───────────────
async def _hybrid_retrieve(
    query: str,
    corpus: List[Dict],
    top_k: int = 4,
    alpha: float = 0.5,
) -> List[Dict]:
    """BM25 + dense cosine hybrid retrieval. Returns top_k items."""
    if not corpus:
        return []

    # BM25 scores
    query_tokens = set(_tokenize(query))
    bm25_scores = [
        _bm25_score(query_tokens, item, idx)
        for idx, item in enumerate(corpus)
    ]
    max_bm25 = max(bm25_scores) if bm25_scores else 1.0
    if max_bm25 == 0:
        max_bm25 = 1.0
    bm25_norm = [s / max_bm25 for s in bm25_scores]

    # Dense scores
    dense_scores = await _dense_score_all(query, corpus)
    min_d = min(dense_scores) if dense_scores else 0.0
    max_d = max(dense_scores) if dense_scores else 1.0
    range_d = (max_d - min_d) or 1.0
    dense_norm = [(s - min_d) / range_d for s in dense_scores]

    # Hybrid combination
    combined = []
    for i, item in enumerate(corpus):
        h_score = alpha * dense_norm[i] + (1 - alpha) * bm25_norm[i]
        entry = dict(item)   # shallow copy; don't mutate the global corpus
        entry['_hybrid_score'] = round(h_score, 4)
        entry['_dense_score']  = round(dense_norm[i], 4)
        entry['_bm25_score']   = round(bm25_norm[i], 4)
        combined.append((h_score, entry))

    combined.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in combined[:top_k]]


# ── TASK 6 — Lost-in-the-middle context window layout ─────────
def _build_context_window(chunks: List[Dict]) -> str:
    """Reorder chunks to place highest-scored items at top and bottom."""
    if not chunks:
        return ''

    # Reorder: [rank1, rank3, rank4, ..., rank2] so highest is at top,
    # second-highest is at bottom (lost-in-the-middle mitigation)
    if len(chunks) >= 2:
        reordered = [chunks[0]] + chunks[2:] + [chunks[1]]
    else:
        reordered = chunks[:]

    parts = [
        'CAREER GUIDANCE CONTEXT (use these sources to ground your answer):\n'
    ]
    for n, item in enumerate(reordered, start=1):
        item_type  = item.get('type', 'item').upper()
        item_title = item.get('title', 'Untitled')
        skills_str = ', '.join(item.get('skills', []))
        desc       = item.get('description', '')[:300]
        h_score    = item.get('_hybrid_score', 0.0)
        block = (
            f'=== SOURCE {n}: {item_type} \u2014 {item_title} ===\n'
            f'Skills: {skills_str}\n'
            f'Description: {desc}\n'
            f'Relevance score: {h_score}\n'
            f'---'
        )
        parts.append(block)

    return '\n\n'.join(parts)


# ── ChromaDB init (kept — used by /health/dependencies) ──────
def _init_chroma():
    global _CHROMA_CLIENT, _CHROMA_COLLECTION
    try:
        import chromadb
        host = _os.getenv('CHROMA_HOST', 'localhost')
        port = int(_os.getenv('CHROMA_PORT', '8001'))
        _CHROMA_CLIENT = chromadb.HttpClient(host=host, port=port)
        _CHROMA_COLLECTION = _CHROMA_CLIENT.get_or_create_collection(
            name='careerpath_chunks',
            metadata={'hnsw:space': 'cosine'}
        )
        if _CHROMA_COLLECTION.count() == 0:
            _populate_chroma()
        print(f'ChromaDB ready: {_CHROMA_COLLECTION.count()} chunks')
    except Exception as e:
        print(f'ChromaDB unavailable ({e}) — flat file fallback active')
        _CHROMA_CLIENT = None
        _CHROMA_COLLECTION = None


def _populate_chroma():
    if not _CORPUS_EMBEDDINGS:
        return
    ids, embeddings, docs, metas = [], [], [], []
    for c in _CORPUS_EMBEDDINGS:
        if not c.get('embedding'):
            continue
        ids.append(str(c['chunk_id']))
        embeddings.append(c['embedding'])
        docs.append(str(c.get('text', '')))
        metas.append({
            'parent_id': str(c.get('parent_id', '')),
            'type': str(c.get('type', '')),
            'title': str(c.get('title', '')),
            'source_type': str(c.get('metadata', {}).get('source_type', '')),
            'track': str(c.get('metadata', {}).get('track', '')),
            'level': str(c.get('metadata', {}).get('level', ''))
        })
    for i in range(0, len(ids), 500):
        _CHROMA_COLLECTION.add(
            ids=ids[i:i+500],
            embeddings=embeddings[i:i+500],
            documents=docs[i:i+500],
            metadatas=metas[i:i+500]
        )
    print(f'ChromaDB populated: {len(ids)} chunks')


# LEGACY: extract_search_query — kept for compatibility
def extract_search_query(message: str) -> str:
    stop_words = {
        'i', 'me', 'my', 'we', 'you', 'the', 'a', 'an', 'is', 'are', 'was', 'were',
        'be', 'been', 'have', 'has', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'can', 'may', 'might', 'how', 'what', 'when', 'where', 'who',
        'why', 'which', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
        'want', 'need', 'like', 'get', 'know', 'tell', 'help', 'please', 'about',
        'some', 'this', 'that', 'these', 'those', 'it', 'its', 'am', 'or', 'and'
    }
    words = message.lower().split()
    keywords = [w.strip('?,!.') for w in words if w.strip('?,!.') not in stop_words]
    result = ' '.join(keywords[:8])
    return result if result else message


# LEGACY: grade_sources — kept for compatibility
def grade_sources(query: str, sources: list) -> bool:
    if not sources:
        return False
    query_words = set(query.lower().split())
    for s in sources:
        combined = set(
            (s.get('title', '') + ' ' + s.get('text', '')).lower().split()
        )
        if query_words & combined:
            return True
    return False


# LEGACY: retrieve_sources — replaced by _hybrid_retrieve in /chat
# Kept here for any external references; /chat no longer calls this.
def retrieve_sources(query: str, top_k: int = 3):
    """
    LEGACY retrieval chain: cache -> chroma -> flat file cosine -> keyword.
    /chat now uses _hybrid_retrieve instead.
    Returns (sources_list, retrieval_path_string)
    """
    cache_key = query.lower().strip()
    if cache_key in _QUERY_CACHE:
        return _QUERY_CACHE[cache_key]

    # LEGACY ChromaDB semantic search
    if _CHROMA_COLLECTION is not None:
        try:
            q_emb = _embed(query)
            if q_emb:
                results = _CHROMA_COLLECTION.query(
                    query_embeddings=[q_emb],
                    n_results=top_k,
                    include=['documents', 'metadatas', 'distances']
                )
                sources = []
                seen = set()
                for i, doc in enumerate(results['documents'][0]):
                    meta = results['metadatas'][0][i]
                    pid = meta.get('parent_id', '')
                    if pid not in seen:
                        seen.add(pid)
                        sources.append({
                            'chunk_id': results['ids'][0][i],
                            'parent_id': pid,
                            'type': meta.get('type', ''),
                            'title': meta.get('title', ''),
                            'text': doc,
                            'score': round(1 - results['distances'][0][i], 3)
                        })
                if sources:
                    _QUERY_CACHE[cache_key] = (sources, 'chroma')
                    return sources, 'chroma'
        except Exception as e:
            print(f'ChromaDB query failed: {e}')

    # LEGACY flat file cosine search
    if _CORPUS_EMBEDDINGS:
        try:
            q_emb = _embed(query)
            if q_emb:
                scored = []
                for chunk in _CORPUS_EMBEDDINGS:
                    emb = chunk.get('embedding')
                    if emb:
                        scored.append((_cosine(q_emb, emb), chunk))
                scored.sort(key=lambda x: x[0], reverse=True)
                seen, sources = set(), []
                for score, chunk in scored:
                    pid = chunk.get('parent_id', '')
                    if pid not in seen:
                        seen.add(pid)
                        sources.append({**chunk, 'score': round(score, 3)})
                    if len(sources) == top_k:
                        break
                if sources:
                    path = _LAST_EMBED_PATH if _LAST_EMBED_PATH in ('local', 'hf') else 'local'
                    _QUERY_CACHE[cache_key] = (sources, path)
                    return sources, path
        except Exception as e:
            print(f'Flat cosine search failed: {e}')

    # LEGACY keyword fallback
    sources = _keyword_search(query, top_k)
    if sources:
        _QUERY_CACHE[cache_key] = (sources, 'keyword')
        return sources, 'keyword'

    return [], 'none'


# ── Gemini client (used by /chat only) ───────────────────────
try:
    from google import genai as _genai
    _GEMINI_API_KEY = _os.getenv('GEMINI_API_KEY', '')
    _GEMINI_CLIENT = _genai.Client(api_key=_GEMINI_API_KEY) if _GEMINI_API_KEY else None
except ImportError:
    _GEMINI_CLIENT = None
    _GEMINI_API_KEY = ''
_GEMINI_MODEL = 'gemini-2.0-flash'


@app.options('/chat')
async def options_chat():
    return {'message': 'OK'}


@app.post('/chat')
async def chat(req: Dict[str, Any]):
    """Hybrid RAG + Gemini career assistant."""
    try:
        if not _GEMINI_CLIENT:
            raise HTTPException(status_code=500, detail='GEMINI_API_KEY not configured')

        user_message = (req.get('message', '') or '').strip()
        if not user_message:
            raise HTTPException(status_code=400, detail='message field is required')

        preferred_track = req.get('preferred_track') or req.get('preferredTrack')
        experience_level = req.get('experience_level') or req.get('experienceLevel')
        query = extract_search_query(user_message)

        if _HYBRID_READY:
            filtered = _filter_corpus(
                _HYBRID_CORPUS,
                preferred_track=preferred_track,
                experience_level=experience_level,
            )
            top_chunks = await _hybrid_retrieve(query, filtered, top_k=4, alpha=0.5)
            context_window = _build_context_window(top_chunks)
            retrieval_path = 'hybrid'
            sources = [
                {
                    'id': c.get('id', c.get('title', '')),
                    'type': c.get('type', ''),
                    'title': c.get('title', ''),
                    'snippet': c.get('description', '')[:120],
                    'score': c['_hybrid_score'],
                }
                for c in top_chunks
            ]
        else:
            context_window = ''
            retrieval_path = 'none'
            sources = []
            top_chunks = []

        contents = []
        for item in (req.get('history') or [])[-4:]:
            role = item.get('role', 'user')
            content = (item.get('content', '') or '').strip()[:300]
            if content:
                contents.append({
                    'role': role,
                    'parts': [{'text': content}],
                })

        if context_window:
            contents.append({'role': 'user', 'parts': [{'text': context_window}]})

        contents.append({'role': 'user', 'parts': [{'text': user_message}]})

        response = _GEMINI_CLIENT.models.generate_content(
            model=_GEMINI_MODEL,
            contents=contents,
        )

        reply_text = ''
        if response.candidates:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                reply_text = ''.join(
                    part.text for part in candidate.content.parts
                    if hasattr(part, 'text') and part.text
                )

        if not reply_text:
            reply_text = "I'm sorry, I couldn't generate a response. Please try again."

        factors = [
            {
                'label': f"{c['title']} ({c['type']}) (rag_source)",
                'positive': True,
                'signal_type': 'rag_source',
                'value': c['_hybrid_score'],
            }
            for c in top_chunks
        ]

        basis = f"RAG retrieval via {retrieval_path}. Search query: '{query}'"
        envelope = _build_envelope(reply_text, factors, basis)
        envelope['reply'] = reply_text
        envelope['sources'] = sources
        envelope['retrieval_path'] = retrieval_path
        return envelope

    except HTTPException:
        raise
    except Exception as e:
        print(f'Error in chat endpoint: {e}')
        raise HTTPException(status_code=500, detail=f'Chat error: {e}')


@app.on_event("startup")
async def startup_event():
    _load_hybrid_corpus()
    _load_corpus()
    _init_chroma()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
