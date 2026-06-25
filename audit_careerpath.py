"""
audit_careerpath.py — full project audit.

Run from project root:
    python audit_careerpath.py

Pure stdlib only. Each section is isolated — failures in one section
never crash later sections. All HTTP calls use a 15-second timeout
and convert any error into a FAIL row instead of an exception.
"""

from __future__ import annotations

import glob       # noqa: F401  (spec requires this stdlib in scope)
import json
import math       # noqa: F401  (spec requires this stdlib in scope)
import os         # noqa: F401  (spec requires this stdlib in scope)
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


# =====================================================================
# Configuration
# =====================================================================
ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
BACKEND_BASE = "http://localhost:8000"
TIMEOUT = 15

ALLOWED_SIGNAL_TYPES = {
    "rag_source", "skill_match", "weight_component",
    "profile_field", "interview_metric",
}
RESTRICTION_WORDS = [
    "cannot", "outside scope", "only answer", "limited to",
    "tip: ask", "not trained", "beyond my", "i don't have",
    "unable to help", "sorry i can't",
]


# =====================================================================
# Result collection
# =====================================================================
# Ordered: each section is a list of (passed, name, detail) tuples.
RESULTS: "dict[str, list[tuple[bool, str, str]]]" = {}
_CURRENT_SECTION: "str | None" = None


def section(num: int, name: str) -> str:
    global _CURRENT_SECTION
    _CURRENT_SECTION = f"Section {num} — {name}"
    RESULTS.setdefault(_CURRENT_SECTION, [])
    return _CURRENT_SECTION


def check(name: str, passed: bool, detail: str = "") -> None:
    sec = _CURRENT_SECTION or "Section ? — Uncategorized"
    RESULTS.setdefault(sec, []).append((bool(passed), str(name), str(detail)))


# =====================================================================
# HTTP helpers (always swallow exceptions → return (None, msg))
# =====================================================================
def http_get(url: str, timeout: int = TIMEOUT):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace")
            try:
                return r.status, json.loads(body)
            except json.JSONDecodeError:
                return r.status, body
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return e.code, body
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def http_post(url: str, payload=None, timeout: int = TIMEOUT,
              headers: "dict[str, str] | None" = None, data_override: "bytes | None" = None):
    hdrs = {"Content-Type": "application/json"} if headers is None else dict(headers)
    data = (
        data_override
        if data_override is not None
        else (json.dumps(payload).encode("utf-8") if payload is not None else b"")
    )
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace")
            try:
                return r.status, json.loads(body)
            except json.JSONDecodeError:
                return r.status, body
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return e.code, body
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def has_restriction_words(text: str) -> bool:
    if not isinstance(text, str):
        return False
    low = text.lower()
    return any(w.lower() in low for w in RESTRICTION_WORDS)


# =====================================================================
# Section 1 — Backend core (HTTP)
# =====================================================================
def section_1():
    section(1, "Backend Core")

    code, _ = http_get(BACKEND_BASE + "/")
    check("GET / responds 200", code == 200, f"code={code}")

    code, _ = http_get(BACKEND_BASE + "/health/dependencies")
    check("GET /health/dependencies responds 200", code == 200, f"code={code}")

    # /chat
    code, body = http_post(BACKEND_BASE + "/chat",
                           {"message": "how do I become a backend developer?", "history": []})
    check("POST /chat responds 200", code == 200, f"code={code}")
    envelope_fields = ["reply", "sources", "factors", "confidence", "basis", "retrieval_path"]
    body_ok = (code == 200 and isinstance(body, dict))
    for f in envelope_fields:
        check(f'/chat envelope field "{f}" present',
              body_ok and f in body,
              "" if body_ok else f"/chat not reachable (code={code})")
    if body_ok:
        rp = body.get("retrieval_path", "")
        check("/chat retrieval_path in (chroma|hf|hybrid|keyword|cache)",
              rp in ("chroma", "hf", "hybrid", "keyword", "cache"), f"got={rp!r}")
        conf = body.get("confidence")
        check("/chat confidence in (High|Medium|Low)",
              conf in ("High", "Medium", "Low"), f"got={conf!r}")
        check("/chat sources non-empty", bool(body.get("sources")))
        check("/chat reply has no restriction words",
              not has_restriction_words(body.get("reply", "")))
    else:
        for label in ("/chat retrieval_path in (chroma|hf|hybrid|keyword|cache)",
                      "/chat confidence in (High|Medium|Low)",
                      "/chat sources non-empty",
                      "/chat reply has no restriction words"):
            check(label, False, "/chat not reachable")

    # /career-dna
    code, _ = http_post(BACKEND_BASE + "/career-dna", {"skills": ["python", "react"]})
    check("POST /career-dna responds 200", code == 200, f"code={code}")

    # /readiness-score
    code, _ = http_post(
        BACKEND_BASE + "/readiness-score",
        {"skills": ["python", "react"], "dnaScores": {"Backend": 80, "Frontend": 70},
         "profileCompletion": 70, "interviewScore": 6},
    )
    check("POST /readiness-score responds 200", code == 200, f"code={code}")

    # /explain-match
    code, _ = http_post(
        BACKEND_BASE + "/explain-match",
        {"jobTitle": "Frontend Developer", "score": 70,
         "matchedSkills": ["react"], "missingSkills": ["typescript"],
         "breakdown": {"skills": 70, "experience": 30, "track": 80}},
    )
    check("POST /explain-match responds 200", code == 200, f"code={code}")

    # /generate-interview-question for each difficulty
    for diff in ("beginner", "intermediate", "advanced"):
        code, _ = http_post(
            BACKEND_BASE + "/generate-interview-question",
            {"role": "frontend", "difficulty": diff,
             "questionNumber": 1, "previousQuestions": []},
        )
        check(f"POST /generate-interview-question ({diff}) responds 200",
              code == 200, f"code={code}")

    # /evaluate-interview-answer
    code, _ = http_post(
        BACKEND_BASE + "/evaluate-interview-answer",
        {"question": "What is React?", "answer": "A UI library by Facebook.",
         "role": "frontend", "difficulty": "beginner"},
    )
    check("POST /evaluate-interview-answer responds 200", code == 200, f"code={code}")

    # /career-advice
    code, _ = http_post(BACKEND_BASE + "/career-advice", {"q": "python"})
    check("POST /career-advice responds 200", code == 200, f"code={code}")

    # /skill-roadmap
    code, _ = http_post(BACKEND_BASE + "/skill-roadmap", {"skill": "python"})
    check("POST /skill-roadmap responds 200", code == 200, f"code={code}")

    # /summarize-cv (multipart)
    boundary = "----audit-boundary-7f3a"
    pdf_stub = (b"%PDF-1.4\n%audit\n1 0 obj<<>>endobj\nxref\n0 1\n0000000000 65535 f\n"
                b"trailer<<>>\nstartxref\n0\n%%EOF\n")
    multipart = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="audit.pdf"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode() + pdf_stub + f"\r\n--{boundary}--\r\n".encode()
    code, _ = http_post(
        BACKEND_BASE + "/summarize-cv",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        data_override=multipart,
    )
    # 200 or 400 (parser rejects stub PDF) both prove the endpoint exists.
    check("POST /summarize-cv accepts multipart", code in (200, 400), f"code={code}")


# =====================================================================
# Section 2 — RAG pipeline internals (import backend/main.py)
# =====================================================================
def section_2():
    section(2, "RAG Pipeline Internals")

    # Make backend importable without polluting sections that may run later.
    inserted = False
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
        inserted = True
    backend_main = None
    try:
        # Reuse if already imported in another section
        backend_main = sys.modules.get("main")
        if backend_main is None:
            import importlib
            backend_main = importlib.import_module("main")
        check("backend.main imports", True)
    except Exception as e:
        check("backend.main imports", False, f"{type(e).__name__}: {e}")
    finally:
        if inserted and str(BACKEND) in sys.path:
            try:
                sys.path.remove(str(BACKEND))
            except ValueError:
                pass

    callable_names = [
        "extract_search_query", "retrieve_sources", "grade_sources",
        "build_rag_answer", "_load_corpus", "_embed", "_cosine",
        "_keyword_search", "_init_chroma",
    ]
    for n in callable_names:
        fn = getattr(backend_main, n, None) if backend_main else None
        check(f"{n} is callable", callable(fn),
              "module not imported" if backend_main is None else f"got {type(fn).__name__}")

    # INTERVIEW_QUESTIONS
    iq = getattr(backend_main, "INTERVIEW_QUESTIONS", None) if backend_main else None
    check("INTERVIEW_QUESTIONS dict exists", isinstance(iq, dict))
    levels = ("beginner", "intermediate", "advanced")
    if isinstance(iq, dict):
        # Accept both shapes: {level: [...]} OR {role: {level: [...]}}
        flat_ok = all(L in iq and isinstance(iq[L], (list, tuple)) for L in levels)
        nested_ok = (not flat_ok) and any(
            isinstance(v, dict) and all(L in v and isinstance(v[L], (list, tuple)) for L in levels)
            for v in iq.values()
        )
        has_all_levels = flat_ok or nested_ok
        check("INTERVIEW_QUESTIONS has beginner/intermediate/advanced", has_all_levels)

        each_5 = False
        if flat_ok:
            each_5 = all(len(iq[L]) >= 5 for L in levels)
        elif nested_ok:
            each_5 = all(
                isinstance(v, dict) and all(len(v[L]) >= 5 for L in levels)
                for v in iq.values() if isinstance(v, dict) and all(L in v for L in levels)
            )
        check("INTERVIEW_QUESTIONS each level has 5+ questions", each_5,
              "Need >=5 per beginner/intermediate/advanced")
    else:
        check("INTERVIEW_QUESTIONS has beginner/intermediate/advanced", False, "dict missing")
        check("INTERVIEW_QUESTIONS each level has 5+ questions", False, "dict missing")

    # _CORPUS_EMBEDDINGS
    ce = getattr(backend_main, "_CORPUS_EMBEDDINGS", None) if backend_main else None
    dims = None
    if isinstance(ce, list) and ce:
        for item in ce:
            if isinstance(item, dict):
                emb = item.get("embedding") or item.get("vector") or item.get("values")
                if isinstance(emb, list) and emb:
                    dims = len(emb)
                    break
        check("_CORPUS_EMBEDDINGS loaded with embeddings",
              dims is not None, "no embedding-like field found")
        check("_CORPUS_EMBEDDINGS embeddings are 768-dim (mpnet)",
              dims == 768, f"got dims={dims}")
    else:
        check("_CORPUS_EMBEDDINGS loaded with embeddings", False,
              "missing or empty" if backend_main else "module not imported")
        check("_CORPUS_EMBEDDINGS embeddings are 768-dim (mpnet)", False, "no embeddings")

    # _embed
    fn = getattr(backend_main, "_embed", None) if backend_main else None
    if callable(fn):
        try:
            vec = fn("hello world")
            ok = isinstance(vec, (list, tuple)) and len(vec) == 768
            check("_embed() returns 768-dim vector", ok,
                  f"len={len(vec) if hasattr(vec, '__len__') else 'n/a'}")
        except Exception as e:
            check("_embed() returns 768-dim vector", False, f"{type(e).__name__}: {e}")
    else:
        check("_embed() returns 768-dim vector", False, "function missing")

    # extract_search_query
    fn = getattr(backend_main, "extract_search_query", None) if backend_main else None
    if callable(fn):
        try:
            q = "How do I become a senior backend engineer in fintech?"
            r = fn(q)
            ok = isinstance(r, str) and 0 < len(r) < len(q)
            check("extract_search_query() non-empty & shorter than input", ok,
                  f"input={len(q)} result={len(r) if isinstance(r, str) else 'n/a'}")
        except Exception as e:
            check("extract_search_query() non-empty & shorter than input", False,
                  f"{type(e).__name__}: {e}")
    else:
        check("extract_search_query() non-empty & shorter than input", False, "function missing")

    # retrieve_sources
    fn = getattr(backend_main, "retrieve_sources", None) if backend_main else None
    if callable(fn):
        try:
            res = fn("python developer", k=3)
            srcs = res
            path = ""
            if isinstance(res, tuple):
                srcs = res[0] if res else None
                path = res[1] if len(res) > 1 else ""
            ok = bool(srcs) and (path in ("chroma", "hf", "hybrid", "cache") or path == "")
            check("retrieve_sources() returns sources via semantic path", ok,
                  f"path={path!r} n={len(srcs) if hasattr(srcs, '__len__') else 'n/a'}")
        except Exception as e:
            check("retrieve_sources() returns sources via semantic path", False,
                  f"{type(e).__name__}: {e}")
    else:
        check("retrieve_sources() returns sources via semantic path", False, "function missing")

    # grade_sources
    fn = getattr(backend_main, "grade_sources", None) if backend_main else None
    if callable(fn):
        try:
            r = fn("python", [{"title": "python developer",
                               "description": "writing python code"}])
            check("grade_sources() returns bool", isinstance(r, bool), f"got {type(r).__name__}")
        except Exception as e:
            check("grade_sources() returns bool", False, f"{type(e).__name__}: {e}")
    else:
        check("grade_sources() returns bool", False, "function missing")

    # build_rag_answer
    fn = getattr(backend_main, "build_rag_answer", None) if backend_main else None
    if callable(fn):
        try:
            r = fn("how do I learn python?",
                   [{"title": "python", "description": "python is a great first language"}])
            ok = (isinstance(r, str) and len(r) > 50 and not has_restriction_words(r))
            check("build_rag_answer() returns >50 chars with no restriction language", ok,
                  f"len={len(r) if isinstance(r, str) else 'n/a'}")
            r2 = fn("anything", [])
            check("build_rag_answer() handles empty sources gracefully",
                  isinstance(r2, str) and len(r2) > 0,
                  f"got type={type(r2).__name__}")
        except Exception as e:
            check("build_rag_answer() returns >50 chars with no restriction language",
                  False, f"{type(e).__name__}: {e}")
            check("build_rag_answer() handles empty sources gracefully",
                  False, f"{type(e).__name__}: {e}")
    else:
        check("build_rag_answer() returns >50 chars with no restriction language",
              False, "function missing")
        check("build_rag_answer() handles empty sources gracefully",
              False, "function missing")

    # ChromaDB collection
    coll = getattr(backend_main, "_CHROMA_COLLECTION", None) if backend_main else None
    if coll is None:
        check("_CHROMA_COLLECTION present and count > 100", False,
              "module not imported" if backend_main is None else "None")
    else:
        try:
            n = coll.count()
            check("_CHROMA_COLLECTION present and count > 100", n > 100, f"count={n}")
        except Exception as e:
            check("_CHROMA_COLLECTION present and count > 100", False,
                  f"{type(e).__name__}: {e}")


# =====================================================================
# Section 3 — Data files
# =====================================================================
def section_3():
    section(3, "Data Files")

    def _read_json(rel: str):
        p = BACKEND / "data" / rel
        if not p.exists():
            return None, f"missing: {p}"
        try:
            return json.loads(p.read_text(encoding="utf-8")), ""
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"

    def _items(data):
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for k in ("items", "data", "rows"):
                if isinstance(data.get(k), list):
                    return data[k]
        return []

    def _audit(rel: str, min_items: int, id_keys=("id",)):
        data, err = _read_json(rel)
        check(f"{rel} exists", data is not None, err)
        items = _items(data)
        check(f"{rel} has {min_items}+ items", len(items) >= min_items,
              f"count={len(items)}")
        ids = []
        for it in items:
            if not isinstance(it, dict):
                continue
            for k in id_keys:
                if k in it:
                    ids.append(it[k])
                    break
        unique_ok = (len(set(ids)) == len(ids)) if ids else True
        check(f"{rel} has no duplicate IDs",
              unique_ok, f"{len(ids)} ids, {len(set(ids))} unique")
        return items

    _audit("seed_corpus.json", 157)
    _audit("career_advice.json", 20)
    _audit("skill_roadmaps.json", 5)

    chunks = _audit("chunks.json", 300)
    types = {it.get("type") for it in chunks if isinstance(it, dict)}
    check("chunks.json covers types: job, course",
          {"job", "course"}.issubset(types), f"types={sorted(t for t in types if t)}")

    data, err = _read_json("corpus_embeddings.json")
    check("corpus_embeddings.json exists", data is not None, err)
    items = _items(data)
    check("corpus_embeddings.json has 300+ embedded items",
          len(items) >= 300, f"count={len(items)}")
    dims = None
    for it in items:
        if isinstance(it, dict):
            emb = it.get("embedding") or it.get("vector") or it.get("values")
            if isinstance(emb, list) and emb:
                dims = len(emb)
                break
    check("corpus_embeddings.json embeddings are 768-dim",
          dims == 768, f"got dims={dims}")


# =====================================================================
# Section 4 — Security scan
# =====================================================================
def section_4():
    section(4, "Security Scan")

    GEMINI_RE = re.compile(
        r"\b(gemini|genai|GenerativeModel|generate_content|GEMINI_API_KEY)\b", re.I)
    HF_SDK_RE = re.compile(r"\b(InferenceClient|HfInference)\b")
    VITE_HF_RE = re.compile(r"\bVITE_HF_(API_)?TOKEN\b")

    # ----- backend python files
    bad = []
    for py in BACKEND.rglob("*.py"):
        if ".venv" in py.parts or "site-packages" in py.parts:
            continue
        try:
            if GEMINI_RE.search(py.read_text(encoding="utf-8", errors="ignore")):
                bad.append(str(py.relative_to(ROOT)))
        except Exception:
            pass
    check("No Gemini patterns in backend/**/*.py",
          not bad, ", ".join(bad[:5]))

    # ----- frontend src
    bad = []
    src = FRONTEND / "src"
    for ext in ("jsx", "js"):
        for f in src.rglob(f"*.{ext}"):
            try:
                if GEMINI_RE.search(f.read_text(encoding="utf-8", errors="ignore")):
                    bad.append(str(f.relative_to(ROOT)))
            except Exception:
                pass
    check("No Gemini patterns in frontend/src/**/*.{jsx,js}",
          not bad, ", ".join(bad[:5]))

    # ----- no HF SDK on frontend
    bad = []
    for ext in ("jsx", "js"):
        for f in src.rglob(f"*.{ext}"):
            try:
                if HF_SDK_RE.search(f.read_text(encoding="utf-8", errors="ignore")):
                    bad.append(str(f.relative_to(ROOT)))
            except Exception:
                pass
    check("No HF InferenceClient/HfInference SDK calls in frontend",
          not bad, ", ".join(bad[:5]))

    # ----- VITE_HF_(API_)TOKEN must not be in frontend .env files
    bad = []
    for env in FRONTEND.glob(".env*"):
        try:
            txt = env.read_text(encoding="utf-8", errors="ignore")
            if VITE_HF_RE.search(txt):
                bad.append(str(env.relative_to(ROOT)))
        except Exception:
            pass
    check("No VITE_HF_API_TOKEN/VITE_HF_TOKEN in frontend .env*",
          not bad, ", ".join(bad))

    # ----- requirements.txt — no google-genai / gemini lines
    req = BACKEND / "requirements.txt"
    if req.exists():
        text = req.read_text(encoding="utf-8", errors="ignore").lower()
        hits = [m for m in re.findall(r"(google-genai|gemini)", text)]
        check("No google-genai/gemini in backend/requirements.txt",
              not hits, ", ".join(hits))
    else:
        check("No google-genai/gemini in backend/requirements.txt",
              False, "requirements.txt missing")

    # ----- .gitignore essentials
    gi = ROOT / ".gitignore"
    gi_text = gi.read_text(encoding="utf-8", errors="ignore") if gi.exists() else ""
    for needle in (".env", ".venv", "node_modules", "__pycache__"):
        check(f".gitignore covers {needle}",
              needle in gi_text,
              "" if gi.exists() else ".gitignore missing")

    # ----- no hardcoded prod backend URL
    bad = []
    for ext in ("jsx", "js", "ts", "tsx"):
        for f in src.rglob(f"*.{ext}"):
            try:
                if "backendcareerpath.vercel.app" in f.read_text(encoding="utf-8", errors="ignore"):
                    bad.append(str(f.relative_to(ROOT)))
            except Exception:
                pass
    check("No hardcoded 'backendcareerpath.vercel.app' in frontend src",
          not bad, ", ".join(bad[:5]))

    # ----- frontend uses VITE_API_URL or import.meta.env
    found = False
    for ext in ("jsx", "js"):
        for f in src.rglob(f"*.{ext}"):
            try:
                t = f.read_text(encoding="utf-8", errors="ignore")
                if "VITE_API_URL" in t or "import.meta.env" in t:
                    found = True
                    break
            except Exception:
                pass
        if found:
            break
    check("Frontend uses VITE_API_URL or import.meta.env", found)


# =====================================================================
# Section 5 — Frontend components
# =====================================================================
def section_5():
    section(5, "Frontend Components")

    src = FRONTEND / "src"
    required = [
        "components/ReasoningCard.jsx",
        "components/IntelligenceSection.jsx",
        "components/JobCard.jsx",
        "components/SkillGapCard.jsx",
        "components/WhatIfSimulator.jsx",
        "components/MindsparksCredential.jsx",
        "components/FaceExpressionOverlay.jsx",
        "pages/Dashboard.jsx",
        "pages/Chatassistance.jsx",
        "pages/Jobs.jsx",
        "pages/MockInterview.jsx",
        "pages/KnowledgeGraph.jsx",
        "pages/CareerRoadmap.jsx",
        "pages/CvUpload.jsx",
        "utils/explainability.js",
        "utils/matchScore.js",
    ]
    for rel in required:
        check(f"{rel} exists", (src / rel).exists())

    def read(rel: str) -> str:
        p = src / rel
        try:
            return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
        except Exception:
            return ""

    # ----- Chatassistance.jsx
    c = read("pages/Chatassistance.jsx")
    check("Chatassistance.jsx calls /chat", "/chat" in c)
    check("Chatassistance.jsx uses react-markdown", "react-markdown" in c)
    check('Chatassistance.jsx has no "Tip: ask about"',
          not re.search(r"tip:\s*ask about", c, re.I))
    check("Chatassistance.jsx has no scope/career-only restriction phrases",
          not re.search(r"outside.*scope|only answer.*career", c, re.I))

    # ----- MockInterview.jsx
    m = read("pages/MockInterview.jsx")
    for needle in ("getVoiceCoaching", "getOverallCoachingSummary",
                   "/generate-interview-question", "/evaluate-interview-answer"):
        check(f"MockInterview.jsx contains {needle}", needle in m)
    check("MockInterview.jsx renders coaching summary",
          re.search(r"coachingSummary|coaching summary", m, re.I) is not None)
    check("MockInterview.jsx renders voice coaching",
          re.search(r"voiceCoaching|voice coaching", m, re.I) is not None)

    # ----- FaceExpressionOverlay.jsx
    f = read("components/FaceExpressionOverlay.jsx")
    check("FaceExpressionOverlay.jsx contains getExpressionCoaching",
          "getExpressionCoaching" in f)
    check("FaceExpressionOverlay.jsx uses canvas/drawBox",
          re.search(r"canvas|drawBox", f, re.I) is not None)
    check("FaceExpressionOverlay.jsx has expression coaching tips",
          re.search(r"\b(Relax|nervous|confident|calm)\b", f, re.I) is not None)

    # ----- explainability.js
    e = read("utils/explainability.js")
    check("explainability.js has buildEnvelope", "buildEnvelope" in e)
    check("explainability.js has deriveConfidence", "deriveConfidence" in e)
    for sig in sorted(ALLOWED_SIGNAL_TYPES):
        check(f"explainability.js references signal '{sig}'", sig in e)

    # ----- ReasoningCard.jsx
    r = read("components/ReasoningCard.jsx")
    check("ReasoningCard.jsx renders factors", "factor" in r.lower())
    check("ReasoningCard.jsx shows confidence badge",
          re.search(r"confidence", r, re.I) is not None)
    check("ReasoningCard.jsx handles empty factors",
          (re.search(r"factors\?\.|factors\.length|!factors|factors\s*&&", r) is not None)
          or "return null" in r)

    # ----- package.json deps
    pkg = FRONTEND / "package.json"
    deps: dict = {}
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps = {**(data.get("dependencies") or {}),
                    **(data.get("devDependencies") or {})}
            check("frontend/package.json parses", True)
        except Exception as ex:
            check("frontend/package.json parses", False, f"{type(ex).__name__}: {ex}")
    else:
        check("frontend/package.json parses", False, "missing")

    required_deps = [
        "react", "react-dom", "react-router-dom", "vite", "tailwindcss", "firebase",
        "framer-motion", "chart.js", "react-chartjs-2", "@xyflow/react", "jspdf",
        "react-markdown", "react-hot-toast", "lucide-react", "gsap",
    ]
    for d in required_deps:
        check(f"frontend dependency: {d}", d in deps,
              "" if pkg.exists() else "package.json missing")


# =====================================================================
# Section 6 — Envelope contract (HTTP deep check)
# =====================================================================
def section_6():
    section(6, "Envelope Contract")

    routes = [
        ("/chat",            {"message": "How do I become a developer?", "history": []}),
        ("/career-dna",      {"skills": ["python", "react"]}),
        ("/readiness-score", {"skills": ["python", "react"], "dnaScores": {"Backend": 80},
                              "profileCompletion": 70, "interviewScore": 6}),
        ("/explain-match",   {"jobTitle": "Frontend Developer", "score": 70,
                              "matchedSkills": ["react"], "missingSkills": ["typescript"],
                              "breakdown": {"skills": 70, "experience": 30}}),
    ]
    for path, payload in routes:
        code, body = http_post(BACKEND_BASE + path, payload)
        ok_body = (code == 200 and isinstance(body, dict))
        if not ok_body:
            for label in (
                f"{path}: envelope has factors list",
                f"{path}: confidence in (High/Medium/Low)",
                f"{path}: basis non-empty string",
                f"{path}: at least one output field (output|score|response|scores)",
                f"{path}: all factor signal_types in allowed set",
                f"{path}: all factors have non-empty label",
            ):
                check(label, False, f"route not reachable (code={code})")
            continue

        factors = body.get("factors")
        check(f"{path}: envelope has factors list",
              isinstance(factors, list),
              f"got type={type(factors).__name__}")
        check(f"{path}: confidence in (High/Medium/Low)",
              body.get("confidence") in ("High", "Medium", "Low"),
              f"got={body.get('confidence')!r}")
        basis = body.get("basis")
        check(f"{path}: basis non-empty string",
              isinstance(basis, str) and bool(basis.strip()),
              f"got={basis!r}")
        check(f"{path}: at least one output field (output|score|response|scores)",
              any(k in body for k in ("output", "score", "response", "scores")))

        sigs_ok = True
        bad_sigs = []
        labels_ok = True
        if isinstance(factors, list) and factors:
            for f in factors:
                if not isinstance(f, dict):
                    sigs_ok = False
                    labels_ok = False
                    continue
                st = f.get("signal_type")
                if st not in ALLOWED_SIGNAL_TYPES:
                    sigs_ok = False
                    bad_sigs.append(str(st))
                if not (isinstance(f.get("label"), str) and f.get("label").strip()):
                    labels_ok = False
        check(f"{path}: all factor signal_types in allowed set",
              sigs_ok, f"unknown={bad_sigs[:3]}")
        check(f"{path}: all factors have non-empty label", labels_ok)


# =====================================================================
# Section 7 — docker-compose.yml
# =====================================================================
def section_7():
    section(7, "Docker Compose")

    dc = ROOT / "docker-compose.yml"
    yml_checks = [
        ("chroma: service",             r"^\s{2,}chroma\s*:"),
        ("chromadb/chroma image",       r"chromadb/chroma"),
        ("8001:8001 port",              r"8001:8001"),
        ("chroma_data volume",          r"chroma_data"),
        ("IS_PERSISTENT env",           r"IS_PERSISTENT"),
        ("8000:8000 backend port",      r"8000:8000"),
        ("0.0.0.0 bind",                r"0\.0\.0\.0"),
        ("USE_LOCAL_EMBEDDINGS env",    r"USE_LOCAL_EMBEDDINGS"),
        ("uvicorn command",             r"uvicorn"),
        ("depends_on block",            r"depends_on"),
        ("./backend/data volume mount", r"\./backend/data"),
    ]

    if not dc.exists():
        for name, _ in yml_checks:
            check(f"docker-compose.yml: {name}", False, "docker-compose.yml missing")
        check("docker-compose.yml: no port 7860 in healthcheck", False, "missing")
        check("docker compose ps lists services", False, "no compose file")
        return

    text = dc.read_text(encoding="utf-8", errors="ignore")
    for name, pattern in yml_checks:
        check(f"docker-compose.yml: {name}",
              bool(re.search(pattern, text, re.MULTILINE)))

    # 7860 must not appear inside a healthcheck: block (best-effort line walk)
    in_health = False
    health_indent = None
    has_7860_in_health = False
    for line in text.splitlines():
        stripped = line.rstrip()
        if not stripped.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if re.search(r"\bhealthcheck\s*:", line):
            in_health = True
            health_indent = indent
            continue
        if in_health and indent <= (health_indent or 0):
            in_health = False
        if in_health and "7860" in line:
            has_7860_in_health = True
            break
    check("docker-compose.yml: no port 7860 in healthcheck", not has_7860_in_health)

    # docker compose ps
    try:
        proc = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            capture_output=True, timeout=15, text=True, cwd=str(ROOT),
        )
        if proc.returncode == 0:
            names = []
            for line in proc.stdout.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, list):
                    for s in obj:
                        if isinstance(s, dict):
                            names.append(s.get("Service") or s.get("Name") or "")
                elif isinstance(obj, dict):
                    names.append(obj.get("Service") or obj.get("Name") or "")
            names = [n for n in names if n]
            check("docker compose ps lists services", True,
                  "running: " + (", ".join(names) if names else "none"))
        else:
            check("docker compose ps lists services", False,
                  proc.stderr.strip()[:160] or f"exit={proc.returncode}")
    except FileNotFoundError:
        check("docker compose ps lists services", False, "docker CLI not installed")
    except Exception as e:
        check("docker compose ps lists services", False, f"{type(e).__name__}: {e}")


# =====================================================================
# Section 8 — broad query test (10 /chat calls)
# =====================================================================
def section_8():
    section(8, "Broad Query Test (/chat)")

    queries = [
        "what career should I choose?",
        "what is Docker?",
        "how much do developers earn?",
        "I am a complete beginner where do I start?",
        "what is machine learning?",
        "how do I become a backend developer?",
        "should I learn React or Vue?",
        "how do I build a portfolio?",
        "how do I prepare for technical interviews?",
        "how long does it take to get a developer job?",
    ]
    for q in queries:
        code, body = http_post(BACKEND_BASE + "/chat", {"message": q, "history": []})
        label = f'/chat "{q[:40]}{"…" if len(q) > 40 else ""}" → reply >50 chars, no restriction'
        if code != 200 or not isinstance(body, dict):
            check(label, False, f"code={code}")
            continue
        reply = body.get("reply", "")
        ok = isinstance(reply, str) and len(reply) > 50 and not has_restriction_words(reply)
        detail = ""
        if not ok:
            preview = (reply[:80] + "…") if isinstance(reply, str) and len(reply) > 80 else reply
            detail = f"len={len(reply) if isinstance(reply, str) else 'n/a'} reply={preview!r}"
        check(label, ok, detail)


# =====================================================================
# Reporting
# =====================================================================
def _section_score(results):
    p = sum(1 for r in results if r[0])
    return p, len(results)


def _print_per_section():
    for sec_name, results in RESULTS.items():
        print(sec_name)
        print("-" * len(sec_name))
        for passed, name, detail in results:
            tag = "[PASS]" if passed else "[FAIL]"
            print(f"  {tag} {name}")
            if detail and not passed:
                print(f"         {detail}")
        p, t = _section_score(results)
        print(f"  {sec_name}: {p}/{t} passed")
        print()


def _classify(pct: float) -> str:
    if pct >= 90:
        return "Production Ready"
    if pct >= 70:
        return "Nearly There"
    if pct >= 50:
        return "Significant Work"
    return "Major Issues"


def _category_buckets():
    fully, broken, partial = [], [], []
    for sec_name, results in RESULTS.items():
        p, t = _section_score(results)
        if t == 0:
            continue
        ratio = p / t
        if ratio == 1.0:
            fully.append(sec_name)
        elif ratio == 0.0:
            broken.append(sec_name)
        else:
            partial.append(sec_name)
    return fully, broken, partial


def _priority_fixes():
    weight = {
        "Section 1 — Backend Core": 5,
        "Section 6 — Envelope Contract": 5,
        "Section 8 — Broad Query Test (/chat)": 5,
        "Section 2 — RAG Pipeline Internals": 4,
        "Section 4 — Security Scan": 4,
        "Section 3 — Data Files": 3,
        "Section 5 — Frontend Components": 3,
        "Section 7 — Docker Compose": 2,
    }
    items = []
    for sec_name, results in RESULTS.items():
        w = weight.get(sec_name, 2)
        for passed, name, detail in results:
            if not passed:
                items.append((w, sec_name, name, detail))
    items.sort(reverse=True, key=lambda x: x[0])
    return items[:5]


def _print_final():
    print("=" * 78)
    print("SECTION SUMMARY")
    print("=" * 78)
    print(f"  {'Section':<50} {'Pass':>6} {'Total':>6} {'%':>7}")
    grand_p = grand_t = 0
    for sec_name, results in RESULTS.items():
        p, t = _section_score(results)
        grand_p += p
        grand_t += t
        pct = (p / t * 100) if t else 0.0
        print(f"  {sec_name[:50]:<50} {p:>6} {t:>6} {pct:>6.1f}%")
    print("  " + "-" * 74)
    overall_pct = (grand_p / grand_t * 100) if grand_t else 0.0
    print(f"  {'TOTAL':<50} {grand_p:>6} {grand_t:>6} {overall_pct:>6.1f}%")
    print()

    fully, broken, partial = _category_buckets()
    print("✅ FULLY WORKING:")
    for s in fully:
        print(f"  - {s}")
    if not fully:
        print("  (none)")
    print()
    print("❌ NOT DONE / BROKEN:")
    for s in broken:
        print(f"  - {s}")
    if not broken:
        print("  (none)")
    print()
    print("⚠️  PARTIAL:")
    for s in partial:
        print(f"  - {s}")
    if not partial:
        print("  (none)")
    print()

    print("PRIORITY FIX LIST (top 5):")
    for i, (_w, sec, name, detail) in enumerate(_priority_fixes(), 1):
        d = f" — {detail}" if detail else ""
        print(f"  {i}. [{sec}] {name}{d}")
    if not _priority_fixes():
        print("  (none — all checks passing!)")
    print()

    status = _classify(overall_pct)
    print("=" * 78)
    print(f"OVERALL STATUS: [{overall_pct:.1f}%]  {status}")
    print("=" * 78)


# =====================================================================
# Entry point
# =====================================================================
def main():
    # On Windows the default code page (cp1252) can't encode the unicode
    # glyphs we use in labels and the final report. Force UTF-8 if available.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    sections = (section_1, section_2, section_3, section_4,
                section_5, section_6, section_7, section_8)
    for fn in sections:
        try:
            fn()
        except Exception as e:
            sec = _CURRENT_SECTION or f"Section ? — {fn.__name__}"
            RESULTS.setdefault(sec, []).append(
                (False, f"{fn.__name__} crashed", f"{type(e).__name__}: {e}")
            )
    _print_per_section()
    _print_final()


if __name__ == "__main__":
    main()
