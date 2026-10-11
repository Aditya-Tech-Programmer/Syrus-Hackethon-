

# ============================================================
# 🎓 CAMPUSCONNECT  —  PRO EDITION v2
# SYRUS 7.0 | PS-04
# Python + Streamlit + JSON + Gemini
#
# API KEY (never hard-code it in this file):
#   Option 1: environment variable   ->  export GEMINI_API_KEY="your_key"
#   Option 2: .streamlit/secrets.toml ->  GEMINI_API_KEY = "your_key"
#   Option 3: paste it in the app (top-right profile menu) for this session
#
# WHAT'S NEW IN v2
#   * FIXED: "No Gemini model is available for this key" — the old model names
#     (gemini-2.0-flash / 2.5-flash) are retired. The app now DISCOVERS the models
#     your key can use, ranks them newest-first and auto-falls-back.
#   * Built-in AI diagnostics + "Test Gemini" button
#   * Campus-aware AI (knows your opportunities, mentors, communities) + web sources
#   * Study Kit (notes/PDF -> summary + interactive quiz)
#   * Peer / teammate matching, duplicate-question detection
#   * Impact Dashboard (SDG 4 + 12 metrics, moderation queue, AI impact report)
#   * One-click demo data + instant demo login for judges
# ============================================================

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
import os
import re
import io
import difflib
import hashlib
import hmac
import html
from datetime import datetime, date, timedelta
import math

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="CampusConnect",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# DATA DIRECTORY
# ============================================================

DATA_DIR = "campusconnect_data"
os.makedirs(DATA_DIR, exist_ok=True)

FILES = {
    "users": "users.json",
    "questions": "questions.json",
    "answers": "answers.json",
    "mentors": "mentors.json",
    "mentor_requests": "mentor_requests.json",
    "communities": "communities.json",
    "memberships": "memberships.json",
    "resources": "resources.json",
    "opportunities": "opportunities.json",
    "reports": "reports.json",
    "bookmarks": "bookmarks.json",
}

BANNED_WORDS = ["idiot", "stupid", "scam", "free money", "buy followers"]

# Optional manual override:  export GEMINI_MODEL="gemini-3.5-flash"
GEMINI_MODEL_OVERRIDE = os.getenv("GEMINI_MODEL", "").strip()

# Only used if the live model list can't be fetched. Live discovery is the primary path.
STATIC_MODEL_FALLBACKS = [
    "gemini-3.5-flash", "gemini-3-flash-preview", "gemini-flash-latest",
    "gemini-3.1-flash-lite", "gemini-2.5-flash", "gemini-2.5-flash-lite",
]
SKIP_MODEL_WORDS = (
    "image", "tts", "live", "audio", "embed", "imagen", "veo", "lyria", "robotics",
    "computer-use", "aqa", "learnlm", "gemma", "vision", "native", "deep-research",
)

# Impact assumptions (shown transparently on the Impact page)
ASSUMED_ITEM_VALUE_INR = 150
ASSUMED_CO2_KG_PER_REUSED_ITEM = 2.5

# ============================================================
# DEFAULT DATA
# ============================================================

DEFAULT_COMMUNITIES = [
    {"id": 1, "name": "Python & Programming", "description": "Learn Python, coding and problem solving.", "icon": "🐍", "members": 128},
    {"id": 2, "name": "AI & GenAI", "description": "Explore Artificial Intelligence and Generative AI.", "icon": "🤖", "members": 96},
    {"id": 3, "name": "Web Development", "description": "Frontend, backend and full-stack development.", "icon": "🌐", "members": 84},
    {"id": 4, "name": "Hackathon Hub", "description": "Find teammates, ideas and upcoming hackathons.", "icon": "🏆", "members": 156},
    {"id": 5, "name": "First Year Connect", "description": "A safe community for first-year students.", "icon": "🎓", "members": 210},
    {"id": 6, "name": "Career & Placements", "description": "Placement preparation, internships and careers.", "icon": "💼", "members": 112},
]

DEFAULT_OPPORTUNITIES = [
    {"id": 1, "title": "College Hackathon", "type": "Hackathon", "description": "Build innovative solutions with your team.", "deadline": "30 Oct 2026", "link": "#"},
    {"id": 2, "title": "AI Project Challenge", "type": "Competition", "description": "Create an AI-powered student solution.", "deadline": "10 Nov 2026", "link": "#"},
    {"id": 3, "title": "Python Internship", "type": "Internship", "description": "Beginner-friendly Python development opportunity.", "deadline": "15 Nov 2026", "link": "#"},
    {"id": 4, "title": "Tech Workshop", "type": "Workshop", "description": "Learn modern development tools from industry experts.", "deadline": "20 Nov 2026", "link": "#"},
]

QA_CATEGORIES = ["Programming", "Academics", "AI & GenAI", "Career", "Projects", "College Life", "Other"]
RESOURCE_TYPES = ["Sell", "Lend", "Donate", "Swap"]
OPPORTUNITY_TYPES = ["Hackathon", "Internship", "Workshop", "Competition"]
BRANCHES = [
    "Information Technology",
    "Computer Engineering",
    "Electronics & Telecommunication",
    "Artificial Intelligence & Data Science",
    "Mechanical Engineering",
    "Other",
]
YEARS = ["First Year", "Second Year", "Third Year", "Final Year"]

AI_MODES = {
    "🧠 Study Helper": "You are a patient tutor. Explain step by step with simple examples, then give a 2-question self-check.",
    "💻 Code Helper": "You are a senior software mentor. Give working, well-commented code, explain the logic briefly, and mention edge cases.",
    "🎯 Career Coach": "You are a campus career coach for Indian engineering students. Give practical, honest, actionable advice on internships, placements and skills.",
    "🏆 Hackathon Mentor": "You are a hackathon mentor. Help with ideas, scoping an MVP in 24-36 hours, tech stack, team roles and pitching.",
    "💬 General": "You are a friendly, accurate campus assistant.",
}

QUICK_PROMPTS = [
    "Make me a 7-day Python roadmap",
    "Explain recursion with an example",
    "How do I prepare for my first internship?",
    "Which opportunity on campus should I apply to?",
]

# ============================================================
# DATA FUNCTIONS
# ============================================================

def load_data(name):
    path = os.path.join(DATA_DIR, FILES[name])
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return []


def save_data(name, data):
    path = os.path.join(DATA_DIR, FILES[name])
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)
    os.replace(temp_path, path)


def next_id(data):
    if not data:
        return 1
    return max(item.get("id", 0) for item in data) + 1


def now():
    return datetime.now().strftime("%d-%m-%Y %H:%M")


def ts_days_ago(days, hour=12):
    d = datetime.now() - timedelta(days=days)
    return d.replace(hour=hour, minute=15).strftime("%d-%m-%Y %H:%M")


def parse_dt(text):
    try:
        return datetime.strptime(text, "%d-%m-%Y %H:%M")
    except Exception:
        return None


def initialize_data():
    for name in FILES:
        path = os.path.join(DATA_DIR, FILES[name])
        if not os.path.exists(path):
            if name == "communities":
                save_data(name, DEFAULT_COMMUNITIES)
            elif name == "opportunities":
                save_data(name, DEFAULT_OPPORTUNITIES)
            else:
                save_data(name, [])


initialize_data()

# ============================================================
# HELPERS
# ============================================================

def esc(text):
    return html.escape(str(text or ""))


def moderate(text):
    low = " ".join(str(text).lower().split())
    for word in BANNED_WORDS:
        if word in low:
            return False, f"Your text contains a blocked phrase: “{word}”."
    if low.count("http") >= 3:
        return False, "Too many links — this looks like spam."
    return True, ""


def split_tags(text):
    return [t.strip().lower() for t in str(text or "").replace(";", ",").split(",") if t.strip()]


def overlap_score(a, b):
    """Simple interest/skill overlap score between two comma-separated strings."""
    a_set = set(split_tags(a))
    b_text = str(b or "").lower()
    return sum(1 for t in a_set if t in b_text)


def get_user(uid):
    return next((u for u in load_data("users") if u["id"] == uid), None)


def refresh_session_user():
    uid = st.session_state.user["id"]
    fresh = get_user(uid)
    if fresh:
        st.session_state.user = fresh


def days_left(deadline_text):
    try:
        d = datetime.strptime(deadline_text, "%d %b %Y").date()
        return (d - date.today()).days
    except Exception:
        return None


def flash(kind, message):
    st.session_state.flash = (kind, message)


def show_flash():
    item = st.session_state.pop("flash", None)
    if not item:
        return
    kind, message = item
    {"success": st.success, "warning": st.warning, "error": st.error}.get(kind, st.info)(message)

# ============================================================
# PASSWORD / AUTH  (salted PBKDF2, legacy SHA-256 auto-upgraded)
# ============================================================

def hash_password(password, salt=None):
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000).hex()
    return f"pbkdf2${salt}${digest}"


def verify_password(password, stored):
    if stored.startswith("pbkdf2$"):
        try:
            _, salt, _ = stored.split("$")
        except ValueError:
            return False
        return hmac.compare_digest(hash_password(password, salt), stored)
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)


def find_user(identifier):
    """Match by email, username, or the part of the email before @."""
    ident = identifier.strip().lower()
    if not ident:
        return None
    for user in load_data("users"):
        email = user.get("email", "").lower()
        if ident == email or ident == user.get("username", "").lower() or ident == email.split("@")[0]:
            return user
    return None


def create_user(name, email, password, branch, year, interests, username=""):
    users = load_data("users")
    if find_user(email):
        return False, "An account with this email already exists."
    if username.strip() and any(u.get("username", "").lower() == username.strip().lower() for u in users):
        return False, "That username is taken."
    users.append({
        "id": next_id(users),
        "name": name.strip(),
        "email": email.strip().lower(),
        "username": username.strip().lower(),
        "password": hash_password(password),
        "branch": branch,
        "year": year,
        "interests": interests.strip(),
        "created_at": now(),
    })
    save_data("users", users)
    return True, "Account created successfully!"


def login_user(email, password):
    user = find_user(email)
    if user and verify_password(password, user["password"]):
        if not user["password"].startswith("pbkdf2$"):  # silently upgrade old hashes
            users = load_data("users")
            for u in users:
                if u["id"] == user["id"]:
                    u["password"] = hash_password(password)
                    user = u
            save_data("users", users)
        return user
    return None

# ============================================================
# GEMINI  (self-healing model discovery — key from session / secrets / env)
# ============================================================

def api_key():
    key = st.session_state.get("gemini_key", "AQ.Ab8RN6Lo35wM5P0F97zYUuaCBf5I3SztMiRR_vxa-QFV4vPh8w")
    if key:
        return key
    try:
        secret = str(st.secrets.get("GEMINI_API_KEY", "AQ.Ab8RN6Lo35wM5P0F97zYUuaCBf5I3SztMiRR_vxa-QFV4vPh8w")).strip()
        if secret:
            return secret
    except Exception:
        pass
    return os.getenv("GEMINI_API_KEY", "").strip()


def gemini_enabled():
    return genai is not None and bool(api_key())


def _has_code(raw, code):
    return re.search(rf"\b{code}\b", raw) is not None


def classify_error(exc):
    raw = str(exc)
    low = raw.lower()
    if _has_code(raw, 429) or "resource_exhausted" in low or "quota" in low or "rate limit" in low:
        return "quota"
    if ("api key" in low or "api_key_invalid" in low or "unauthenticated" in low
            or _has_code(raw, 401) or _has_code(raw, 403) or "permission_denied" in low):
        return "auth"
    if _has_code(raw, 404) or "not_found" in low or "not found" in low or "no longer available" in low or "deprecated" in low:
        return "notfound"
    if _has_code(raw, 503) or _has_code(raw, 500) or "unavailable" in low or "overloaded" in low or "deadline" in low:
        return "busy"
    if _has_code(raw, 400) or "invalid_argument" in low:
        return "badreq"
    return "other"


def _model_rank(name):
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    version = float(m.group(1)) if m else 0.0
    tier = 0 if ("flash" in name and "lite" not in name) else (1 if "flash" in name else 2)
    unstable = ("preview" in name) or ("exp" in name)
    return (tier, -version, unstable, name)


@st.cache_data(ttl=900, show_spinner=False)
def discover_models(key):
    """Ask the API which models THIS key can call (so retired models never matter)."""
    client = genai.Client(api_key=key)
    found = []
    for m in client.models.list():
        name = (getattr(m, "name", "") or "").replace("models/", "")
        if not name.startswith("gemini") or any(w in name for w in SKIP_MODEL_WORDS):
            continue
        actions = getattr(m, "supported_actions", None)
        if actions and "generateContent" not in actions:
            continue
        found.append(name)
    return sorted(set(found), key=_model_rank)


def candidate_models():
    names = []
    if GEMINI_MODEL_OVERRIDE:
        names.append(GEMINI_MODEL_OVERRIDE)
    if st.session_state.get("working_model"):
        names.append(st.session_state.working_model)
    try:
        names += discover_models(api_key())[:6]
        st.session_state.discovery_error = ""
    except Exception as exc:
        st.session_state.discovery_error = str(exc)[:300]
        names += STATIC_MODEL_FALLBACKS
    names.append("gemini-flash-latest")  # alias Google keeps pointing at a live Flash model
    return list(dict.fromkeys(n for n in names if n))


def _config(use_search=False, system=None, json_mode=False):
    if types is None:
        return None
    kwargs = {}
    if use_search and not json_mode:
        kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    if system:
        kwargs["system_instruction"] = system
    if json_mode:
        kwargs["response_mime_type"] = "application/json"
    return types.GenerateContentConfig(**kwargs) if kwargs else None


def extract_sources(resp):
    out, seen = [], set()
    try:
        meta = resp.candidates[0].grounding_metadata
        for chunk in (meta.grounding_chunks or []):
            web = chunk.web
            if web and web.uri and web.uri not in seen:
                seen.add(web.uri)
                out.append({"title": web.title or web.uri, "uri": web.uri})
    except Exception:
        pass
    return out[:5]


def _failure_message(kinds, tried, last_raw):
    if "auth" in kinds:
        return "Gemini API key is invalid or lacks access. Create a fresh key at aistudio.google.com/apikey."
    if "quota" in kinds:
        return "Gemini quota / rate limit reached on the available models. Wait a minute, or use another key."
    if kinds and all(k == "notfound" for k in kinds):
        return f"None of the models tried responded (tried: {', '.join(tried[:5])}). Open 🔬 Diagnostics."
    if "busy" in kinds:
        return "Gemini is busy right now. Please retry in a few seconds."
    return f"Gemini request failed: {last_raw[:220]}"


def _precheck():
    if genai is None:
        return "Google GenAI SDK missing. Run: pip install -U google-genai"
    if not api_key():
        return "Gemini API key missing. Add it in the profile menu (top-right) or set GEMINI_API_KEY."
    return None


def ask_gemini(prompt, use_search=False, system=None, json_mode=False):
    """Returns (text, error). Exactly one is None. Auto-discovers and falls back across models."""
    problem = _precheck()
    if problem:
        return None, problem
    try:
        client = genai.Client(api_key=api_key())
    except Exception as exc:
        return None, f"Gemini client error: {str(exc)[:200]}"
    kinds, tried, last_raw = [], [], ""
    for model in candidate_models():
        tried.append(model)
        for search in ([True, False] if (use_search and not json_mode) else [False]):
            try:
                resp = client.models.generate_content(
                    model=model, contents=prompt, config=_config(search, system, json_mode)
                )
                text = (getattr(resp, "text", "") or "").strip()
                if text:
                    st.session_state.working_model = model
                    st.session_state.last_sources = extract_sources(resp) if search else []
                    return text, None
                last_raw = f"{model}: empty response"
                kinds.append("other")
                break
            except Exception as exc:
                kind = classify_error(exc)
                kinds.append(kind)
                last_raw = f"{model}: {exc}"
                st.session_state.last_ai_error = last_raw[:500]
                if kind == "auth":
                    return None, _failure_message(kinds, tried, last_raw)
                if search and kind != "notfound":
                    continue  # retry the same model without the Google Search tool
                break
    return None, _failure_message(kinds, tried, last_raw)


def gemini_stream(prompt, use_search=False, system=None):
    """Generator of text chunks (for st.write_stream). Falls back across models."""
    problem = _precheck()
    if problem:
        yield f"⚠️ {problem}"
        return
    try:
        client = genai.Client(api_key=api_key())
    except Exception as exc:
        yield f"⚠️ Gemini client error: {str(exc)[:200]}"
        return
    kinds, tried, last_raw = [], [], ""
    for model in candidate_models():
        tried.append(model)
        for search in ([True, False] if use_search else [False]):
            started, sources = False, []
            try:
                for chunk in client.models.generate_content_stream(
                    model=model, contents=prompt, config=_config(search, system)
                ):
                    found = extract_sources(chunk) if search else []
                    if found:
                        sources = found
                    piece = getattr(chunk, "text", "") or ""
                    if piece:
                        started = True
                        yield piece
                if started:
                    st.session_state.working_model = model
                    st.session_state.last_sources = sources
                    return
                kinds.append("other")
                last_raw = f"{model}: empty response"
                break
            except Exception as exc:
                if started:
                    return
                kind = classify_error(exc)
                kinds.append(kind)
                last_raw = f"{model}: {exc}"
                st.session_state.last_ai_error = last_raw[:500]
                if kind == "auth":
                    yield f"⚠️ {_failure_message(kinds, tried, last_raw)}"
                    return
                if search and kind != "notfound":
                    continue
                break
    yield f"⚠️ {_failure_message(kinds, tried, last_raw)}"


def ask_gemini_json(prompt):
    """Ask for JSON and parse it safely. Returns (data, error)."""
    text, err = ask_gemini(prompt, json_mode=True)
    if not text:
        return None, err
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned), None
    except Exception:
        match = re.search(r"(\[.*\]|\{.*\})", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1)), None
            except Exception:
                pass
    return None, "Gemini returned malformed JSON. Please try again."


def gemini_diagnose():
    report = {"sdk": genai is not None, "key": bool(api_key()), "models": [], "discovery_error": "",
              "test": "", "ok": False, "model": ""}
    if not report["sdk"] or not report["key"]:
        report["test"] = _precheck() or ""
        return report
    try:
        discover_models.clear()
        report["models"] = discover_models(api_key())
    except Exception as exc:
        report["discovery_error"] = str(exc)[:300]
    text, err = ask_gemini("Reply with exactly the word: OK")
    report["ok"] = bool(text)
    report["test"] = text or err
    report["model"] = st.session_state.get("working_model", "")
    return report


def diagnostics_panel(prefix="diag"):
    if st.button("🔬 Test Gemini connection", key=f"{prefix}_btn"):
        with st.spinner("Testing models available to your key..."):
            st.session_state.diag = gemini_diagnose()
    d = st.session_state.get("diag")
    if d:
        if d["ok"]:
            st.success(f"✅ Working with **{d['model']}**")
        else:
            st.error(f"❌ {d['test']}")
        st.caption(f"SDK installed: {d['sdk']} • Key present: {d['key']}")
        if d["models"]:
            st.caption("Models your key can use (best first): " + ", ".join(d["models"][:8]))
        if d["discovery_error"]:
            st.caption(f"Model list error: {d['discovery_error']}")
        if st.session_state.get("last_ai_error"):
            st.code(st.session_state.last_ai_error, language="text")


def profile_text(user):
    return (
        f"Name: {user['name']}\nYear: {user['year']}\n"
        f"Branch: {user['branch']}\nInterests: {user.get('interests', '')}\n"
    )


def campus_context():
    """Lets the AI answer using REAL CampusConnect data (RAG-lite)."""
    opps = [f"{o['title']} ({o['type']}, deadline {o['deadline']})" for o in load_data("opportunities")
            if (days_left(o["deadline"]) is None or days_left(o["deadline"]) >= 0)][:8]
    mentors = [f"{m['name']} — {m['skills']}" for m in load_data("mentors")][:8]
    comms = [c["name"] for c in load_data("communities")]
    return (
        f"Open opportunities: {'; '.join(opps) or 'none'}\n"
        f"Mentors on the platform: {'; '.join(mentors) or 'none yet'}\n"
        f"Communities: {', '.join(comms)}"
    )


def build_assistant_prompt(user, question, history):
    context = "\n".join(f"{m['role']}: {m['text']}" for m in history[-10:])
    return (
        "You are CampusConnect AI Campus Assistant. Answer the exact question asked. "
        "Hinglish is fine if the student uses it. Use the profile only when relevant. "
        "When relevant, point the student to the matching CampusConnect section (Mentor Hub, Opportunity Hub, "
        "Resource Exchange, Communities, Anonymous Q&A) using the campus data below. "
        "Never invent facts, URLs or citations. Use clear Markdown.\n\n"
        f"Student profile:\n{profile_text(user)}\n"
        f"CampusConnect data:\n{campus_context()}\n\n"
        f"Recent conversation:\n{context or '(none)'}\n\n"
        f"Question:\n{question}"
    )


def show_ai(text, err):
    if text:
        st.markdown(text)
    else:
        st.warning(f"⚠️ {err}")


def show_sources(sources):
    if sources:
        st.caption("🌐 Sources: " + " • ".join(f"[{s['title'][:40]}]({s['uri']})" for s in sources))

# ============================================================
# GAMIFICATION  (XP, levels, badges, leaderboard)
# ============================================================

def user_stats(uid):
    questions = [q for q in load_data("questions") if q["user_id"] == uid]
    answers = [a for a in load_data("answers") if a["user_id"] == uid]
    upvotes = sum(len(a.get("upvotes", [])) for a in answers)
    best = sum(1 for a in answers if a.get("best"))
    comms = sum(1 for m in load_data("memberships") if m["user_id"] == uid)
    res = sum(1 for r in load_data("resources") if r["user_id"] == uid)
    is_mentor = any(m["user_id"] == uid for m in load_data("mentors"))
    saved = sum(1 for b in load_data("bookmarks") if b["user_id"] == uid)
    xp = (len(questions) * 5 + len(answers) * 10 + upvotes * 3 + best * 25
          + comms * 3 + res * 8 + (15 if is_mentor else 0) + saved * 2)
    return {
        "questions": len(questions), "answers": len(answers), "upvotes": upvotes, "best": best,
        "communities": comms, "resources": res, "mentor": is_mentor, "saved": saved,
        "xp": xp, "level": xp // 50 + 1, "into_level": xp % 50,
    }


def badges_for(s):
    out = []
    if s["questions"] >= 1: out.append("🙋 Curious Mind")
    if s["answers"] >= 3: out.append("💡 Helper")
    if s["best"] >= 1: out.append("⭐ Best Answer")
    if s["upvotes"] >= 5: out.append("🔥 Community Favorite")
    if s["mentor"]: out.append("🎓 Mentor")
    if s["resources"] >= 2: out.append("♻️ Eco Sharer")
    if s["communities"] >= 3: out.append("👥 Connector")
    if s["xp"] >= 150: out.append("🚀 Rising Star")
    return out or ["🌱 Just getting started"]


def leaderboard(limit=5):
    rows = []
    for u in load_data("users"):
        s = user_stats(u["id"])
        rows.append({"Rank": 0, "Student": u["name"], "Level": s["level"], "XP": s["xp"]})
    rows.sort(key=lambda r: r["XP"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["Rank"] = i
    return rows[:limit], rows

# ============================================================
# DEMO DATA (one click — makes the app look alive for judges)
# ============================================================

DEMO_PASSWORD = "demo123"


def seed_demo_data():
    users = load_data("users")
    if any(u.get("email", "").endswith("@demo.edu") for u in users):
        return False, "Demo data is already loaded."
    people = [
        ("Aarav Sharma", "aarav", "Information Technology", "Final Year", "Python, AI, Web, Hackathons"),
        ("Diya Patel", "diya", "Artificial Intelligence & Data Science", "Third Year", "AI, Machine Learning, Data Science, Python"),
        ("Rohan Mehta", "rohan", "Computer Engineering", "Second Year", "Web, React, Hackathons, Design"),
        ("Sneha Iyer", "sneha", "Electronics & Telecommunication", "First Year", "Python, Electronics, Career"),
        ("Karan Singh", "karan", "Mechanical Engineering", "Third Year", "Career, Placements, Projects"),
    ]
    ids = {}
    for name, uname, branch, year, interests in people:
        users.append({
            "id": next_id(users), "name": name, "email": f"{uname}@demo.edu", "username": uname,
            "password": hash_password(DEMO_PASSWORD), "branch": branch, "year": year,
            "interests": interests, "created_at": ts_days_ago(12),
        })
        ids[uname] = users[-1]["id"]
    save_data("users", users)

    mentors = load_data("mentors")
    mentors.append({"id": next_id(mentors), "user_id": ids["aarav"], "name": "Aarav Sharma", "year": "Final Year",
                    "branch": "Information Technology", "skills": "DSA, Python, Hackathons, Placements",
                    "about": "Placed at a product company. Won 3 hackathons. Happy to help with DSA roadmaps and project scoping.",
                    "availability": "Saturday evenings"})
    mentors.append({"id": next_id(mentors), "user_id": ids["diya"], "name": "Diya Patel", "year": "Third Year",
                    "branch": "Artificial Intelligence & Data Science", "skills": "Machine Learning, Data Science, GenAI, Kaggle",
                    "about": "Kaggle expert. I can guide you from your first ML model to a deployed GenAI app.",
                    "availability": "Weekdays after 6 PM"})
    save_data("mentors", mentors)

    questions = load_data("questions")
    qdefs = [
        ("sneha", "How should I start learning Python as a complete beginner?", "I know no programming. Which resources and what order should I follow in first year?", "Programming", 6),
        ("rohan", "Best way to find teammates for my first hackathon?", "I have web skills but no team. Where do I find people with complementary skills?", "Projects", 5),
        ("karan", "When should mechanical students start placement prep?", "Is it okay to start in third year? What skills matter beyond core subjects?", "Career", 4),
        ("sneha", "Difference between AI, ML and GenAI?", "I keep hearing these words together. Can someone explain simply with examples?", "AI & GenAI", 2),
        ("rohan", "How do I stay consistent with DSA practice?", "I start strong and drop after two weeks. Any practical routine that worked for you?", "Academics", 1),
    ]
    qids = []
    for uname, title, desc, cat, ago in qdefs:
        questions.append({"id": next_id(questions), "title": title, "description": desc, "category": cat,
                          "user_id": ids[uname], "created_at": ts_days_ago(ago, 10), "views": 0})
        qids.append(questions[-1]["id"])
    save_data("questions", questions)

    answers = load_data("answers")
    adefs = [
        (0, "aarav", "Start with Python basics (variables, loops, functions), then solve 2 small problems daily. Build a tiny project like a to-do CLI by week 3.", [ids["diya"], ids["rohan"], ids["karan"]], True, 6),
        (0, "diya", "Use the official Python tutorial plus one practice site. Do not hop between courses — finish one first.", [ids["aarav"]], False, 5),
        (1, "aarav", "Join the Hackathon Hub community and look for people whose skills differ from yours. A balanced team is frontend, backend, AI and a presenter.", [ids["rohan"], ids["diya"]], True, 4),
        (2, "aarav", "Third year start is fine. Build one solid project, learn basic programming and aptitude, and practise communication.", [ids["karan"]], False, 3),
        (3, "diya", "AI is the big goal, ML is learning from data to reach it, GenAI is models that create new text, images or code.", [ids["sneha"], ids["rohan"], ids["aarav"]], True, 1),
        (4, "diya", "Fix a 30-minute daily slot and track a streak. Revise old problems on weekends instead of only solving new ones.", [ids["rohan"]], False, 0),
    ]
    for qi, uname, body, ups, best, ago in adefs:
        answers.append({"id": next_id(answers), "question_id": qids[qi], "user_id": ids[uname],
                        "author_name": next(p[0] for p in people if p[1] == uname), "body": body,
                        "created_at": ts_days_ago(ago, 15), "upvotes": ups, "best": best})
    save_data("answers", answers)

    resources = load_data("resources")
    rdefs = [
        ("aarav", "Data Structures & Algorithms textbook", "Clean copy, minimal highlighting. Great for placement prep.", "Donate", "Books", 0, "completed", "sneha", 6),
        ("diya", "Arduino starter kit", "Complete kit with sensors and jumper wires. Lending for one semester.", "Lend", "Electronics", 0, "available", None, 4),
        ("rohan", "First-year Engineering Maths notes", "Handwritten, topic-wise, with solved examples.", "Sell", "Notes", 100, "completed", "sneha", 3),
        ("karan", "Scientific calculator (Casio fx-991)", "Works perfectly. Swap for a drafter set.", "Swap", "Electronics", 0, "reserved", "rohan", 2),
        ("sneha", "Python crash-course book", "Beginner friendly. Looking to donate to a first-year.", "Donate", "Books", 0, "available", None, 1),
    ]
    for uname, title, desc, kind, cat, price, status, claimer, ago in rdefs:
        resources.append({"id": next_id(resources), "user_id": ids[uname], "owner_name": next(p[0] for p in people if p[1] == uname),
                          "title": title, "description": desc, "kind": kind, "category": cat, "price": price,
                          "status": status, "claimed_by": ids[claimer] if claimer else None, "created_at": ts_days_ago(ago)})
    save_data("resources", resources)

    memberships = load_data("memberships")
    for uname, cids in {"aarav": [1, 2, 4, 6], "diya": [1, 2, 4], "rohan": [3, 4], "sneha": [1, 5], "karan": [6]}.items():
        for cid in cids:
            memberships.append({"user_id": ids[uname], "community_id": cid, "joined_at": ts_days_ago(8)})
    save_data("memberships", memberships)

    reqs = load_data("mentor_requests")
    reqs.append({"id": next_id(reqs), "mentor_user_id": ids["aarav"], "mentee_id": ids["sneha"], "mentee_name": "Sneha Iyer",
                 "message": "I'm a first-year and want a Python + DSA roadmap.", "status": "accepted", "created_at": ts_days_ago(5)})
    reqs.append({"id": next_id(reqs), "mentor_user_id": ids["diya"], "mentee_id": ids["rohan"], "mentee_name": "Rohan Mehta",
                 "message": "Want to add an ML feature to my hackathon project.", "status": "pending", "created_at": ts_days_ago(1)})
    save_data("mentor_requests", reqs)

    marks = load_data("bookmarks")
    marks.append({"user_id": ids["sneha"], "opportunity_id": 1, "saved_at": ts_days_ago(2)})
    marks.append({"user_id": ids["rohan"], "opportunity_id": 1, "saved_at": ts_days_ago(2)})
    save_data("bookmarks", marks)
    return True, "Demo data loaded! Log in as aarav / diya / rohan / sneha / karan — password: demo123"

# ============================================================
# SESSION STATE
# ============================================================

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "Dashboard"
if "chat" not in st.session_state:
    st.session_state.chat = []
if "fail_count" not in st.session_state:
    st.session_state.fail_count = 0

# ============================================================
# GLOBAL CSS
# ============================================================

st.markdown("""
<style>
.stApp {
    background:
        radial-gradient(1200px 600px at 85% -10%, rgba(99,102,241,0.14), transparent 60%),
        radial-gradient(900px 500px at -5% 105%, rgba(14,165,233,0.09), transparent 60%),
        linear-gradient(180deg, #0b1220 0%, #0f172a 55%, #111827 100%);
    color: #f8fafc;
}
.block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px; }
section[data-testid="stSidebar"] { background: #0b1220; border-right: 1px solid rgba(148,163,184,0.15); }
section[data-testid="stSidebar"] * { color: #e2e8f0; }
h1, h2, h3 { color: #f8fafc; }
p { color: #cbd5e1; }
div[data-testid="stMetric"] {
    background: rgba(15,23,42,0.75);
    border: 1px solid rgba(96,165,250,0.18);
    padding: 15px; border-radius: 18px;
}
.stButton > button {
    border-radius: 12px; border: 1px solid rgba(96,165,250,0.25);
    font-weight: 600; min-height: 42px;
}
.stTextInput input, .stTextArea textarea, .stSelectbox div, .stMultiSelect div { border-radius: 12px; }
.cc-card {
    background: rgba(15,23,42,0.72);
    border: 1px solid rgba(148,163,184,0.14);
    border-radius: 20px; padding: 22px; margin-bottom: 16px;
}
.cc-card:hover { border-color: rgba(96,165,250,0.35); }
.small-muted { color: #94a3b8; font-size: 14px; }
.tag {
    display: inline-block; padding: 5px 10px; margin: 3px; border-radius: 20px;
    background: rgba(59,130,246,0.14); border: 1px solid rgba(96,165,250,0.20);
    color: #bfdbfe; font-size: 12px;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# 3D GLASS UI
# ============================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3, .cc-title { font-family: 'Plus Jakarta Sans', sans-serif; }

.stApp { perspective: 1400px; }
.stApp:before {
    content:""; position:fixed; inset:0; pointer-events:none; opacity:.04;
    background-image: linear-gradient(rgba(255,255,255,.05) 1px, transparent 1px),
                      linear-gradient(90deg, rgba(255,255,255,.05) 1px, transparent 1px);
    background-size: 34px 34px; mask-image: linear-gradient(to bottom, black, transparent 85%);
}

.stApp .cc-hero {
    position: relative; overflow: hidden; transform-style: preserve-3d;
    box-shadow: 0 28px 80px rgba(0,0,0,.34), inset 0 1px 0 rgba(255,255,255,.07);
}
.stApp .cc-hero:after {
    content:""; position:absolute; width:245px; height:245px; right:4%; top:-76px;
    border-radius:50%; pointer-events:none;
    background: radial-gradient(circle at 30% 28%, rgba(221,252,255,.95) 0%, rgba(67,217,255,.72) 9%, rgba(40,164,222,.25) 35%, rgba(85,230,180,.12) 56%, transparent 72%);
    border:1px solid rgba(151,238,255,.28);
    box-shadow: inset -18px -20px 36px rgba(0,10,25,.46), inset 12px 10px 28px rgba(255,255,255,.16), 0 0 55px rgba(67,217,255,.20);
    animation: ccOrbFloat 7s ease-in-out infinite;
}
.stApp .cc-hero:before {
    content:""; position:absolute; width:300px; height:92px; right:1%; top:40px;
    border:1px solid rgba(67,217,255,.20); border-radius:50%; transform:rotate(-24deg);
    box-shadow:0 0 24px rgba(67,217,255,.08); pointer-events:none;
}
.hero-cc-float {
    position:absolute; z-index:2; top:22px; right:26px; width:66px; height:66px;
    display:flex; align-items:center; justify-content:center; border-radius:20px; color:#fff;
    font-family:'Plus Jakarta Sans',sans-serif; font-size:23px; font-weight:900; letter-spacing:-1px;
    background: linear-gradient(145deg,#31d9ff 0%,#078ee9 48%,#3158ff 100%);
    border:1px solid rgba(205,250,255,.8);
    box-shadow: 0 0 0 5px rgba(25,190,255,.07), 0 12px 28px rgba(0,128,255,.35), inset 0 2px 5px rgba(255,255,255,.5);
    animation: ccLogoFloat 4.8s ease-in-out infinite; pointer-events:none;
}
.hero-cc-float:after {
    content:""; position:absolute; inset:-8px; border-radius:25px;
    border:1px solid rgba(67,217,255,.28); box-shadow:0 0 22px rgba(67,217,255,.12);
}
.cc-hero .cc-badge, .cc-hero .cc-logo, .cc-hero .cc-title, .cc-hero .cc-tagline,
.cc-hero .cc-description, .cc-hero .cc-pills { position: relative; z-index: 1; }

.cc-card, div[data-testid="stMetric"], div[data-testid="stVerticalBlockBorderWrapper"] {
    transform-style: preserve-3d; backdrop-filter: blur(12px);
    transition: transform .28s ease, box-shadow .28s ease, border-color .28s ease;
    box-shadow: 0 16px 38px rgba(0,0,0,.20), inset 0 1px 0 rgba(255,255,255,.035);
}
.cc-card:hover, div[data-testid="stMetric"]:hover {
    transform: translateY(-6px) rotateX(2deg) rotateY(-1deg);
    border-color: rgba(67,217,255,.34);
    box-shadow: 0 26px 52px rgba(0,0,0,.32), 0 0 25px rgba(67,217,255,.07), inset 0 1px 0 rgba(255,255,255,.07);
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    border-color: rgba(67,217,255,.30);
    box-shadow: 0 22px 46px rgba(0,0,0,.28), 0 0 22px rgba(67,217,255,.06);
}
.tag { box-shadow: inset 0 1px 0 rgba(255,255,255,.07), 0 5px 15px rgba(0,0,0,.12); }

.stButton > button, .stDownloadButton > button, [data-testid="stLinkButton"] a {
    background: linear-gradient(135deg,#123b58,#0b2d47) !important;
    color:#f7fbff !important; -webkit-text-fill-color:#f7fbff !important;
    border:1px solid rgba(67,217,255,.28) !important; border-radius:13px !important;
    box-shadow: 0 8px 0 rgba(2,13,23,.42), 0 13px 24px rgba(0,0,0,.20), inset 0 1px 0 rgba(255,255,255,.09);
    transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.stButton > button p, .stButton > button span { color:#f7fbff !important; -webkit-text-fill-color:#f7fbff !important; }
.stButton > button:hover, [data-testid="stLinkButton"] a:hover {
    transform: translateY(-2px); border-color:#43d9ff !important;
    box-shadow: 0 10px 0 rgba(2,13,23,.30), 0 18px 30px rgba(0,0,0,.26), 0 0 22px rgba(67,217,255,.12);
}
.stButton > button:active { transform: translateY(2px); box-shadow: 0 3px 0 rgba(2,13,23,.36); }

label, [data-testid="stWidgetLabel"] p { color:#dff3ff !important; }
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-testid="stNumberInput"] input,
[data-testid="stTextArea"] div[data-baseweb="textarea"] {
    background:#0b2134 !important; color:#f7fbff !important; -webkit-text-fill-color:#f7fbff !important;
    caret-color:#43d9ff !important; border:1px solid rgba(67,217,255,.24) !important; border-radius:14px !important;
}
[data-testid="stTextInput"] input:focus, [data-testid="stTextArea"] textarea:focus {
    border-color:#43d9ff !important; box-shadow:0 0 0 1px rgba(67,217,255,.16), 0 0 22px rgba(67,217,255,.08) !important;
}
[data-testid="stTextInput"] input::placeholder, [data-testid="stTextArea"] textarea::placeholder { color:#8daabd !important; opacity:1 !important; }
[data-testid="stSelectbox"] [data-baseweb="select"] > div, [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
    background:#0a2133 !important; border:1px solid rgba(67,217,255,.22) !important; border-radius:13px !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] *, [data-testid="stMultiSelect"] [data-baseweb="select"] * {
    color:#f7fbff !important; -webkit-text-fill-color:#f7fbff !important;
}
[data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"] {
    background:#0b2438 !important; border:1px solid rgba(67,217,255,.22) !important; border-radius:14px !important;
}
[role="option"], [role="option"] * { background:#0b2438 !important; color:#edf8ff !important; -webkit-text-fill-color:#edf8ff !important; }
[role="option"]:hover, [role="option"][aria-selected="true"], [role="option"][aria-selected="true"] * { background:#123b58 !important; color:#fff !important; }
[data-testid="stExpander"] { border:1px solid rgba(67,217,255,.14) !important; border-radius:16px !important; background:rgba(7,24,39,.78) !important; overflow:hidden; }
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary * { color:#eef9ff !important; }

@keyframes ccOrbFloat { 0%,100% { transform:translate3d(0,0,0) rotate(0deg); } 50% { transform:translate3d(-8px,12px,14px) rotate(5deg); } }
@keyframes ccLogoFloat { 0%,100% { transform:translateY(-2px) rotate(0deg); } 50% { transform:translateY(-7px) rotate(2deg); } }
@media (max-width: 600px) {
    .hero-cc-float { width:48px; height:48px; right:16px; top:16px; border-radius:15px; font-size:18px; }
}
@media (prefers-reduced-motion: reduce) {
    .stApp .cc-hero:after, .hero-cc-float { animation: none; }
    .cc-card, .stButton > button, div[data-testid="stMetric"] { transition: none; }
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# AUTH PAGE (landing UI)
# ============================================================

LANDING_CSS = """
<style>
.block-container { max-width: 1280px; }
header[data-testid="stHeader"] { background: transparent; }

.lp-nav {
    display:flex; align-items:center; justify-content:space-between;
    padding:10px 6px 18px; gap:16px; flex-wrap:wrap;
}
.lp-brand { display:flex; align-items:center; gap:10px; }
.lp-brand-icon {
    width:38px; height:38px; border-radius:12px; display:flex; align-items:center; justify-content:center;
    font-size:22px; background:linear-gradient(145deg,rgba(67,217,255,.25),rgba(49,88,255,.25));
    border:1px solid rgba(67,217,255,.30);
}
.lp-brand-name { font-family:'Plus Jakarta Sans',sans-serif; font-weight:800; font-size:20px; color:#f7fbff; letter-spacing:-.5px; }
.lp-brand-name b { color:#43d9ff; font-weight:800; }
.lp-links { display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
.lp-link {
    padding:9px 16px; font-size:13px; font-weight:600; color:#b6cfdd; border-radius:10px;
    display:flex; align-items:center; gap:7px; position:relative;
}
.lp-link.active { color:#43d9ff; background:rgba(67,217,255,.08); }
.lp-link.active:after { content:""; position:absolute; left:16px; right:16px; bottom:2px; height:2px; border-radius:2px; background:#43d9ff; box-shadow:0 0 10px #43d9ff; }
.lp-avatar {
    width:38px; height:38px; border-radius:50%; display:flex; align-items:center; justify-content:center;
    background:linear-gradient(145deg,#31d9ff,#3158ff); color:#fff; font-weight:800; font-size:15px;
    border:1px solid rgba(205,250,255,.6); box-shadow:0 0 18px rgba(49,152,255,.45);
}

.lp-hero {
    position:relative; overflow:hidden; min-height:330px; padding:34px 36px; border-radius:24px;
    border:1px solid rgba(67,217,255,.45);
    background:
        radial-gradient(circle at 78% 45%, rgba(37,99,235,.35), transparent 38%),
        linear-gradient(135deg,rgba(9,36,66,.97),rgba(5,20,38,.97));
    box-shadow:0 0 0 1px rgba(67,217,255,.08), 0 0 38px rgba(37,150,255,.22), 0 24px 70px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.07);
}
.lp-eyebrow { position:relative; z-index:2; color:#43d9ff; font-size:11px; font-weight:800; letter-spacing:2.4px; margin-bottom:14px; }
.lp-hero h1 {
    position:relative; z-index:2; margin:0 0 14px; max-width:520px;
    font-family:'Plus Jakarta Sans',sans-serif; font-weight:800; font-size:44px; line-height:1.08; letter-spacing:-1.6px; color:#f7fbff;
}
.lp-hero h1 span { background:linear-gradient(90deg,#43d9ff,#2f8bff); -webkit-background-clip:text; background-clip:text; color:transparent; -webkit-text-fill-color:transparent; }
.lp-hero p { position:relative; z-index:2; max-width:470px; color:#b9cad6; font-size:14px; line-height:1.6; margin:0 0 22px; }
.lp-chips { position:relative; z-index:2; display:flex; flex-wrap:wrap; gap:9px; }
.lp-chip {
    padding:8px 13px; border-radius:11px; font-size:11.5px; font-weight:600; color:#d7e8f3;
    background:rgba(255,255,255,.05); border:1px solid rgba(67,217,255,.20);
    box-shadow:inset 0 1px 0 rgba(255,255,255,.06);
}
.lp-orb { position:absolute; right:7%; top:50%; width:230px; height:230px; margin-top:-115px; z-index:1; }
.lp-cc {
    position:absolute; left:50%; top:50%; width:104px; height:104px; margin:-52px 0 0 -52px; border-radius:28px;
    display:flex; align-items:center; justify-content:center; color:#fff;
    font-family:'Plus Jakarta Sans',sans-serif; font-size:38px; font-weight:900; letter-spacing:-2px;
    background:linear-gradient(145deg,#4be3ff 0%,#0a8fe9 48%,#3158ff 100%);
    border:1px solid rgba(215,252,255,.85);
    box-shadow:0 0 0 7px rgba(25,190,255,.08), 0 18px 40px rgba(0,128,255,.5), 0 0 60px rgba(67,217,255,.35), inset 0 3px 8px rgba(255,255,255,.55), inset 0 -8px 16px rgba(0,30,110,.35);
    animation:lpFloat 5s ease-in-out infinite;
}
.lp-ring {
    position:absolute; left:-30px; right:-30px; top:50%; height:120px; margin-top:-60px; border-radius:50%;
    border:1.5px solid rgba(67,217,255,.55); transform:rotate(-20deg);
    box-shadow:0 0 22px rgba(67,217,255,.25), inset 0 0 22px rgba(67,217,255,.12);
}
.lp-ring.two { transform:rotate(-20deg) scale(.82,.78); border-color:rgba(67,217,255,.22); box-shadow:none; }
.lp-dot { position:absolute; border-radius:50%; background:radial-gradient(circle at 30% 30%,#9be9ff,#1f7bff); box-shadow:0 0 14px rgba(67,217,255,.8); }
.lp-dot.a { width:13px; height:13px; left:-8px; top:34%; }
.lp-dot.b { width:10px; height:10px; right:-6px; top:68%; }
.lp-dot.c { width:8px; height:8px; right:24px; top:6%; }

.st-key-login_card {
    position:relative; padding:26px 26px 22px !important; border-radius:22px !important; min-height:330px;
    border:1px solid rgba(67,217,255,.38) !important;
    background:linear-gradient(160deg,rgba(11,40,70,.95),rgba(6,22,40,.97)) !important;
    box-shadow:0 0 34px rgba(37,150,255,.18), 0 22px 60px rgba(0,0,0,.32), inset 0 1px 0 rgba(255,255,255,.07) !important;
}
.st-key-login_card [data-testid="stForm"] { background:transparent !important; border:0 !important; padding:0 !important; }
.lp-welcome { font-family:'Plus Jakarta Sans',sans-serif; font-weight:800; font-size:15px; color:#f7fbff; display:flex; align-items:center; gap:8px; margin-bottom:14px; }
.lp-welcome i { width:9px; height:9px; border-radius:50%; background:#ff4d6d; box-shadow:0 0 10px #ff4d6d; display:inline-block; }
.st-key-login_card [data-testid="stTextInput"] input { padding-left:42px !important; min-height:44px; background-repeat:no-repeat !important; background-position:14px center !important; background-size:17px !important; }
.st-key-login_card input[aria-label="Email or Username"], .st-key-login_card input[aria-label="College Email"] {
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%237dd3fc' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='5' width='18' height='14' rx='2'/%3E%3Cpath d='m3 7 9 6 9-6'/%3E%3C/svg%3E") !important;
}
.st-key-login_card input[aria-label="Password"], .st-key-login_card input[aria-label="Create Password"] {
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%237dd3fc' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='4' y='11' width='16' height='10' rx='2'/%3E%3Cpath d='M8 11V7a4 4 0 0 1 8 0v4'/%3E%3C/svg%3E") !important;
}
.st-key-login_card [data-testid="stFormSubmitButton"] button {
    min-height:46px !important; font-size:15px !important; margin-top:6px;
    background:linear-gradient(90deg,#17c3ff 0%,#2a7bff 100%) !important;
    border:1px solid rgba(190,240,255,.55) !important;
    box-shadow:0 0 26px rgba(30,160,255,.45), 0 8px 0 rgba(2,13,23,.35), inset 0 1px 0 rgba(255,255,255,.4) !important;
}
.lp-new { color:#a8c5d7; font-size:12px; margin-top:16px; }
.st-key-goto_signup .stButton > button, .st-key-goto_login .stButton > button {
    background:transparent !important; border:0 !important; box-shadow:none !important;
    min-height:0 !important; padding:2px 0 !important; color:#43d9ff !important; -webkit-text-fill-color:#43d9ff !important;
    justify-content:flex-start; font-size:13px !important;
}
.st-key-goto_signup .stButton > button p, .st-key-goto_login .stButton > button p { color:#43d9ff !important; -webkit-text-fill-color:#43d9ff !important; }
.st-key-goto_signup .stButton > button:hover, .st-key-goto_login .stButton > button:hover { transform:none !important; box-shadow:none !important; text-decoration:underline; }

.lp-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-top:22px; }
.lp-fcard {
    --c:#3b6bff; position:relative; padding:20px 20px 18px; min-height:150px; border-radius:20px;
    border:1px solid color-mix(in srgb, var(--c) 40%, transparent);
    background:linear-gradient(160deg, color-mix(in srgb, var(--c) 16%, #08182b), #07172a 70%);
    box-shadow:0 16px 38px rgba(0,0,0,.25), 0 6px 26px color-mix(in srgb, var(--c) 28%, transparent), inset 0 -2px 0 color-mix(in srgb, var(--c) 70%, transparent), inset 0 1px 0 rgba(255,255,255,.05);
    transition:transform .25s ease, box-shadow .25s ease;
}
.lp-fcard:hover { transform:translateY(-6px) rotateX(2deg); }
.lp-ficon {
    width:36px; height:36px; border-radius:11px; display:flex; align-items:center; justify-content:center; font-size:18px;
    background:color-mix(in srgb, var(--c) 35%, #0a1d33); border:1px solid color-mix(in srgb, var(--c) 60%, transparent);
    box-shadow:0 0 16px color-mix(in srgb, var(--c) 45%, transparent);
}
.lp-ftitle { margin-top:12px; font-family:'Plus Jakarta Sans',sans-serif; font-weight:800; font-size:15px; color:#f7fbff; }
.lp-fdesc { margin-top:6px; padding-right:34px; font-size:11.5px; line-height:1.5; color:#a8c5d7; }
.lp-farrow {
    position:absolute; right:16px; bottom:16px; width:28px; height:28px; border-radius:50%;
    display:flex; align-items:center; justify-content:center; color:#fff; font-size:14px; font-weight:800;
    background:var(--c); box-shadow:0 0 16px color-mix(in srgb, var(--c) 70%, transparent);
}
@keyframes lpFloat { 0%,100% { transform:translateY(0) rotate(0deg); } 50% { transform:translateY(-9px) rotate(2deg); } }
@media (max-width:1000px) {
    .lp-grid { grid-template-columns:repeat(2,1fr); }
    .lp-orb { opacity:.35; right:-2%; }
}
@media (max-width:640px) {
    .lp-grid { grid-template-columns:1fr; }
    .lp-hero { padding:26px 22px; }
    .lp-hero h1 { font-size:32px; }
    .lp-links { display:none; }
}
@media (prefers-reduced-motion: reduce) { .lp-cc { animation:none; } }
</style>
"""


def top_nav(logged_in=False):
    user = st.session_state.get("user") or {}
    initial = esc((user.get("name") or "?")[:1].upper())
    links = ""
    if not logged_in:
        items = [("🏠", "Home", True), ("🎓", "Mentor", False), ("📖", "Resources", False),
                 ("💼", "Opportunities", False), ("👥", "Community", False)]
        links = "".join(
            f'<div class="lp-link{" active" if a else ""}">{i} {n}</div>' for i, n, a in items
        )
    right = f'<div class="lp-avatar">{initial}</div>' if logged_in else '<div class="lp-avatar">👤</div>'
    st.markdown(
        '<div class="lp-nav">'
        '<div class="lp-brand"><div class="lp-brand-icon">🤖</div>'
        '<div class="lp-brand-name">Campus<b>Connect</b></div></div>'
        f'<div class="lp-links">{links}</div>{right}</div>',
        unsafe_allow_html=True,
    )


def landing_hero_html():
    chips = [("👥", "Peer Learning"), ("🎓", "Mentorship"), ("📖", "Resource Reuse"),
             ("✨", "AI-assisted discovery"), ("🌐", "SDG 4 + SDG 12")]
    chips_html = "".join(f'<span class="lp-chip">{i} {t}</span>' for i, t in chips)
    return (
        '<div class="lp-hero">'
        '<div class="lp-eyebrow">SYRUS 7.0 • PS-04</div>'
        '<h1>Your campus. Your<br>network. <span>Your growth.</span></h1>'
        '<p>A peer-learning platform where students ask, mentor, reuse resources and '
        'discover opportunities — built for a sustainable campus community.</p>'
        f'<div class="lp-chips">{chips_html}</div>'
        '<div class="lp-orb"><div class="lp-ring two"></div><div class="lp-ring"></div>'
        '<div class="lp-cc">CC</div>'
        '<div class="lp-dot a"></div><div class="lp-dot b"></div><div class="lp-dot c"></div></div>'
        '</div>'
    )


def feature_cards_html():
    cards = [
        ("#3b6bff", "🎓", "AI Mentor", "Get personalized guidance, study plans and instant answers."),
        ("#34d399", "📖", "Resources", "Access notes, PDFs, past papers and useful study material."),
        ("#fb923c", "💼", "Opportunities", "Find internships, hackathons, jobs and more."),
        ("#a855f7", "👥", "Community", "Connect, discuss and grow together."),
    ]
    out = '<div class="lp-grid">'
    for c, icon, title, desc in cards:
        out += (
            f'<div class="lp-fcard" style="--c:{c}"><div class="lp-ficon">{icon}</div>'
            f'<div class="lp-ftitle">{title}</div><div class="lp-fdesc">{desc}</div>'
            '<div class="lp-farrow">→</div></div>'
        )
    return out + "</div>"


def _do_login(user):
    st.session_state.fail_count = 0
    st.session_state.logged_in = True
    st.session_state.user = user
    st.session_state.page = "Dashboard"
    st.rerun()


def auth_page():
    st.markdown(LANDING_CSS, unsafe_allow_html=True)
    st.markdown(
        '<style>section[data-testid="stSidebar"], [data-testid="collapsedControl"], '
        '[data-testid="stSidebarCollapsedControl"] { display:none !important; }</style>',
        unsafe_allow_html=True,
    )
    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = "login"

    top_nav(logged_in=False)

    left, right = st.columns([1.75, 1], gap="large")
    with left:
        st.markdown(landing_hero_html(), unsafe_allow_html=True)

    with right:
        with st.container(key="login_card"):
            if st.session_state.auth_mode == "login":
                st.markdown('<div class="lp-welcome"><i></i> Welcome Back!</div>', unsafe_allow_html=True)
                with st.form("login_form", border=False):
                    identifier = st.text_input("Email or Username", placeholder="Email or Username", label_visibility="collapsed")
                    password = st.text_input("Password", type="password", placeholder="Password", label_visibility="collapsed")
                    submit = st.form_submit_button("Login  →", use_container_width=True)
                if submit:
                    if st.session_state.fail_count >= 5:
                        st.error("Too many failed attempts. Refresh the page to try again.")
                    else:
                        user = login_user(identifier, password)
                        if user:
                            _do_login(user)
                        else:
                            st.session_state.fail_count += 1
                            st.error("Invalid email/username or password.")
                st.markdown('<div class="lp-new">New to CampusConnect?</div>', unsafe_allow_html=True)
                if st.button("Create an Account →", key="goto_signup"):
                    st.session_state.auth_mode = "signup"
                    st.rerun()
                st.divider()
                if st.button("⚡ Instant demo login (judges)", key="demo_login", use_container_width=True):
                    seed_demo_data()
                    user = login_user("aarav@demo.edu", DEMO_PASSWORD)
                    if user:
                        _do_login(user)
                    else:
                        st.error("Demo login failed — try Load demo data first.")
                if st.button("🎬 Load demo data only", key="demo_seed", use_container_width=True):
                    ok, msg = seed_demo_data()
                    (st.success if ok else st.info)(msg)
            else:
                st.markdown('<div class="lp-welcome"><i></i> Create your account</div>', unsafe_allow_html=True)
                with st.form("signup_form", border=False):
                    name = st.text_input("Full Name", placeholder="Full name", label_visibility="collapsed")
                    email = st.text_input("College Email", placeholder="College email", label_visibility="collapsed")
                    username = st.text_input("Username", placeholder="Username (optional)", label_visibility="collapsed")
                    password = st.text_input("Create Password", type="password", placeholder="Create password (6+ chars)", label_visibility="collapsed")
                    branch = st.selectbox("Branch", BRANCHES, label_visibility="collapsed")
                    year = st.selectbox("Year", YEARS, label_visibility="collapsed")
                    interests = st.text_input("Interests", placeholder="Interests: Python, AI, Web", label_visibility="collapsed")
                    submit = st.form_submit_button("Create account  →", use_container_width=True)
                if submit:
                    if not name.strip() or not email.strip() or not password:
                        st.warning("Please fill name, email and password.")
                    elif "@" not in email or "." not in email.split("@")[-1]:
                        st.warning("Please enter a valid email address.")
                    elif len(password) < 6:
                        st.warning("Password should contain at least 6 characters.")
                    else:
                        ok, message = create_user(name, email, password, branch, year, interests, username)
                        if ok:
                            st.success(message + " Please log in.")
                            st.session_state.auth_mode = "login"
                        else:
                            st.error(message)
                st.markdown('<div class="lp-new">Already have an account?</div>', unsafe_allow_html=True)
                if st.button("Back to Login →", key="goto_login"):
                    st.session_state.auth_mode = "login"
                    st.rerun()

    st.markdown(feature_cards_html(), unsafe_allow_html=True)

# ============================================================
# APP SHELL (same front-page UI after login)
# ============================================================

APP_CSS = """
<style>
:root { --pc:#3b6bff; }
.block-container { padding-top:1rem !important; max-width:1280px; }
section[data-testid="stSidebar"], [data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"] { display:none !important; }

.st-key-topnav {
    padding:6px 8px; margin:4px 0 18px; border-radius:18px;
    border:1px solid rgba(67,217,255,.24);
    background:linear-gradient(160deg,rgba(11,40,70,.92),rgba(6,22,40,.94));
    box-shadow:0 0 30px rgba(37,150,255,.14), 0 14px 38px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.06);
}
.st-key-topnav [data-testid="stHorizontalBlock"] { flex-wrap:nowrap !important; overflow-x:auto; gap:4px !important; scrollbar-width:thin; }
.st-key-topnav [data-testid="stColumn"], .st-key-topnav [data-testid="column"] { min-width:fit-content !important; flex:1 1 auto !important; width:auto !important; }
[class*="st-key-nav_"] .stButton > button, [class*="st-key-navon_"] .stButton > button {
    background:transparent !important; border:0 !important; box-shadow:none !important; min-height:40px !important;
    border-radius:12px !important; white-space:nowrap; color:#b6cfdd !important; -webkit-text-fill-color:#b6cfdd !important;
}
[class*="st-key-nav_"] .stButton > button p, [class*="st-key-navon_"] .stButton > button p {
    color:inherit !important; -webkit-text-fill-color:inherit !important; font-size:13px; font-weight:600;
}
[class*="st-key-nav_"] .stButton > button:hover { background:rgba(67,217,255,.09) !important; transform:none !important; box-shadow:none !important; color:#fff !important; -webkit-text-fill-color:#fff !important; }
[class*="st-key-navon_"] .stButton > button {
    background:rgba(67,217,255,.12) !important; color:#43d9ff !important; -webkit-text-fill-color:#43d9ff !important;
    box-shadow:inset 0 -2px 0 #43d9ff, 0 0 18px rgba(67,217,255,.18) !important;
}

.lp-hero.sm { min-height:150px; padding:26px 30px; margin-bottom:18px; }
.lp-hero.sm h1 { font-size:32px; margin-bottom:8px; }
.lp-hero.sm p { margin-bottom:14px; }
.lp-hero.sm .lp-orb { transform:scale(.6); transform-origin:100% 50%; right:3%; }
.lp-grid.three { grid-template-columns:repeat(3,1fr); }

div[data-testid="stVerticalBlockBorderWrapper"]:not([data-border="false"]) {
    border:1px solid color-mix(in srgb, var(--pc) 38%, transparent) !important;
    border-radius:20px !important;
    background:linear-gradient(160deg, color-mix(in srgb, var(--pc) 13%, #08182b), #07172a 75%) !important;
    box-shadow:0 16px 38px rgba(0,0,0,.25), 0 6px 26px color-mix(in srgb, var(--pc) 20%, transparent),
               inset 0 -2px 0 color-mix(in srgb, var(--pc) 60%, transparent), inset 0 1px 0 rgba(255,255,255,.05) !important;
    transition:transform .25s ease, box-shadow .25s ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:not([data-border="false"]):hover { transform:translateY(-4px); }
div[data-testid="stMetric"] {
    border:1px solid color-mix(in srgb, var(--pc) 38%, transparent) !important;
    background:linear-gradient(160deg, color-mix(in srgb, var(--pc) 13%, #08182b), #07172a 75%) !important;
    box-shadow:0 14px 32px rgba(0,0,0,.25), 0 4px 22px color-mix(in srgb, var(--pc) 22%, transparent), inset 0 -2px 0 color-mix(in srgb, var(--pc) 60%, transparent) !important;
}
[data-testid="stAlert"] { border-radius:14px !important; background:rgba(9,29,45,.78) !important; border:1px solid rgba(67,217,255,.22) !important; }
[data-testid="stAlert"] * { color:#e9f7ff !important; }
[data-testid="stChatMessage"] { background:rgba(9,29,45,.72) !important; border:1px solid rgba(67,217,255,.16); border-radius:16px; }
[data-testid="stChatInput"] { background:#0b2134 !important; border-radius:16px !important; }
[data-testid="stChatInput"] textarea { color:#f7fbff !important; -webkit-text-fill-color:#f7fbff !important; }
[data-testid="stProgress"] > div > div > div > div { background:linear-gradient(90deg,#17c3ff,#2a7bff) !important; }
[data-testid="stPopover"] button { border-radius:14px !important; }
caption, [data-testid="stCaptionContainer"] { color:#9fb2c4 !important; }

@media (max-width:1000px) { .lp-grid.three { grid-template-columns:repeat(2,1fr); } }
@media (max-width:640px) {
    .lp-grid.three { grid-template-columns:1fr; }
    .lp-hero.sm .lp-orb { display:none; }
    .lp-hero.sm h1 { font-size:26px; }
}
</style>
"""


THREE_D_CSS = """
<style>
[data-testid="stAppViewContainer"]:before {
    content:""; position:fixed; inset:0; z-index:-1; pointer-events:none;
    background:
        radial-gradient(circle at 12% 22%, rgba(99,102,241,.07), transparent 24%),
        radial-gradient(circle at 88% 14%, rgba(56,189,248,.06), transparent 24%);
}
[data-testid="stAppViewContainer"]:after { content:none; }
@keyframes ccDrift { from { transform:translate3d(-14px,-8px,0) scale(1); } to { transform:translate3d(18px,14px,0) scale(1.06); } }
@keyframes ccFloor { from { background-position:0 0; } to { background-position:0 64px; } }
@keyframes ccRise  { from { opacity:0; transform:perspective(1100px) translateY(26px) rotateX(7deg); } to { opacity:1; transform:perspective(1100px) translateY(0) rotateX(0); } }

.lp-hero.sm, .lp-hero, .lp-fcard { animation: ccRise .6s cubic-bezier(.2,.8,.2,1) backwards; }
.lp-fcard:nth-child(2) { animation-delay:.07s; } .lp-fcard:nth-child(3) { animation-delay:.14s; }
.lp-fcard:nth-child(4) { animation-delay:.21s; } .lp-fcard:nth-child(5) { animation-delay:.28s; }
.lp-fcard:nth-child(6) { animation-delay:.35s; }

h1, h2, h3 { text-shadow:0 2px 0 rgba(0,0,0,.45), 0 0 26px color-mix(in srgb, var(--pc) 35%, transparent); }
.lp-hero h1 { text-shadow:none; }
[data-testid="stMetricValue"] { text-shadow:0 2px 0 rgba(0,0,0,.45), 0 0 22px color-mix(in srgb, var(--pc) 55%, transparent); }
[data-testid="stMetricLabel"] p { text-transform:uppercase; letter-spacing:1px; font-size:11px !important; color:#9fb2c4 !important; }
hr { border:0 !important; height:1px !important; background:linear-gradient(90deg, transparent, color-mix(in srgb, var(--pc) 70%, transparent), transparent) !important; }

.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] button, [data-testid="stLinkButton"] a {
    background:
        linear-gradient(180deg, rgba(255,255,255,.16), rgba(255,255,255,0) 52%),
        linear-gradient(135deg, #14507a, #0b2d47) !important;
    box-shadow: 0 7px 0 rgba(2,13,23,.55), 0 14px 26px rgba(0,0,0,.30),
                0 0 18px color-mix(in srgb, var(--pc) 22%, transparent), inset 0 1px 0 rgba(255,255,255,.22) !important;
}
.stButton > button:hover, [data-testid="stFormSubmitButton"] button:hover {
    transform:translateY(-3px) !important;
    box-shadow: 0 10px 0 rgba(2,13,23,.45), 0 20px 34px rgba(0,0,0,.34), 0 0 28px color-mix(in srgb, var(--pc) 45%, transparent), inset 0 1px 0 rgba(255,255,255,.28) !important;
}
.stButton > button:active, [data-testid="stFormSubmitButton"] button:active { transform:translateY(4px) !important; box-shadow:0 2px 0 rgba(2,13,23,.55), 0 4px 10px rgba(0,0,0,.3) !important; }
[class*="st-key-nav_"] .stButton > button, [class*="st-key-navon_"] .stButton > button { background-image:none !important; }
[class*="st-key-nav_"] .stButton > button:hover { transform:translateY(-1px) !important; }
[class*="st-key-navon_"] .stButton > button { transform:translateY(-1px); }

[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-testid="stNumberInput"] input, [data-testid="stDateInput"] input {
    box-shadow: inset 0 4px 10px rgba(0,0,0,.50), inset 0 -1px 0 rgba(255,255,255,.05), 0 1px 0 rgba(255,255,255,.07) !important;
    transition: box-shadow .2s ease, border-color .2s ease, transform .2s ease;
}
[data-testid="stTextInput"] input:focus, [data-testid="stTextArea"] textarea:focus, [data-testid="stNumberInput"] input:focus {
    transform:translateY(-1px);
    box-shadow: inset 0 3px 8px rgba(0,0,0,.45), 0 0 0 2px color-mix(in srgb, var(--pc) 45%, transparent), 0 10px 26px color-mix(in srgb, var(--pc) 25%, transparent) !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div, [data-testid="stMultiSelect"] [data-baseweb="select"] > div, [data-testid="stDateInput"] > div > div {
    box-shadow: inset 0 3px 8px rgba(0,0,0,.45), 0 1px 0 rgba(255,255,255,.06) !important;
}
[data-baseweb="popover"] > div, [data-baseweb="menu"], [data-testid="stPopoverBody"] {
    box-shadow:0 26px 70px rgba(0,0,0,.55), 0 0 30px rgba(67,217,255,.12) !important;
}
[data-testid="stPopoverBody"] { background:#0b2438 !important; border:1px solid rgba(67,217,255,.25) !important; border-radius:18px !important; }

[data-testid="stExpander"] {
    box-shadow:0 14px 34px rgba(0,0,0,.28), 0 4px 22px color-mix(in srgb, var(--pc) 18%, transparent), inset 0 -2px 0 color-mix(in srgb, var(--pc) 55%, transparent), inset 0 1px 0 rgba(255,255,255,.05) !important;
    transition:transform .25s ease, box-shadow .25s ease;
}
[data-testid="stExpander"]:hover { transform:translateY(-3px); }

[data-testid="stAlert"] { box-shadow:0 12px 28px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.05), inset 0 -2px 0 rgba(67,217,255,.35) !important; }
[data-testid="stChatMessage"] { box-shadow:0 12px 28px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.05); transition:transform .2s ease; }
[data-testid="stChatMessage"]:hover { transform:translateY(-2px) perspective(800px) rotateX(1deg); }
[data-testid="stChatInput"] { box-shadow: inset 0 4px 10px rgba(0,0,0,.45), 0 0 0 1px rgba(67,217,255,.25), 0 12px 30px rgba(0,0,0,.3) !important; }
[data-testid="stProgress"] > div > div { background:rgba(255,255,255,.07) !important; box-shadow:inset 0 2px 5px rgba(0,0,0,.5); border-radius:999px; }
[data-testid="stProgress"] > div > div > div > div { box-shadow:0 0 16px rgba(23,195,255,.6), inset 0 1px 0 rgba(255,255,255,.45); border-radius:999px; }

.tag, .lp-chip { transition:transform .2s ease, box-shadow .2s ease; }
.tag:hover, .lp-chip:hover { transform:translateY(-3px); box-shadow:0 10px 20px rgba(0,0,0,.3), 0 0 14px rgba(67,217,255,.25); }

.lp-fcard, .cc-card, [data-testid="stMetric"], div[data-testid="stVerticalBlockBorderWrapper"] { transform-style:preserve-3d; will-change:transform; }

::-webkit-scrollbar { width:10px; height:10px; }
::-webkit-scrollbar-track { background:rgba(5,17,28,.6); }
::-webkit-scrollbar-thumb { background:linear-gradient(180deg,#1f6fa0,#14507a); border-radius:10px; border:2px solid rgba(5,17,28,.6); }

@media (max-width:640px) {
    [data-testid="stAppViewContainer"]:after { height:34vh; }
}
@media (prefers-reduced-motion: reduce) {
    [data-testid="stAppViewContainer"]:before, [data-testid="stAppViewContainer"]:after,
    .lp-hero.sm, .lp-hero, .lp-fcard { animation:none !important; }
}
</style>
"""

TILT_JS = """
<script>
(function () {
  try {
    var P = window.parent, D = P.document;
    if (P.__ccTilt) return;
    if (P.matchMedia && P.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    P.__ccTilt = true;
    var SEL = '.lp-fcard, [data-testid="stMetric"], .cc-card, div[data-testid="stVerticalBlockBorderWrapper"]:not([data-border="false"])';
    var cur = null;
    function reset(el) { if (el) { el.style.transition = 'transform .4s ease'; el.style.transform = ''; } }
    D.addEventListener('mousemove', function (e) {
      var el = e.target && e.target.closest ? e.target.closest(SEL) : null;
      if (cur && cur !== el) { reset(cur); cur = null; }
      if (!el) return;
      var a = D.activeElement;
      if (a && el.contains(a) && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)) { reset(el); return; }
      cur = el;
      var r = el.getBoundingClientRect();
      var x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      var max = (r.width > 700 || r.height > 420) ? 1.6 : 7;
      el.style.transition = 'transform .08s linear';
      el.style.transform = 'perspective(900px) rotateX(' + (-y * max).toFixed(2) + 'deg) rotateY(' + (x * max).toFixed(2) + 'deg) translateY(-4px)';
    }, { passive: true });
    D.addEventListener('mouseleave', function () { reset(cur); cur = null; }, true);
  } catch (err) { /* tilt is optional */ }
})();
</script>
"""

NAV = [
    ("🏠", "Home", "Dashboard"),
    ("💬", "Q&A", "Anonymous Q&A"),
    ("🎓", "Mentor", "Mentor Hub"),
    ("👥", "Community", "Communities"),
    ("📖", "Resources", "Resource Exchange"),
    ("💼", "Opportunities", "Opportunity Hub"),
    ("🤖", "AI Assistant", "AI Campus Assistant"),
    ("🧰", "AI Tools", "AI Tools"),
    ("🛤️", "Growth Path", "Student Growth Path"),
    ("🌍", "Impact", "Impact Dashboard"),
    ("❓", "FAQ", "FAQ"),
]

PAGE_STYLE = {
    "Anonymous Q&A": ("#3b6bff", "COMMUNITY Q&A", [("🕶️", "Anonymous"), ("💡", "Peer answers"), ("✨", "AI summary")]),
    "Mentor Hub": ("#a855f7", "MENTOR NETWORK", [("🎯", "Skill matching"), ("📨", "Requests"), ("🤝", "Peer guidance")]),
    "Communities": ("#a855f7", "COMMUNITIES", [("👥", "Join"), ("💬", "Discuss"), ("🚀", "Contribute")]),
    "Resource Exchange": ("#34d399", "RESOURCE EXCHANGE", [("💸", "Sell"), ("🔁", "Lend"), ("🎁", "Donate"), ("♻️", "Swap")]),
    "Opportunity Hub": ("#fb923c", "OPPORTUNITY RADAR", [("🏆", "Hackathons"), ("💼", "Internships"), ("🛠️", "Workshops")]),
    "AI Campus Assistant": ("#3b6bff", "AI MENTOR", [("🧠", "Study help"), ("💻", "Code help"), ("🎯", "Career")]),
    "AI Tools": ("#43d9ff", "AI TOOLKIT", [("📄", "Resume"), ("💡", "Hackathon ideas"), ("🗓️", "Study plan"), ("🎤", "Interview prep"), ("📚", "Study kit")]),
    "Student Growth Path": ("#43d9ff", "GROWTH PATH", [("✅", "Milestones"), ("📈", "Progress"), ("🤖", "AI plan")]),
    "Impact Dashboard": ("#34d399", "SDG IMPACT", [("🎓", "SDG 4"), ("♻️", "SDG 12"), ("🌍", "Measured impact")]),
    "FAQ": ("#43d9ff", "HELP CENTER", [("🎓", "Academics"), ("💻", "Coding"), ("🏆", "Hackathons"), ("💼", "Placements")]),
    "My Profile": ("#a855f7", "PROFILE", [("🪪", "Identity"), ("🎯", "Interests"), ("🏅", "Contribution")]),
}


def hero_card(eyebrow, title_html, desc, chips, small=False):
    chips_html = "".join(f'<span class="lp-chip">{i} {esc(t)}</span>' for i, t in chips)
    cls = "lp-hero sm" if small else "lp-hero"
    return (
        f'<div class="{cls}"><div class="lp-eyebrow">{esc(eyebrow)}</div>'
        f'<h1>{title_html}</h1><p>{esc(desc)}</p><div class="lp-chips">{chips_html}</div>'
        '<div class="lp-orb"><div class="lp-ring two"></div><div class="lp-ring"></div>'
        '<div class="lp-cc">CC</div>'
        '<div class="lp-dot a"></div><div class="lp-dot b"></div><div class="lp-dot c"></div></div></div>'
    )


def page_header(title, subtitle=""):
    """Front-page style hero card used at the top of every inner page."""
    key = title.split(" ", 1)[1] if " " in title else title
    accent, eyebrow, chips = PAGE_STYLE.get(key, ("#3b6bff", "CAMPUSCONNECT", []))
    words = esc(key).split(" ")
    title_html = " ".join(words[:-1] + [f"<span>{words[-1]}</span>"]) if len(words) > 1 else f"<span>{words[0]}</span>"
    st.markdown(
        f"<style>:root{{--pc:{accent};}}</style>" + hero_card(eyebrow, title_html, subtitle, chips, small=True),
        unsafe_allow_html=True,
    )
    show_flash()


def app_shell():
    user = st.session_state.user
    st.markdown(LANDING_CSS, unsafe_allow_html=True)
    st.markdown(APP_CSS, unsafe_allow_html=True)
    st.markdown(THREE_D_CSS, unsafe_allow_html=True)
    components.html(TILT_JS, height=0)

    brand_col, menu_col = st.columns([5, 1.5])
    with brand_col:
        st.markdown(
            '<div class="lp-nav" style="padding:6px 6px 0"><div class="lp-brand">'
            '<div class="lp-brand-icon">🤖</div>'
            '<div class="lp-brand-name">Campus<b>Connect</b></div></div></div>',
            unsafe_allow_html=True,
        )
    with menu_col:
        stats = user_stats(user["id"])
        with st.popover(f"👤 {user['name'].split()[0]} · Lv {stats['level']}", use_container_width=True):
            st.markdown(f"**{user['name']}**")
            st.caption(f"{user['year']} • {user['branch']} • ⚡ {stats['xp']} XP")
            if st.button("🪪 My Profile", key="pop_profile", use_container_width=True):
                st.session_state.page = "My Profile"
                st.rerun()
            key = st.text_input("Gemini API key", type="password", placeholder="Google AI Studio key", key="pop_gemini")
            if key.strip():
                if key.strip() != st.session_state.get("gemini_key"):
                    st.session_state.working_model = ""
                    st.session_state.diag = None
                st.session_state.gemini_key = key.strip()
            st.caption("🟢 Gemini AI enabled" if gemini_enabled() else "🟡 Add a Gemini key to enable AI features")
            if gemini_enabled() and st.session_state.get("working_model"):
                st.caption(f"Model in use: {st.session_state.working_model}")
            diagnostics_panel("pop")
            if st.button("🚪 Logout", key="pop_logout", use_container_width=True):
                st.session_state.logged_in = False
                st.session_state.user = None
                st.session_state.chat = []
                st.session_state.auth_mode = "login"
                st.rerun()

    with st.container(key="topnav"):
        cols = st.columns(len(NAV))
        for i, (col, (icon, label, page)) in enumerate(zip(cols, NAV)):
            active = st.session_state.page == page
            with col:
                if st.button(f"{icon} {label}", key=f"{'navon' if active else 'nav'}_{i}", use_container_width=True):
                    st.session_state.page = page
                    st.rerun()


# ============================================================
# DASHBOARD
# ============================================================

def community_member_count(community):
    joined = sum(1 for m in load_data("memberships") if m["community_id"] == community["id"])
    return community.get("members", 0) + joined


def recommended_opportunities(user, limit=2):
    scored = []
    for o in load_data("opportunities"):
        left = days_left(o["deadline"])
        if left is not None and left < 0:
            continue
        s = overlap_score(user.get("interests", ""), f"{o['title']} {o['description']} {o['type']}")
        scored.append((s, o))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [o for s, o in scored if s > 0][:limit]


def _fcard(color, icon, title, desc):
    return (
        f'<div class="lp-fcard" style="--c:{color}"><div class="lp-ficon">{icon}</div>'
        f'<div class="lp-ftitle">{esc(title)}</div><div class="lp-fdesc">{esc(desc)}</div>'
        '<div class="lp-farrow">→</div></div>'
    )


def dashboard():
    user = st.session_state.user
    uid = user["id"]
    first = esc(user["name"].split()[0])
    st.markdown(
        "<style>:root{--pc:#3b6bff;}</style>" + hero_card(
            "WELCOME BACK • SYRUS 7.0",
            f"Hey {first}, <span>grow today.</span>",
            "Your campus dashboard for learning, mentoring, opportunities and resource reuse.",
            [("👥", "Peer Learning"), ("🎓", "Mentorship"), ("📖", "Resource Reuse"), ("✨", "AI-assisted discovery"), ("🌐", "SDG 4 + SDG 12")],
        ),
        unsafe_allow_html=True,
    )

    questions = load_data("questions")
    mentors = load_data("mentors")
    resources = load_data("resources")
    opportunities = load_data("opportunities")
    communities = load_data("communities")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💬 Questions", len(questions))
    c2.metric("🎓 Mentors", len(mentors))
    c3.metric("📖 Resources", len(resources))
    c4.metric("💼 Opportunities", len(opportunities))

    # ---- personal status + AI tip ----
    stats = user_stats(uid)
    left, right = st.columns([1, 1])
    with left:
        with st.container(border=True):
            st.markdown(f"### ⚡ Level {stats['level']}")
            st.progress(stats["into_level"] / 50, text=f"{stats['xp']} XP • {50 - stats['into_level']} XP to next level")
            st.markdown("".join(f'<span class="tag">{esc(b)}</span>' for b in badges_for(stats)), unsafe_allow_html=True)
            alerts = []
            pending = sum(1 for r in load_data("mentor_requests") if r["mentor_user_id"] == uid and r["status"] == "pending")
            if pending:
                alerts.append(f"📨 {pending} mentorship request(s) waiting for you.")
            my_q_ids = {q["id"] for q in questions if q["user_id"] == uid}
            new_ans = sum(1 for a in load_data("answers") if a["question_id"] in my_q_ids and a["user_id"] != uid)
            if new_ans:
                alerts.append(f"💬 {new_ans} answer(s) on your questions.")
            accepted = sum(1 for r in load_data("mentor_requests") if r["mentee_id"] == uid and r["status"] == "accepted")
            if accepted:
                alerts.append(f"🎉 {accepted} mentor(s) accepted your request.")
            for a in alerts:
                st.caption(a)
            if not alerts:
                st.caption("✅ You're all caught up.")
    with right:
        with st.container(border=True):
            st.markdown("### ✨ Your AI campus tip")
            tip = st.session_state.get("daily_tip")
            if tip and tip[0] == str(date.today()):
                st.markdown(tip[1])
            else:
                st.caption("Get one personalised, actionable tip based on your branch, year and interests.")
            if st.button("✨ Generate today's tip", key="dash_tip", use_container_width=True):
                if not gemini_enabled():
                    st.warning("Add your Gemini key in the profile menu (top-right).")
                else:
                    with st.spinner("Thinking..."):
                        text, err = ask_gemini(
                            "Give ONE short, practical, motivating tip (max 60 words) for this student to make progress "
                            "this week. End with one concrete 15-minute action.\n" + profile_text(user)
                        )
                    if text:
                        st.session_state.daily_tip = (str(date.today()), text)
                        st.rerun()
                    else:
                        st.warning(f"⚠️ {err}")

    st.markdown("### 🚀 Jump in")
    shortcuts = [
        ("#3b6bff", "🎓", "AI Mentor", "Get personalized guidance, study plans and instant answers.", "AI Campus Assistant"),
        ("#34d399", "📖", "Resources", "Access notes, PDFs, past papers and useful study material.", "Resource Exchange"),
        ("#fb923c", "💼", "Opportunities", "Find internships, hackathons, jobs and more.", "Opportunity Hub"),
        ("#a855f7", "👥", "Community", "Connect, discuss and grow together.", "Communities"),
    ]
    cols = st.columns(4)
    for i, (col, (color, icon, title, desc, page)) in enumerate(zip(cols, shortcuts)):
        with col:
            st.markdown(_fcard(color, icon, title, desc), unsafe_allow_html=True)
            if st.button(f"Open {title} →", key=f"dash_open_{i}", use_container_width=True):
                st.session_state.page = page
                st.rerun()

    # ---- recommendations ----
    recs = recommended_opportunities(user)
    if recs:
        st.markdown("### 🎯 Recommended for you")
        rc = st.columns(len(recs))
        for col, o in zip(rc, recs):
            with col:
                with st.container(border=True):
                    st.markdown(f"**{o['title']}**")
                    st.caption(f"🏷️ {o['type']} • ⏳ {o['deadline']}")
                    st.write(o["description"])

    # ---- insights ----
    st.markdown("### 📊 Campus pulse")
    a, b = st.columns([1.3, 1])
    with a:
        with st.container(border=True):
            st.markdown("**Questions by category**")
            if questions:
                counts = {c: sum(1 for q in questions if q["category"] == c) for c in QA_CATEGORIES}
                counts = {k: v for k, v in counts.items() if v}
                st.bar_chart(pd.DataFrame({"Questions": counts}))
            else:
                st.caption("No questions yet — ask the first one!")
    with b:
        with st.container(border=True):
            st.markdown("**🏅 Top contributors**")
            top, _ = leaderboard(5)
            if top:
                st.dataframe(pd.DataFrame(top), hide_index=True, use_container_width=True)
            else:
                st.caption("No students yet.")

    st.markdown("### 👥 Popular Communities")
    palette = ["#3b6bff", "#34d399", "#fb923c", "#a855f7", "#43d9ff", "#f472b6"]
    grid = '<div class="lp-grid three">'
    for i, c in enumerate(communities[:6]):
        grid += (
            f'<div class="lp-fcard" style="--c:{palette[i % len(palette)]}"><div class="lp-ficon">{esc(c["icon"])}</div>'
            f'<div class="lp-ftitle">{esc(c["name"])}</div><div class="lp-fdesc">{esc(c["description"])}<br>'
            f'<b style="color:#dff3ff">👥 {community_member_count(c)} members</b></div>'
            '<div class="lp-farrow">→</div></div>'
        )
    st.markdown(grid + "</div>", unsafe_allow_html=True)


# ============================================================
# ANONYMOUS Q&A
# ============================================================

def similar_questions(title, questions, limit=3):
    """Duplicate detection — works offline, no AI needed."""
    t = title.lower().strip()
    if len(t) < 8:
        return []
    words_a = set(re.findall(r"\w{4,}", t))
    scored = []
    for q in questions:
        qt = q["title"].lower()
        ratio = difflib.SequenceMatcher(None, t, qt).ratio()
        words_b = set(re.findall(r"\w{4,}", qt))
        jac = len(words_a & words_b) / len(words_a | words_b) if (words_a | words_b) else 0
        score = max(ratio, jac)
        if score >= 0.45:
            scored.append((score, q))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [q for _, q in scored[:limit]]


def _post_question():
    user = st.session_state.user
    title = st.session_state.get("q_title", "").strip()
    desc = st.session_state.get("q_desc", "").strip()
    cat = st.session_state.get("q_cat", QA_CATEGORIES[0])
    if not title or not desc:
        flash("warning", "Please enter your question.")
        return
    ok, reason = moderate(title + " " + desc)
    if not ok:
        flash("error", reason)
        return
    questions = load_data("questions")
    questions.append({
        "id": next_id(questions), "title": title, "description": desc, "category": cat,
        "user_id": user["id"], "created_at": now(), "views": 0,
    })
    save_data("questions", questions)
    st.session_state.q_title = ""
    st.session_state.q_desc = ""
    flash("success", "Your question has been posted anonymously! (+5 XP)")


def _post_answer(qid):
    user = st.session_state.user
    key = f"ans_{qid}"
    body = st.session_state.get(key, "").strip()
    if not body:
        flash("warning", "Write an answer first.")
        return
    ok, reason = moderate(body)
    if not ok:
        flash("error", reason)
        return
    answers = load_data("answers")
    answers.append({
        "id": next_id(answers), "question_id": qid, "user_id": user["id"], "author_name": user["name"],
        "body": body, "created_at": now(), "upvotes": [], "best": False,
    })
    save_data("answers", answers)
    st.session_state[key] = ""
    flash("success", "Answer posted! (+10 XP)")


def anonymous_qa():
    user = st.session_state.user
    page_header("💬 Anonymous Q&A", "Ask questions without publicly revealing your identity.")

    with st.expander("➕ Ask a New Question", expanded=True):
        title = st.text_input("Question Title", placeholder="Example: How should I start learning Python?", key="q_title")
        description = st.text_area("Describe your question", placeholder="Explain your problem...", key="q_desc")
        category = st.selectbox("Category", QA_CATEGORIES, key="q_cat")

        dupes = similar_questions(title, load_data("questions"))
        if dupes:
            st.info("🔁 Similar questions already exist — maybe your answer is already here:\n\n"
                    + "\n".join(f"- {d['title']}" for d in dupes))

        p1, p2 = st.columns(2)
        p1.button("🚀 Post Anonymously", use_container_width=True, on_click=_post_question)
        improve = p2.button("✨ Improve my question with AI", use_container_width=True)

        if improve:
            if not title.strip() and not description.strip():
                st.warning("Write a rough question first.")
            elif not gemini_enabled():
                st.warning("Add your Gemini key in the profile menu (top-right).")
            else:
                with st.spinner("Polishing..."):
                    text, err = ask_gemini(
                        "Rewrite this student question so it is specific, complete and easy to answer. "
                        "Return: **Better title**, **Better description**, and **What to include** (2 bullets).\n\n"
                        f"Title: {title}\nDescription: {description}\nCategory: {category}"
                    )
                show_ai(text, err)

    st.divider()

    questions = load_data("questions")
    answers = load_data("answers")

    f1, f2, f3 = st.columns([2.2, 1, 1])
    search = f1.text_input("🔎 Search questions", placeholder="Search Python, AI, placements...")
    cat_filter = f2.selectbox("Category", ["All"] + QA_CATEGORIES, key="q_filter")
    sort_by = f3.selectbox("Sort", ["Newest", "Most answered", "Unanswered"], key="q_sort")

    if search:
        s = search.lower()
        questions = [
            q for q in questions
            if s in (q["title"] + " " + q["description"] + " " + q["category"]).lower()
        ]
    if cat_filter != "All":
        questions = [q for q in questions if q["category"] == cat_filter]

    ans_count = {q["id"]: sum(1 for a in answers if a["question_id"] == q["id"]) for q in questions}
    if sort_by == "Most answered":
        questions = sorted(questions, key=lambda q: ans_count[q["id"]], reverse=True)
    elif sort_by == "Unanswered":
        questions = [q for q in reversed(questions) if ans_count[q["id"]] == 0]
    else:
        questions = list(reversed(questions))

    if not questions:
        st.info("No questions found. Be the first to ask!")

    for q in questions:
        with st.container(border=True):
            st.markdown(f"### 💬 {q['title']}")
            mine = " • ✏️ Your question" if q["user_id"] == user["id"] else ""
            st.caption(f"🕒 {q['created_at']}  •  🏷️ {q['category']}  •  👤 Anonymous Student{mine}")
            st.write(q["description"])

            question_answers = [a for a in answers if a["question_id"] == q["id"]]
            question_answers.sort(key=lambda a: (not a.get("best"), -len(a.get("upvotes", []))))
            if question_answers:
                st.markdown(f"**💡 {len(question_answers)} Answer(s)**")
                for a in question_answers:
                    badge = "✅ **Best answer** • " if a.get("best") else ""
                    st.info(f"{badge}🎓 {a['author_name']} ({a['created_at']})\n\n{a['body']}")
                    v1, v2, _ = st.columns([1, 1.4, 4])
                    votes = a.get("upvotes", [])
                    voted = user["id"] in votes
                    if v1.button(f"{'👍' if not voted else '💙'} {len(votes)}", key=f"vote_{a['id']}"):
                        if a["user_id"] == user["id"]:
                            st.toast("You can't upvote your own answer.", icon="🙅")
                        else:
                            a["upvotes"] = [x for x in votes if x != user["id"]] if voted else votes + [user["id"]]
                            save_data("answers", answers)
                            st.rerun()
                    if q["user_id"] == user["id"] and not a.get("best"):
                        if v2.button("⭐ Mark best", key=f"best_{a['id']}"):
                            for other in answers:
                                if other["question_id"] == q["id"]:
                                    other["best"] = False
                            a["best"] = True
                            save_data("answers", answers)
                            st.rerun()

            st.text_input("Add an answer", key=f"ans_{q['id']}", placeholder="Share what helped you...")
            c1, c2, c3, c4 = st.columns([1, 1, 1.3, 2.7])
            c1.button("💡 Answer", key=f"ans_btn_{q['id']}", on_click=_post_answer, args=(q["id"],))
            if c2.button("🚩 Report", key=f"rep_{q['id']}"):
                reports = load_data("reports")
                reports.append({
                    "id": next_id(reports), "target": "question", "target_id": q["id"],
                    "reporter_id": user["id"], "created_at": now(), "status": "open",
                })
                save_data("reports", reports)
                st.toast("Reported to moderators", icon="🚩")

            if gemini_enabled():
                if c3.button("🤖 AI hint", key=f"hint_{q['id']}"):
                    with st.spinner("Thinking..."):
                        text, err = ask_gemini(
                            "A student asked this campus question. Give a short, accurate, helpful answer (max 150 words) "
                            "the community can build on. Do not invent facts.\n\n"
                            f"Title: {q['title']}\nDetails: {q['description']}\nCategory: {q['category']}"
                        )
                    show_ai(text, err)
                if question_answers and c4.button("✨ AI summary", key=f"sum_{q['id']}"):
                    thread = "QUESTION: " + q["title"] + "\n" + q["description"]
                    for a in question_answers:
                        thread += "\nANSWER: " + a["body"]
                    with st.spinner("Summarizing..."):
                        text, err = ask_gemini(
                            "Summarize this peer-learning discussion into Key suggestions and Next steps. Be concise.\n\n" + thread[:5000]
                        )
                    show_ai(text, err)

# ============================================================
# MENTOR HUB
# ============================================================

def mentor_hub():
    user = st.session_state.user
    page_header("🤝 Mentor Hub", "Connect with seniors and peers who can guide your next step.")

    mentors = load_data("mentors")
    mine = next((m for m in mentors if m["user_id"] == user["id"]), None)

    with st.expander("🎓 Become a mentor" if not mine else "✏️ Edit my mentor profile"):
        skills = st.text_input("Skills", value=mine["skills"] if mine else "", placeholder="DSA, Python, Cloud...")
        about = st.text_area("About your mentoring", value=mine["about"] if mine else "")
        availability = st.text_input("Availability", value=mine["availability"] if mine else "", placeholder="Saturday evenings")
        if st.button("Save mentor profile"):
            if not skills.strip():
                st.warning("Add at least one skill.")
            else:
                if mine:
                    mine.update({"skills": skills.strip(), "about": about.strip(), "availability": availability.strip()})
                else:
                    mentors.append({
                        "id": next_id(mentors), "user_id": user["id"], "name": user["name"],
                        "year": user["year"], "branch": user["branch"],
                        "skills": skills.strip(), "about": about.strip(),
                        "availability": availability.strip(),
                    })
                save_data("mentors", mentors)
                st.success("Mentor profile saved.")
                st.rerun()

    requests_ = load_data("mentor_requests")

    if mine:
        incoming = [r for r in requests_ if r["mentor_user_id"] == user["id"] and r["status"] == "pending"]
        if incoming:
            st.markdown("### 📨 Requests for you")
            for r in incoming:
                with st.container(border=True):
                    st.write(f"**{r['mentee_name']}** — {r['message'] or 'wants to connect'}")
                    a, b, _ = st.columns([1, 1, 4])
                    if a.button("Accept", key=f"acc_{r['id']}"):
                        r["status"] = "accepted"
                        save_data("mentor_requests", requests_)
                        st.rerun()
                    if b.button("Decline", key=f"dec_{r['id']}"):
                        r["status"] = "declined"
                        save_data("mentor_requests", requests_)
                        st.rerun()

    connections = [r for r in requests_ if r["status"] == "accepted" and user["id"] in (r["mentee_id"], r["mentor_user_id"])]
    if connections:
        st.markdown("### ✅ Your connections")
        for r in connections:
            other_id = r["mentor_user_id"] if r["mentee_id"] == user["id"] else r["mentee_id"]
            other = get_user(other_id)
            role = "your mentor" if r["mentee_id"] == user["id"] else "your mentee"
            st.caption(f"🤝 {other['name'] if other else 'Student'} — {role}")

    st.markdown("### 🔍 Mentors for you")
    others = [m for m in mentors if m["user_id"] != user["id"]]
    others.sort(key=lambda m: overlap_score(user.get("interests", ""), m["skills"] + " " + m["about"]), reverse=True)

    if not others:
        st.info("No mentors yet. Be the first to create a mentor profile!")

    for m in others:
        score = overlap_score(user.get("interests", ""), m["skills"] + " " + m["about"])
        match_pct = min(99, 55 + score * 15)
        with st.container(border=True):
            st.markdown(f"### 🎓 {m['name']}")
            st.caption(f"{m['year']} • {m['branch']} • ⚡ {match_pct}% match")
            st.progress(match_pct / 100)
            st.write(m["about"] or "—")
            st.markdown(
                "".join(f'<span class="tag">{esc(s)}</span>' for s in m["skills"].split(",") if s.strip()),
                unsafe_allow_html=True,
            )
            st.caption(f"🗓️ Available: {m['availability'] or 'Not specified'}")

            existing = next((r for r in requests_ if r["mentee_id"] == user["id"] and r["mentor_user_id"] == m["user_id"]), None)
            if existing:
                st.info(f"Request status: **{existing['status']}**")
            else:
                msg = st.text_input("Why do you want to connect?", key=f"mmsg_{m['id']}")
                col1, col2, col3 = st.columns([1, 1, 1])
                if col1.button("📨 Request mentorship", key=f"mreq_{m['id']}"):
                    ok, reason = moderate(msg)
                    if not ok:
                        st.error(reason)
                    else:
                        requests_.append({
                            "id": next_id(requests_), "mentor_user_id": m["user_id"],
                            "mentee_id": user["id"], "mentee_name": user["name"],
                            "message": msg.strip(), "status": "pending", "created_at": now(),
                        })
                        save_data("mentor_requests", requests_)
                        st.toast("Mentorship request sent", icon="📨")
                        st.rerun()
                if gemini_enabled():
                    if col2.button("🤖 Why this mentor?", key=f"mfit_{m['id']}"):
                        text, err = ask_gemini(
                            "Match this student with this mentor in 2 short sentences: why they fit, and one thing the mentor can help with.\n"
                            f"Student interests: {user.get('interests', '')}\n"
                            f"Mentor skills: {m['skills']}\nMentor bio: {m['about']}"
                        )
                        show_ai(text, err)
                    if col3.button("✍️ Draft my message", key=f"mdraft_{m['id']}"):
                        text, err = ask_gemini(
                            "Write a polite, specific 3-sentence mentorship request from a student to a senior. No placeholders.\n"
                            f"Student:\n{profile_text(user)}\nMentor skills: {m['skills']}\nMentor bio: {m['about']}"
                        )
                        show_ai(text, err)

# ============================================================
# COMMUNITIES  (+ Peer / teammate matching)
# ============================================================

def peer_match_tab(user):
    st.caption("Find classmates with overlapping interests — study buddies, hackathon teammates, project partners.")
    others = [u for u in load_data("users") if u["id"] != user["id"]]
    if not others:
        st.info("No other students yet — invite your friends!")
        return
    scored = []
    for u in others:
        s = overlap_score(user.get("interests", ""), u.get("interests", "")) + overlap_score(u.get("interests", ""), user.get("interests", ""))
        shared = sorted(set(split_tags(user.get("interests", ""))) & set(split_tags(u.get("interests", ""))))
        scored.append((s, shared, u))
    scored.sort(key=lambda x: x[0], reverse=True)
    for s, shared, u in scored[:8]:
        pct = min(98, 40 + s * 14) if s else 35
        with st.container(border=True):
            st.markdown(f"### 🤝 {u['name']}")
            st.caption(f"{u['year']} • {u['branch']} • ⚡ {pct}% match")
            st.markdown(
                "".join(f'<span class="tag">{esc(t)}</span>' for t in u.get("interests", "").split(",") if t.strip()),
                unsafe_allow_html=True,
            )
            if shared:
                st.caption("Shared interests: " + ", ".join(shared))
            if gemini_enabled() and st.button("🤖 Icebreaker + project idea", key=f"peer_{u['id']}"):
                with st.spinner("Thinking..."):
                    text, err = ask_gemini(
                        "Write a friendly 2-sentence icebreaker message from student A to student B, then suggest ONE small "
                        "project they could build together this month. Keep it under 90 words, no placeholders.\n"
                        f"Student A:\n{profile_text(user)}\nStudent B:\n{profile_text(u)}"
                    )
                show_ai(text, err)


def communities_page():
    user = st.session_state.user
    page_header("👥 Communities", "Join circles around your interests and learn together.")

    tab_c, tab_p = st.tabs(["👥 Communities", "🤝 Peer & Teammate Match"])

    with tab_p:
        peer_match_tab(user)

    with tab_c:
        communities = load_data("communities")
        memberships = load_data("memberships")
        joined_ids = {m["community_id"] for m in memberships if m["user_id"] == user["id"]}

        st.caption(f"You've joined {len(joined_ids)} of {len(communities)} communities.")

        cols = st.columns(2)
        for i, c in enumerate(communities):
            with cols[i % 2]:
                with st.container(border=True):
                    st.markdown(f"### {c['icon']} {c['name']}")
                    st.write(c["description"])
                    st.caption(f"👥 {community_member_count(c)} members")
                    if c["id"] in joined_ids:
                        if st.button("✓ Joined — click to leave", key=f"leave_{c['id']}", use_container_width=True):
                            memberships = [m for m in memberships if not (m["user_id"] == user["id"] and m["community_id"] == c["id"])]
                            save_data("memberships", memberships)
                            st.rerun()
                    else:
                        if st.button("Join community", key=f"join_{c['id']}", use_container_width=True):
                            memberships.append({"user_id": user["id"], "community_id": c["id"], "joined_at": now()})
                            save_data("memberships", memberships)
                            st.rerun()

# ============================================================
# RESOURCE EXCHANGE
# ============================================================

def _ai_fill_description():
    title = st.session_state.get("res_title", "").strip()
    if not title:
        st.session_state.res_err = "Enter an item title first."
        return
    text, err = ask_gemini(
        "Write a clear, honest 2-sentence listing description for a student resource exchange. "
        "No emojis, no invented specs, no placeholders.\n"
        f"Item: {title}\nCategory: {st.session_state.get('res_cat', '')}\n"
        f"Exchange type: {st.session_state.get('res_kind', '')}"
    )
    if text:
        st.session_state.res_desc = text
        st.session_state.res_err = ""
    else:
        st.session_state.res_err = err


def resource_exchange():
    user = st.session_state.user
    page_header("📚 Resource Exchange", "Reuse more, buy less. Share books, notes, kits and more.")

    with st.expander("➕ Share a resource"):
        title = st.text_input("Item title", key="res_title")
        desc = st.text_area("Description", key="res_desc")
        kind = st.selectbox("Exchange type", RESOURCE_TYPES, key="res_kind")
        category = st.text_input("Category", placeholder="Books, Notes, Electronics...", key="res_cat")
        price = st.number_input("Price (₹)", min_value=0, value=0, step=10)
        b1, b2 = st.columns(2)
        if gemini_enabled():
            b1.button("✨ Write description with AI", on_click=_ai_fill_description, use_container_width=True)
        if st.session_state.get("res_err"):
            st.warning(st.session_state.res_err)
        if b2.button("Publish resource", use_container_width=True):
            ok, reason = moderate(title + " " + desc)
            if not title.strip():
                st.warning("Give your item a title.")
            elif not ok:
                st.error(reason)
            else:
                resources = load_data("resources")
                resources.append({
                    "id": next_id(resources), "user_id": user["id"], "owner_name": user["name"],
                    "title": title.strip(), "description": desc.strip(), "kind": kind,
                    "category": category.strip(), "price": int(price),
                    "status": "available", "claimed_by": None, "created_at": now(),
                })
                save_data("resources", resources)
                st.success("Resource published!")
                st.rerun()

    resources = load_data("resources")
    c1, c2, c3, c4 = st.columns(4)
    reused = sum(1 for r in resources if r["status"] != "available")
    c1.metric("Items shared", len(resources))
    c2.metric("Reused / claimed", reused)
    c3.metric("Donations", sum(1 for r in resources if r["kind"] == "Donate"))
    c4.metric("♻️ Reuse rate", f"{int(100 * reused / len(resources)) if resources else 0}%")
    st.caption("♻️ SDG 12: resource reuse reduces unnecessary buying and waste.")

    f1, f2 = st.columns([2, 1])
    query = f1.text_input("🔎 Search resources")
    type_filter = f2.selectbox("Type", ["All"] + RESOURCE_TYPES, key="res_filter")
    rows = [r for r in resources if r["status"] == "available"]
    if type_filter != "All":
        rows = [r for r in rows if r["kind"] == type_filter]
    if query.strip():
        q = query.lower()
        rows = [r for r in rows if q in (r["title"] + " " + r["description"] + " " + r["category"]).lower()]

    if not rows:
        st.info("No available resources right now.")

    for r in reversed(rows):
        with st.container(border=True):
            st.markdown(f"### 📦 {r['title']}")
            st.caption(f"{r['kind']} • {r['category'] or 'General'} • {'₹' + str(r['price']) if r['price'] else 'Free'} • by {r['owner_name']}")
            st.write(r["description"] or "—")
            if r["user_id"] != user["id"]:
                if st.button("Request / claim", key=f"claim_{r['id']}"):
                    r["status"] = "completed" if r["kind"] in ("Donate", "Sell") else "reserved"
                    r["claimed_by"] = user["id"]
                    save_data("resources", resources)
                    st.success("Request recorded. Contact the owner to complete the exchange.")
                    st.rerun()
            else:
                st.caption("This is your listing.")

# ============================================================
# OPPORTUNITY HUB
# ============================================================

def opportunity_hub():
    user = st.session_state.user
    page_header("🏆 Opportunity Hub", "Hackathons, internships, workshops and competitions in one place.")

    with st.expander("➕ Add an opportunity"):
        title = st.text_input("Title", key="opp_title")
        kind = st.selectbox("Type", OPPORTUNITY_TYPES)
        desc = st.text_area("Description", key="opp_desc")
        deadline = st.date_input("Deadline")
        link = st.text_input("Link", value="#")
        if st.button("Publish opportunity"):
            ok, reason = moderate(title + " " + desc)
            if not title.strip():
                st.warning("Add a title.")
            elif not ok:
                st.error(reason)
            else:
                opps = load_data("opportunities")
                opps.append({
                    "id": next_id(opps), "title": title.strip(), "type": kind,
                    "description": desc.strip(), "deadline": deadline.strftime("%d %b %Y"),
                    "link": link.strip() or "#",
                })
                save_data("opportunities", opps)
                st.success("Opportunity published!")
                st.rerun()

    recs = recommended_opportunities(user, limit=3)
    if recs:
        st.markdown("### 🎯 Matched to your interests")
        st.markdown("".join(f'<span class="tag">⭐ {esc(o["title"])}</span>' for o in recs), unsafe_allow_html=True)

    f1, f2, f3 = st.columns([1.2, 1, 1])
    chosen = f1.selectbox("Filter by type", ["All"] + OPPORTUNITY_TYPES)
    sort_by = f2.selectbox("Sort", ["Closest deadline", "Newest added"])
    saved_only = f3.toggle("🔖 Saved only")

    bookmarks = load_data("bookmarks")
    saved_ids = {b["opportunity_id"] for b in bookmarks if b["user_id"] == user["id"]}

    opps = load_data("opportunities")
    if chosen != "All":
        opps = [o for o in opps if o["type"] == chosen]
    if saved_only:
        opps = [o for o in opps if o["id"] in saved_ids]
    if sort_by == "Closest deadline":
        opps.sort(key=lambda o: (days_left(o["deadline"]) is None, days_left(o["deadline"]) if days_left(o["deadline"]) is not None else 0))
    else:
        opps = list(reversed(opps))

    if not opps:
        st.info("Nothing to show here yet.")

    cols = st.columns(2)
    for i, o in enumerate(opps):
        left = days_left(o["deadline"])
        if left is None:
            urgency = ""
        elif left < 0:
            urgency = " • 🔴 Closed"
        elif left <= 7:
            urgency = f" • 🟠 {left} day(s) left"
        else:
            urgency = f" • 🟢 {left} days left"
        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(f"### {o['title']}")
                st.caption(f"🏷️ {o['type']} • ⏳ Deadline: {o['deadline']}{urgency}")
                st.write(o["description"])
                b1, b2, b3 = st.columns([1, 1, 1])
                is_saved = o["id"] in saved_ids
                if b1.button("🔖 Saved" if is_saved else "➕ Save", key=f"bm_{o['id']}"):
                    if is_saved:
                        bookmarks = [b for b in bookmarks if not (b["user_id"] == user["id"] and b["opportunity_id"] == o["id"])]
                    else:
                        bookmarks.append({"user_id": user["id"], "opportunity_id": o["id"], "saved_at": now()})
                    save_data("bookmarks", bookmarks)
                    st.rerun()
                if o.get("link") and o["link"] != "#":
                    b2.link_button("Open", o["link"])
                if gemini_enabled() and b3.button("🤖 Am I ready?", key=f"ready_{o['id']}"):
                    with st.spinner("Checking fit..."):
                        text, err = ask_gemini(
                            "In under 90 words, tell this student how well they fit this opportunity and give 2 concrete "
                            "preparation steps before the deadline.\n"
                            f"Opportunity: {o['title']} ({o['type']}) — {o['description']}. Deadline: {o['deadline']}\n"
                            f"Student:\n{profile_text(user)}"
                        )
                    show_ai(text, err)

# ============================================================
# AI CAMPUS ASSISTANT
# ============================================================

def ai_assistant():
    user = st.session_state.user
    page_header("🤖 AI Campus Assistant", "Ask about coding, studies, projects, hackathons or careers.")

    if gemini_enabled():
        model = st.session_state.get("working_model")
        st.caption("🟢 Gemini is active" + (f" • model: {model}" if model else " • model auto-detected on first message"))
    else:
        st.warning("Add your Gemini API key in the profile menu (top-right) or set GEMINI_API_KEY to chat.")

    o1, o2, o3 = st.columns([1.4, 1.2, 1])
    mode = o1.selectbox("Assistant mode", list(AI_MODES), key="ai_mode")
    use_search = o2.toggle("🌐 Use Google Search", value=True, help="Grounds answers with live web results.")
    if o3.button("🧹 Clear chat", use_container_width=True):
        st.session_state.chat = []
        st.rerun()

    for m in st.session_state.chat:
        with st.chat_message(m["role"]):
            st.markdown(m["text"])
            if m.get("sources"):
                show_sources(m["sources"])

    if not st.session_state.chat:
        st.caption("Try one of these:")
        qcols = st.columns(len(QUICK_PROMPTS))
        for i, (col, qp) in enumerate(zip(qcols, QUICK_PROMPTS)):
            if col.button(qp, key=f"qp_{i}", use_container_width=True):
                st.session_state.pending_prompt = qp
                st.rerun()

    typed = st.chat_input("Ask your AI assistant...")
    prompt = typed or st.session_state.pop("pending_prompt", None)

    if prompt and prompt.strip():
        prompt = prompt.strip()
        history = list(st.session_state.chat)
        st.session_state.last_sources = []
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            reply = st.write_stream(
                gemini_stream(
                    build_assistant_prompt(user, prompt, history),
                    use_search=use_search,
                    system=AI_MODES[mode],
                )
            )
        reply = reply if isinstance(reply, str) else str(reply)
        if reply.strip().startswith("⚠️"):
            st.session_state.ai_failed = True   # don't pollute history with errors
        else:
            st.session_state.ai_failed = False
            st.session_state.chat.append({"role": "user", "text": prompt})
            st.session_state.chat.append({
                "role": "assistant", "text": reply,
                "sources": st.session_state.get("last_sources", []),
            })
            st.rerun()

    if st.session_state.get("ai_failed"):
        with st.expander("🔬 Diagnostics — why did this fail?", expanded=True):
            st.caption("Tests which Gemini models your key can actually call.")
            diagnostics_panel("assist")

    if st.session_state.chat:
        transcript = "\n\n".join(f"{m['role'].upper()}: {m['text']}" for m in st.session_state.chat)
        st.download_button("⬇️ Download chat", transcript, file_name="campusconnect_chat.md", key="dl_chat")

# ============================================================
# AI TOOLS
# ============================================================

def run_tool(key, label, prompt, ready=True, hint=""):
    if st.button(label, key=f"run_{key}", use_container_width=True):
        if not gemini_enabled():
            st.warning("Add your Gemini key in the profile menu (top-right).")
        elif not ready:
            st.warning(hint or "Please fill in the required fields.")
        else:
            with st.spinner("Working on it..."):
                text, err = ask_gemini(prompt)
            st.session_state[f"out_{key}"] = text if text else f"⚠️ {err}"
    out = st.session_state.get(f"out_{key}")
    if out:
        st.markdown(out)
        st.download_button("⬇️ Download as Markdown", out, file_name=f"{key}.md", key=f"dl_{key}")


def read_uploaded_text(upload):
    """Read .txt/.md/.pdf uploads. Returns (text, error)."""
    name = upload.name.lower()
    data = upload.getvalue()
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="ignore"), None
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except Exception:
            try:
                from PyPDF2 import PdfReader
            except Exception:
                return "", "PDF support needs: pip install pypdf  (or paste the text instead)."
        try:
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in reader.pages[:25]), None
        except Exception as exc:
            return "", f"Could not read this PDF: {str(exc)[:120]}"
    return "", "Unsupported file type."


def study_kit_tab(user):
    st.caption("Turn lecture notes into a summary, key terms and an interactive quiz in one click.")
    mode = st.radio("Source", ["Paste text", "Upload .txt / .md / .pdf"], horizontal=True, key="kit_mode")
    text = ""
    if mode == "Paste text":
        text = st.text_area("Paste your notes / chapter text", height=200, key="kit_text")
    else:
        up = st.file_uploader("Upload notes", type=["txt", "md", "pdf"], key="kit_file")
        if up:
            text, err = read_uploaded_text(up)
            if err:
                st.warning(err)
            elif text.strip():
                st.caption(f"Loaded {len(text):,} characters from {up.name}")
    n_q = st.slider("Quiz questions", 3, 10, 5, key="kit_n")

    if st.button("📚 Generate study kit", key="kit_go", use_container_width=True):
        if not gemini_enabled():
            st.warning("Add your Gemini key in the profile menu (top-right).")
        elif len(text.strip()) < 80:
            st.warning("Add at least a few lines of notes first.")
        else:
            body = text.strip()[:9000]
            with st.spinner("Summarizing your notes..."):
                summary, err1 = ask_gemini(
                    "You are a study coach. From the notes below produce Markdown with: **Summary** (5 bullets), "
                    "**Key terms** (up to 8, one line each), and **Likely exam questions** (3). Use only the notes.\n\n" + body
                )
            with st.spinner("Building your quiz..."):
                quiz, err2 = ask_gemini_json(
                    f"Create {n_q} multiple-choice questions from the notes. Return ONLY a JSON array. Each item: "
                    '{"q": "question", "options": ["A","B","C","D"], "answer": 0, "why": "one-line explanation"} '
                    "where answer is the 0-based index of the correct option. Use only the notes.\n\n" + body
                )
            valid = []
            if isinstance(quiz, list):
                for item in quiz:
                    if (isinstance(item, dict) and isinstance(item.get("options"), list) and len(item["options"]) >= 2
                            and isinstance(item.get("answer"), int) and 0 <= item["answer"] < len(item["options"]) and item.get("q")):
                        valid.append(item)
            st.session_state.kit = {"summary": summary or f"⚠️ {err1}", "quiz": valid, "checked": False}
            for i in range(20):
                st.session_state.pop(f"kit_q_{i}", None)
            if not valid and err2:
                st.warning(f"Quiz could not be generated: {err2}")

    kit = st.session_state.get("kit")
    if not kit:
        return
    st.markdown(kit["summary"])
    st.download_button("⬇️ Download summary", kit["summary"], file_name="study_kit.md", key="kit_dl")
    if kit["quiz"]:
        st.markdown("### 🧪 Test yourself")
        for i, item in enumerate(kit["quiz"]):
            st.radio(f"**Q{i + 1}. {item['q']}**", item["options"], index=None, key=f"kit_q_{i}")
        if st.button("✅ Check my answers", key="kit_check"):
            kit["checked"] = True
        if kit["checked"]:
            score = 0
            for i, item in enumerate(kit["quiz"]):
                picked = st.session_state.get(f"kit_q_{i}")
                correct = item["options"][item["answer"]]
                if picked == correct:
                    score += 1
                    st.success(f"Q{i + 1}: Correct ✅ — {item.get('why', '')}")
                else:
                    st.error(f"Q{i + 1}: Answer is **{correct}** — {item.get('why', '')}")
            st.markdown(f"### 🎯 Score: {score}/{len(kit['quiz'])}")
            if score == len(kit["quiz"]):
                st.balloons()


def ai_tools():
    user = st.session_state.user
    page_header("🧰 AI Tools", "Resume review, hackathon ideas, study plans, interview prep and study kits — powered by Gemini.")

    t1, t2, t3, t4, t5 = st.tabs(["📄 Resume Reviewer", "💡 Hackathon Ideas", "🗓️ Study Planner", "🎤 Interview Prep", "📚 Study Kit"])

    with t1:
        role = st.text_input("Target role", placeholder="Python Developer Intern", key="rv_role")
        resume = st.text_area("Paste your resume text", height=220, key="rv_text")
        prompt = (
            "You are a strict but kind resume reviewer for engineering students in India. Review the resume for the target role. "
            "Return in Markdown: 1) Score out of 100 with a one-line reason, 2) Top 3 strengths, 3) Top 5 fixes, "
            "4) Three rewritten bullet points using action verbs and measurable impact (do not invent numbers; use placeholders like [X%]), "
            "5) Missing ATS keywords.\n\n"
            f"Target role: {role}\n\nResume:\n{resume[:6000]}"
        )
        run_tool("resume", "📄 Review my resume", prompt, ready=bool(resume.strip()), hint="Paste your resume first.")

    with t2:
        theme = st.text_input("Theme / problem area", placeholder="Education, Healthcare, Sustainability...", key="hk_theme")
        skills = st.text_input("Team skills", value=user.get("interests", ""), key="hk_skills")
        c1, c2 = st.columns(2)
        team = c1.slider("Team size", 1, 6, 4, key="hk_team")
        hours = c2.select_slider("Time available", ["6 hrs", "12 hrs", "24 hrs", "36 hrs", "48 hrs"], value="24 hrs", key="hk_hours")
        prompt = (
            "Generate 3 original, realistic hackathon project ideas. For each: name, one-line pitch, problem, "
            "MVP scope that fits the time, tech stack (use the team's skills), role split for the team, "
            "a demo plan, and which UN SDG it supports. Keep each idea under 160 words.\n\n"
            f"Theme: {theme or 'open'}\nTeam skills: {skills}\nTeam size: {team}\nTime: {hours}"
        )
        run_tool("hackathon", "💡 Generate ideas", prompt)

    with t3:
        subjects = st.text_input("Subjects / topics", placeholder="DBMS, OS, DSA", key="sp_subjects")
        c1, c2 = st.columns(2)
        exam = c1.date_input("Exam / target date", value=date.today(), key="sp_date")
        hrs = c2.slider("Study hours per day", 1, 10, 3, key="sp_hours")
        days = max((exam - date.today()).days, 1)
        prompt = (
            "Create a realistic day-by-day study plan as a Markdown table (Day, Focus, Tasks, Hours). "
            "Include revision days, short breaks and a final mock-test day. If more than 14 days remain, plan week-by-week "
            "for the first weeks and day-by-day for the final 10 days.\n\n"
            f"Subjects: {subjects}\nDays available: {days}\nHours/day: {hrs}\n{profile_text(user)}"
        )
        run_tool("studyplan", "🗓️ Build my plan", prompt, ready=bool(subjects.strip()), hint="Enter at least one subject.")

    with t4:
        irole = st.text_input("Role you're preparing for", placeholder="Software Engineer Intern", key="ip_role")
        level = st.selectbox("Round", ["HR / Behavioural", "Technical", "Mixed"], key="ip_level")
        prompt = (
            "Act as an interviewer. Give 8 likely interview questions for this role and round. For each question add: "
            "what the interviewer looks for, and a short model-answer outline (3 bullets). End with 3 smart questions the "
            "candidate can ask the interviewer.\n\n"
            f"Role: {irole}\nRound: {level}\n{profile_text(user)}"
        )
        run_tool("interview", "🎤 Prepare me", prompt, ready=bool(irole.strip()), hint="Enter a role first.")

    with t5:
        study_kit_tab(user)

# ============================================================
# STUDENT GROWTH PATH
# ============================================================

def growth_path():
    user = st.session_state.user
    page_header("🛤️ Student Growth Path", "Complete these milestones to grow with the campus community.")

    uid = user["id"]
    steps = [
        ("Set your interests", bool(user.get("interests", "").strip()), "My Profile"),
        ("Join a community", any(m["user_id"] == uid for m in load_data("memberships")), "Communities"),
        ("Ask your first question", any(q["user_id"] == uid for q in load_data("questions")), "Anonymous Q&A"),
        ("Help someone with an answer", any(a["user_id"] == uid for a in load_data("answers")), "Anonymous Q&A"),
        ("Request a mentor", any(r["mentee_id"] == uid for r in load_data("mentor_requests")), "Mentor Hub"),
        ("Share or claim a resource", any(r["user_id"] == uid or r.get("claimed_by") == uid for r in load_data("resources")), "Resource Exchange"),
        ("Save an opportunity", any(b["user_id"] == uid for b in load_data("bookmarks")), "Opportunity Hub"),
    ]
    done = sum(1 for _, ok, _ in steps if ok)
    st.progress(done / len(steps), text=f"{done} of {len(steps)} milestones complete")
    if done == len(steps):
        st.success("🎉 All milestones complete — you're a CampusConnect champion!")

    for label, ok, page in steps:
        with st.container(border=True):
            a, b = st.columns([5, 1])
            a.markdown(f"{'✅' if ok else '⬜'} **{label}**")
            if not ok and b.button("Go", key=f"gp_{label}"):
                st.session_state.page = page
                st.rerun()

    if gemini_enabled():
        if st.button("🤖 Get my AI weekly plan", use_container_width=True):
            with st.spinner("Planning..."):
                text, err = ask_gemini(
                    "Act as a campus success coach. Give a concise, practical 4-step weekly plan for this student.\n"
                    f"{profile_text(user)}"
                    f"Completed milestones: {', '.join(l for l, ok, _ in steps if ok) or 'none'}\n"
                    f"Pending milestones: {', '.join(l for l, ok, _ in steps if not ok) or 'none'}"
                )
            show_ai(text, err)

# ============================================================
# IMPACT DASHBOARD  (SDG 4 + SDG 12 — the "so what?" slide for judges)
# ============================================================

def impact_metrics():
    users = load_data("users")
    questions = load_data("questions")
    answers = load_data("answers")
    resources = load_data("resources")
    requests_ = load_data("mentor_requests")
    reused = [r for r in resources if r["status"] != "available"]
    answered = {a["question_id"] for a in answers}
    return {
        "students": len(users),
        "questions": len(questions),
        "answers": len(answers),
        "answer_rate": int(100 * len({q["id"] for q in questions} & answered) / len(questions)) if questions else 0,
        "reused": len(reused),
        "listed": len(resources),
        "saved_inr": sum((r.get("price") or ASSUMED_ITEM_VALUE_INR) for r in reused),
        "co2": round(len(reused) * ASSUMED_CO2_KG_PER_REUSED_ITEM, 1),
        "connections": sum(1 for r in requests_ if r["status"] == "accepted"),
        "mentors": len(load_data("mentors")),
    }


def impact_page():
    user = st.session_state.user
    page_header("🌍 Impact Dashboard", "Measurable outcomes for SDG 4 (Quality Education) and SDG 12 (Responsible Consumption).")

    m = impact_metrics()
    st.markdown("#### 🎓 SDG 4 — Quality Education")
    a, b, c, d = st.columns(4)
    a.metric("Active students", m["students"])
    b.metric("Peer answers shared", m["answers"])
    c.metric("Questions answered", f"{m['answer_rate']}%")
    d.metric("Mentor connections", m["connections"])

    st.markdown("#### ♻️ SDG 12 — Responsible Consumption")
    a, b, c, d = st.columns(4)
    a.metric("Items listed", m["listed"])
    b.metric("Items reused", m["reused"])
    c.metric("₹ saved (est.)", f"₹{m['saved_inr']:,}")
    d.metric("CO₂ avoided (est.)", f"{m['co2']} kg")
    st.caption(f"Estimates: unpriced items valued at ₹{ASSUMED_ITEM_VALUE_INR}; "
               f"{ASSUMED_CO2_KG_PER_REUSED_ITEM} kg CO₂e avoided per reused item (assumption — adjust at the top of the file).")

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("**📈 Peer-learning activity**")
            rows = []
            for q in load_data("questions"):
                d_ = parse_dt(q["created_at"])
                if d_:
                    rows.append({"Date": d_.date(), "Type": "Questions"})
            for a_ in load_data("answers"):
                d_ = parse_dt(a_["created_at"])
                if d_:
                    rows.append({"Date": d_.date(), "Type": "Answers"})
            if rows:
                df = pd.DataFrame(rows).groupby(["Date", "Type"]).size().unstack(fill_value=0)
                st.bar_chart(df)
            else:
                st.caption("No activity yet.")
    with right:
        with st.container(border=True):
            st.markdown("**♻️ Resources by exchange type**")
            res = load_data("resources")
            if res:
                counts = pd.Series([r["kind"] for r in res]).value_counts()
                st.bar_chart(counts)
            else:
                st.caption("No resources yet.")

    st.markdown("#### 🛡️ Moderation queue")
    reports = [r for r in load_data("reports") if r["status"] == "open"]
    if not reports:
        st.caption("✅ No open reports.")
    for r in reports:
        q = next((x for x in load_data("questions") if x["id"] == r["target_id"]), None)
        with st.container(border=True):
            st.write(f"🚩 Reported: **{q['title'] if q else '(deleted question)'}**  • {r['created_at']}")
            x, y, _ = st.columns([1, 1.2, 4])
            if x.button("Dismiss", key=f"rp_ok_{r['id']}"):
                reps = load_data("reports")
                for it in reps:
                    if it["id"] == r["id"]:
                        it["status"] = "dismissed"
                save_data("reports", reps)
                st.rerun()
            if q and y.button("Remove question", key=f"rp_rm_{r['id']}"):
                save_data("questions", [it for it in load_data("questions") if it["id"] != q["id"]])
                save_data("answers", [it for it in load_data("answers") if it["question_id"] != q["id"]])
                reps = load_data("reports")
                for it in reps:
                    if it["target_id"] == q["id"]:
                        it["status"] = "actioned"
                save_data("reports", reps)
                st.rerun()

    if gemini_enabled():
        if st.button("🤖 Generate AI impact report", use_container_width=True, key="impact_ai"):
            with st.spinner("Writing report..."):
                text, err = ask_gemini(
                    "Write a concise (under 200 words) impact report for a college administration about a peer-learning and "
                    "resource-reuse platform. Mention SDG 4 and SDG 12, interpret these numbers honestly (do not exaggerate), "
                    "and end with 3 recommended next steps.\n" + json.dumps(m)
                )
            st.session_state.impact_report = text if text else f"⚠️ {err}"
    if st.session_state.get("impact_report"):
        st.markdown(st.session_state.impact_report)
        st.download_button("⬇️ Download impact report", st.session_state.impact_report, file_name="campusconnect_impact.md", key="impact_dl")

# ============================================================
# SKILLS GRAPH  (radar + network graph + skill bars + AI roadmap)
# PASTE THIS WHOLE BLOCK just above the "# MY PROFILE" section.
# No new dependencies — charts are pure SVG rendered with components.html.
# ============================================================

SKILL_MAP = {
    "Programming": ["python", "java", "c++", "dsa", "coding", "programming", "algorithm", "algorithms", "code"],
    "AI & Data": ["ai", "ml", "machine learning", "genai", "data science", "data", "kaggle", "deep learning"],
    "Web Dev": ["web", "react", "html", "css", "frontend", "backend", "javascript", "django", "flask"],
    "Hackathons & Projects": ["hackathon", "hackathons", "project", "projects", "prototype", "mvp"],
    "Career & Placements": ["career", "placement", "placements", "internship", "resume", "interview"],
    "Design": ["design", "ui", "ux", "figma"],
    "Electronics": ["electronics", "arduino", "iot", "embedded", "sensors"],
    "Communication": ["communication", "pitch", "presentation", "leadership"],
}
SKILL_COLORS = {
    "Programming": "#3b6bff", "AI & Data": "#a855f7", "Web Dev": "#43d9ff", "Hackathons & Projects": "#fb923c",
    "Career & Placements": "#34d399", "Design": "#f472b6", "Electronics": "#facc15", "Communication": "#60a5fa",
}


def _hits(text, keywords):
    low = str(text or "").lower()
    return sum(1 for k in keywords if re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", low))


def skill_scores(user):
    """Score 0-100 per skill from interests, mentoring, Q&A activity, communities + optional self-rating."""
    uid = user["id"]
    mentor = next((m for m in load_data("mentors") if m["user_id"] == uid), None)
    my_q = " ".join(f"{q['title']} {q['description']} {q['category']}" for q in load_data("questions") if q["user_id"] == uid)
    my_a = [a["body"] for a in load_data("answers") if a["user_id"] == uid]
    comm_ids = {m["community_id"] for m in load_data("memberships") if m["user_id"] == uid}
    comm_text = " ".join(c["name"] for c in load_data("communities") if c["id"] in comm_ids)
    self_levels = user.get("skill_levels", {}) or {}
    out = {}
    for skill, kws in SKILL_MAP.items():
        auto = _hits(user.get("interests", ""), kws) * 22
        if mentor:
            auto += _hits(f"{mentor['skills']} {mentor['about']}", kws) * 18
        auto += min(_hits(my_q, kws), 4) * 5
        auto += min(sum(_hits(b, kws) for b in my_a), 5) * 9
        auto += _hits(comm_text, kws) * 8
        auto = min(100, auto)
        manual = int(self_levels.get(skill, 0) or 0)
        out[skill] = {"auto": auto, "self": manual, "score": min(100, auto + manual // 2)}
    return out


def level_label(score):
    if score >= 75: return "Expert"
    if score >= 50: return "Advanced"
    if score >= 25: return "Intermediate"
    if score > 0: return "Beginner"
    return "Not started"


def radar_svg(scores):
    import math as _m
    names = list(scores)
    n, cx, cy, R = len(names), 230, 220, 140
    def pt(i, frac):
        ang = -_m.pi / 2 + 2 * _m.pi * i / n
        return cx + R * frac * _m.cos(ang), cy + R * frac * _m.sin(ang)
    svg = ['<svg viewBox="0 0 460 440" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto">']
    for ring in (0.25, 0.5, 0.75, 1.0):
        pts = " ".join(f"{pt(i, ring)[0]:.1f},{pt(i, ring)[1]:.1f}" for i in range(n))
        svg.append(f'<polygon points="{pts}" fill="none" stroke="rgba(148,163,184,.25)" stroke-width="1"/>')
    for i, name in enumerate(names):
        x, y = pt(i, 1)
        svg.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="rgba(148,163,184,.2)"/>')
        lx, ly = pt(i, 1.2)
        anchor = "middle" if abs(lx - cx) < 12 else ("start" if lx > cx else "end")
        svg.append(f'<text x="{lx:.1f}" y="{ly:.1f}" fill="#dff3ff" font-size="11.5" font-weight="600" '
                   f'text-anchor="{anchor}" dominant-baseline="middle" font-family="DM Sans,sans-serif">{esc(name)}</text>')
    poly = " ".join(f"{pt(i, max(scores[nm]['score'], 4) / 100)[0]:.1f},{pt(i, max(scores[nm]['score'], 4) / 100)[1]:.1f}"
                    for i, nm in enumerate(names))
    svg.append(f'<polygon points="{poly}" fill="rgba(67,217,255,.28)" stroke="#43d9ff" stroke-width="2.2" '
               'style="filter:drop-shadow(0 0 8px rgba(67,217,255,.6))"/>')
    for i, nm in enumerate(names):
        x, y = pt(i, max(scores[nm]["score"], 4) / 100)
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{SKILL_COLORS.get(nm, "#43d9ff")}" stroke="#fff" stroke-width="1.5">'
                   f'<title>{esc(nm)}: {scores[nm]["score"]}/100</title></circle>')
    svg.append("</svg>")
    return "".join(svg)


def network_svg(user, scores):
    """You in the centre -> skill nodes (size = score) -> best peer for that skill on the outside."""
    import math as _m
    names = list(scores)
    n, cx, cy = len(names), 280, 280
    peers = {}
    for u in load_data("users"):
        if u["id"] == user["id"]:
            continue
        ps = skill_scores(u)
        for sk in names:
            if ps[sk]["score"] >= 30 and ps[sk]["score"] > peers.get(sk, (None, 0))[1]:
                peers[sk] = (u["name"].split()[0], ps[sk]["score"])
    svg = ['<svg viewBox="0 0 560 560" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto">',
           '<circle cx="280" cy="280" r="150" fill="none" stroke="rgba(148,163,184,.12)" stroke-dasharray="4 6"/>',
           '<circle cx="280" cy="280" r="228" fill="none" stroke="rgba(148,163,184,.08)" stroke-dasharray="4 6"/>']
    nodes, lines = [], []
    for i, sk in enumerate(names):
        ang = -_m.pi / 2 + 2 * _m.pi * i / n
        x, y = cx + 150 * _m.cos(ang), cy + 150 * _m.sin(ang)
        s = scores[sk]["score"]
        col = SKILL_COLORS.get(sk, "#43d9ff")
        r = 14 + s * 0.16
        lines.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="{col}" '
                     f'stroke-width="{1 + s / 25:.1f}" stroke-opacity="{0.25 + s / 140:.2f}"/>')
        nodes.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{col}" fill-opacity="{0.35 + s / 160:.2f}" '
                     f'stroke="{col}" stroke-width="2" style="filter:drop-shadow(0 0 10px {col})"><title>{esc(sk)}: {s}/100</title></circle>')
        nodes.append(f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" fill="#fff" font-size="11" font-weight="800" '
                     f'font-family="Plus Jakarta Sans,sans-serif">{s}</text>')
        tx, ty = cx + (150 + r + 14) * _m.cos(ang), cy + (150 + r + 14) * _m.sin(ang)
        if sk in peers:
            tx, ty = cx + (150 + r + 12) * _m.cos(ang), cy + (150 + r + 12) * _m.sin(ang)
        anchor = "middle" if abs(_m.cos(ang)) < 0.2 else ("start" if _m.cos(ang) > 0 else "end")
        nodes.append(f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="{anchor}" dominant-baseline="middle" fill="#dff3ff" '
                     f'font-size="10.5" font-weight="600" font-family="DM Sans,sans-serif">{esc(sk)}</text>')
        if sk in peers:
            px, py = cx + 232 * _m.cos(ang), cy + 232 * _m.sin(ang)
            lines.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{px:.1f}" y2="{py:.1f}" stroke="{col}" stroke-opacity=".45" stroke-dasharray="3 4"/>')
            nodes.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="15" fill="#0b2134" stroke="{col}" stroke-width="1.5">'
                         f'<title>{esc(peers[sk][0])} is strong in {esc(sk)} ({peers[sk][1]}/100)</title></circle>')
            nodes.append(f'<text x="{px:.1f}" y="{py + 3.5:.1f}" text-anchor="middle" fill="#e9f7ff" font-size="9.5" font-weight="700" '
                         f'font-family="DM Sans,sans-serif">{esc(peers[sk][0][:6])}</text>')
    svg += lines + nodes
    svg.append(f'<circle cx="{cx}" cy="{cy}" r="34" fill="url(#cg)" stroke="rgba(215,252,255,.85)" stroke-width="1.5" style="filter:drop-shadow(0 0 16px rgba(67,217,255,.7))"/>')
    svg.append('<defs><linearGradient id="cg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4be3ff"/><stop offset="1" stop-color="#3158ff"/></linearGradient></defs>')
    svg.append(f'<text x="{cx}" y="{cy + 5}" text-anchor="middle" fill="#fff" font-size="13" font-weight="800" font-family="Plus Jakarta Sans,sans-serif">'
               f'{esc(user["name"].split()[0][:8])}</text>')
    svg.append("</svg>")
    return "".join(svg)


def _graph_frame(inner, height):
    html_doc = (
        "<div style='background:linear-gradient(160deg,rgba(11,40,70,.55),rgba(6,22,40,.7));border:1px solid rgba(67,217,255,.25);"
        "border-radius:18px;padding:10px;box-shadow:0 0 30px rgba(37,150,255,.14)'>" + inner + "</div>"
    )
    components.html(html_doc, height=height)


def skills_graph_page():
    user = st.session_state.user
    page_header("🕸️ Skills Graph", "See your skills at a glance, find who can help, and plan what to learn next.")
    scores = skill_scores(user)
    ranked = sorted(scores.items(), key=lambda kv: kv[1]["score"], reverse=True)
    top, weakest = ranked[0], ranked[-1]
    avg = round(sum(v["score"] for v in scores.values()) / len(scores))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏆 Top skill", top[0] if top[1]["score"] else "—")
    c2.metric("📈 Average level", f"{avg}/100")
    c3.metric("🌱 Growth area", weakest[0])
    c4.metric("✅ Skills active", sum(1 for v in scores.values() if v["score"] >= 25))

    tab_r, tab_n, tab_c = st.tabs(["📡 Radar", "🕸️ Network", "👥 Campus comparison"])
    with tab_r:
        left, right = st.columns([1.2, 1])
        with left:
            _graph_frame(radar_svg(scores), 470)
        with right:
            st.markdown("**Skill levels**")
            for skill, v in ranked:
                st.markdown(f"<span class='tag' style='border-color:{SKILL_COLORS.get(skill)}'>{esc(skill)}</span> "
                            f"<span class='small-muted'>{level_label(v['score'])} • {v['score']}/100</span>", unsafe_allow_html=True)
                st.progress(v["score"] / 100)
    with tab_n:
        st.caption("Centre = you. Bigger nodes = stronger skills. Outer bubbles show the classmate strongest in that skill — hover for details.")
        _graph_frame(network_svg(user, scores), 600)

    with tab_c:
        users = load_data("users")
        if len(users) < 2:
            st.info("Invite more students to compare skills across campus.")
        else:
            allscores = [skill_scores(u) for u in users]
            campus_avg = {sk: round(sum(s[sk]["score"] for s in allscores) / len(allscores)) for sk in SKILL_MAP}
            df = pd.DataFrame({"You": {sk: scores[sk]["score"] for sk in SKILL_MAP}, "Campus average": campus_avg})
            st.bar_chart(df)
            gaps = [sk for sk in SKILL_MAP if campus_avg[sk] - scores[sk]["score"] >= 15]
            st.caption("Below campus average in: " + (", ".join(gaps) if gaps else "nothing — you're at or above average everywhere 🎉"))

    with st.expander("🎚️ Self-assess your skills (boosts your graph)"):
        st.caption("Rate yourself honestly. Your rating adds half its value on top of the score earned from your activity.")
        new_levels = {}
        cols = st.columns(2)
        for i, sk in enumerate(SKILL_MAP):
            new_levels[sk] = cols[i % 2].slider(sk, 0, 100, int(scores[sk]["self"]), 5, key=f"sk_self_{i}")
        if st.button("💾 Save my skill levels", key="sk_save"):
            users = load_data("users")
            for u in users:
                if u["id"] == user["id"]:
                    u["skill_levels"] = new_levels
            save_data("users", users)
            refresh_session_user()
            flash("success", "Skill levels saved.")
            st.rerun()

    with st.container(border=True):
        st.markdown("### 🤖 AI skill roadmap")
        target = st.text_input("Goal (optional)", placeholder="Python Developer Intern, ML Engineer...", key="sk_goal")
        if st.button("🚀 Build my skill roadmap", key="sk_ai", use_container_width=True):
            if not gemini_enabled():
                st.warning("Add your Gemini key in the profile menu (top-right).")
            else:
                summary = "; ".join(f"{k}: {v['score']}/100" for k, v in ranked)
                with st.spinner("Planning your roadmap..."):
                    text, err = ask_gemini(
                        "Act as a campus skills coach. Using the skill scores, give a 4-week roadmap (Markdown) that "
                        "improves the weakest relevant skills first. For each week: focus, 3 concrete tasks, and one "
                        "free resource TYPE (do not invent URLs). Mention which CampusConnect section can help.\n"
                        f"Goal: {target or 'overall growth'}\nSkill scores: {summary}\n{profile_text(user)}\n"
                        f"CampusConnect data:\n{campus_context()}"
                    )
                st.session_state.skill_plan = text if text else f"⚠️ {err}"
        if st.session_state.get("skill_plan"):
            st.markdown(st.session_state.skill_plan)
            st.download_button("⬇️ Download roadmap", st.session_state.skill_plan, file_name="skill_roadmap.md", key="sk_dl")

# ============================================================
# END SKILLS GRAPH
# ============================================================


# ============================================================
# MY PROFILE
# ============================================================

def profile_page():
    user = st.session_state.user
    page_header("👤 My Profile", "A compact view of your profile, interests and contribution trail.")

    uid = user["id"]
    s = user_stats(uid)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Questions", s["questions"])
    c2.metric("Answers", s["answers"])
    c3.metric("Communities", s["communities"])
    c4.metric("Resources", s["resources"])

    _, everyone = leaderboard(1)
    rank = next((r["Rank"] for r in everyone if r["Student"] == user["name"]), "-")

    st.markdown(
        f'<div class="cc-card"><h3>{esc(user["name"])}</h3>'
        f'<p>{esc(user["email"])}</p>'
        f'<span class="small-muted">{esc(user["year"])} • {esc(user["branch"])}</span><br>'
        + "".join(f'<span class="tag">{esc(t)}</span>' for t in user.get("interests", "").split(",") if t.strip())
        + "</div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown(f"### ⚡ Level {s['level']} • Rank #{rank} of {len(everyone)}")
        st.progress(s["into_level"] / 50, text=f"{s['xp']} XP total • {50 - s['into_level']} XP to Level {s['level'] + 1}")
        st.markdown("".join(f'<span class="tag">{esc(b)}</span>' for b in badges_for(s)), unsafe_allow_html=True)
        st.caption("Earn XP: question +5 • answer +10 • upvote received +3 • best answer +25 • mentor profile +15 • resource +8")

    with st.expander("✏️ Edit profile"):
        name = st.text_input("Full name", value=user["name"])
        branch = st.selectbox("Branch", BRANCHES, index=BRANCHES.index(user["branch"]) if user["branch"] in BRANCHES else 0)
        year = st.selectbox("Year", YEARS, index=YEARS.index(user["year"]) if user["year"] in YEARS else 0)
        interests = st.text_input("Interests", value=user.get("interests", ""))
        if st.button("Save profile"):
            if not name.strip():
                st.warning("Name cannot be empty.")
            else:
                users = load_data("users")
                for u in users:
                    if u["id"] == uid:
                        u.update({"name": name.strip(), "branch": branch, "year": year, "interests": interests.strip()})
                save_data("users", users)
                refresh_session_user()
                st.success("Profile updated.")
                st.rerun()

    with st.expander("🔑 Change password"):
        old = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        if st.button("Update password"):
            if not verify_password(old, user["password"]):
                st.error("Current password is incorrect.")
            elif len(new) < 6:
                st.warning("New password should contain at least 6 characters.")
            else:
                users = load_data("users")
                for u in users:
                    if u["id"] == uid:
                        u["password"] = hash_password(new)
                save_data("users", users)
                refresh_session_user()
                st.success("Password updated.")

    with st.expander("💾 Export my data"):
        mine = {
            "profile": {k: v for k, v in user.items() if k != "password"},
            "stats": s,
            "questions": [q for q in load_data("questions") if q["user_id"] == uid],
            "answers": [a for a in load_data("answers") if a["user_id"] == uid],
        }
        st.download_button("⬇️ Download JSON", json.dumps(mine, indent=2, ensure_ascii=False),
                           file_name="my_campusconnect_data.json", key="dl_export")

# ============================================================
# FAQ
# ============================================================

FAQ_SECTIONS = {
    "First-Year Academics": {
        "takeaway": "Use your first year to explore, strengthen your fundamentals and discover which technical field you genuinely enjoy.",
        "items": [
            {
                "q": "How should I choose between CSE, IT, AI/DS, AIML and other branches?",
                "a": [
                    "Don't choose a branch only because one name sounds more attractive than another. First understand what you will actually study and what kind of work interests you.",
                    "CSE and IT have a lot of overlap and both can lead to software-development careers. AI/DS and AIML put more emphasis on mathematics, statistics, data and machine-learning concepts. Other branches such as EXTC, Mechanical or Civil can also lead to excellent careers, but the subjects and career paths are different.",
                ],
                "tips": [
                    "**CSE and IT:** Both offer pathways to software-development careers and have overlapping subjects.",
                    "**AI/DS and AIML:** Focus more on mathematics, statistics, data and machine learning.",
                    "**Other branches:** EXTC, Mechanical and Civil also offer excellent career opportunities, with different subjects and career paths.",
                ],
            },
            {
                "q": "Do I need coding knowledge before entering engineering?",
                "a": [
                    "No. You are not expected to enter engineering already knowing programming. Some students will have been coding since school, while others will write their first program in college.",
                    "Don't compare your starting point with someone else's. Start with one language, preferably the language used in your first-year curriculum or the one you find easiest to learn. Learn variables, conditions, loops, functions, arrays/lists and basic problem solving before jumping into advanced frameworks or AI.",
                ],
                "tips": [
                    "Start with one programming language, preferably the one taught in your first-year curriculum.",
                    "Learn variables, conditions, loops, functions, arrays/lists and basic problem-solving.",
                    "Avoid comparing your progress with students who started coding earlier.",
                    "Build a strong foundation before moving to advanced frameworks or AI.",
                ],
            },
            {
                "q": "How can I participate in my first hackathon?",
                "a": [
                    "Don't wait until you feel that you're \"good enough.\" Your first hackathon is primarily a learning experience. Find 2–4 teammates with complementary skills, understand the problem statement properly and divide the work.",
                    "As a beginner, focus on building a small working prototype instead of promising a huge application. Use tools such as GitHub to collaborate, keep your code organized and test your features regularly.",
                    "A simple project that actually works is much better during a demo than ten impressive features that are only shown on slides.",
                ],
                "tips": [
                    "Find 2–4 teammates with complementary skills.",
                    "Understand the problem statement and divide the work.",
                    "Build a small, functional prototype instead of promising too many features.",
                    "Use GitHub for collaboration and test your features regularly.",
                    "A simple working project is better than many impressive features that exist only on slides.",
                ],
            },
            {
                "q": "What should I do if I don't understand a subject taught in college?",
                "a": [
                    "Don't wait until the examination week. First identify exactly what you don't understand—is it the basic concept, the mathematics behind it, or the way problems are solved?",
                    "Go back one level and learn the prerequisite concept. Then try examples yourself. You can use your professor, classmates, seniors, textbooks and reliable online lectures. If you're still stuck, ask a specific question instead of saying only \"I don't understand this chapter.\"",
                    "Keep a small list of doubts while studying and clear them regularly. Small gaps become much harder to fix when several chapters depend on them.",
                ],
                "tips": [
                    "Identify whether your difficulty is with basic concepts, mathematics or problem-solving methods.",
                    "Review prerequisite concepts and practise examples.",
                    "Seek help from professors, classmates, seniors, textbooks and reliable online lectures.",
                    "Ask specific questions instead of saying only that you don't understand a chapter.",
                    "Maintain a list of doubts and resolve them regularly.",
                    "Small knowledge gaps become harder to fix when several chapters depend on them.",
                ],
            },
            {
                "q": "When should I start preparing for internships and placements?",
                "a": [
                    "You don't need to start serious placement preparation from your first semester, but you should start building your foundation early.",
                    "In first year, focus on programming fundamentals, problem solving, communication and exploring different technical domains. Later, you can go deeper into DSA, projects, development, internships and other skills depending on your career goal.",
                    "Don't turn first year into a race to collect certificates. Build actual skills and projects.",
                    "Your first year is the best time to explore. By the end of it, try to have a clearer idea of which technical area you genuinely enjoy.",
                ],
                "tips": [
                    "Focus on programming fundamentals, problem-solving and communication.",
                    "Explore different technical domains to discover your interests.",
                    "Gradually learn Data Structures and Algorithms (DSA), development and project building.",
                    "Pursue internships and other opportunities as your skills improve.",
                    "Prioritize practical skills and real projects over collecting certificates.",
                ],
            },
        ],
    },
}


def faq_page():
    page_header("❓ FAQ", "Quick, honest answers to the questions first-year students ask most.")

    search = st.text_input("🔎 Search FAQs", placeholder="Try: hackathon, branch, placements...").strip().lower()

    shown = 0
    for section, data in FAQ_SECTIONS.items():
        matches = []
        for n, item in enumerate(data["items"], 1):
            haystack = " ".join([item["q"], *item["a"], *item.get("tips", [])]).lower()
            if not search or search in haystack:
                matches.append((n, item))
        if not matches:
            continue

        st.markdown(f"### 📘 {section}")
        for n, item in matches:
            with st.expander(f"{n}. {item['q']}"):
                for para in item["a"]:
                    st.write(para)
                if item.get("tips"):
                    st.markdown("**✅ Quick tips**")
                    st.markdown("\n".join(f"- {t}" for t in item["tips"]))
            shown += 1

        if data.get("takeaway") and not search:
            st.info(f"**🎯 Main takeaway:** {data['takeaway']}")

    if shown == 0:
        st.info("No FAQ matches your search. Try different words, or ask the AI / community below.")
        if search and gemini_enabled() and st.button("🤖 Ask AI this question", key="faq_ai"):
            text, err = ask_gemini(
                "Answer this first-year engineering student's question briefly and honestly:\n" + search
            )
            show_ai(text, err)

    with st.container(border=True):
        st.markdown("**Still have a doubt?** Ask the community — a specific question gets a faster answer.")
        if st.button("💬 Ask in Anonymous Q&A", key="faq_to_qa"):
            st.session_state.page = "Anonymous Q&A"
            st.rerun()

# ============================================================
# SEMANTIC SEARCH  (hybrid: Gemini embeddings + offline TF-IDF/synonyms)
# PASTE THIS WHOLE BLOCK next to the Skills Graph block
# (anywhere above the "# MAIN" section). No new dependencies.
#
# How it works
#   1. Indexes Q&A (with answers), mentors, resources, opportunities, communities,
#      students' public interests and FAQ into one searchable corpus.
#   2. If a Gemini key is available it embeds the corpus + your query and ranks by
#      cosine similarity (understands meaning: "need a job" ~ "internship").
#      Model names are auto-discovered, so retired models never break it.
#   3. It ALWAYS also computes an offline TF-IDF score with a synonym map, and blends
#      the two. With no key / no network it silently falls back to TF-IDF only.
# ============================================================

SS_STOP = set(
    "a an the is are was were be to of in on for and or with how do does did i my me can what which who where when "
    "should would could about from at it this that you your we our there any some get want need find help please".split()
)

SS_SYN_GROUPS = [
    {"job", "jobs", "internship", "internships", "placement", "placements", "career", "hiring", "recruit", "intern"},
    {"ai", "ml", "genai", "llm", "neural", "deep", "kaggle", "model", "models"},
    {"team", "teammate", "teammates", "partner", "partners", "hackathon", "hackathons", "squad", "collaborate"},
    {"book", "books", "textbook", "notes", "material", "reading"},
    {"coding", "code", "programming", "python", "java", "dsa", "algorithm", "algorithms", "developer"},
    {"web", "website", "frontend", "backend", "react", "html", "css", "javascript", "fullstack"},
    {"mentor", "mentors", "mentorship", "guidance", "senior", "seniors", "guide", "advice"},
    {"free", "donate", "donation", "giveaway", "gift"},
    {"borrow", "lend", "lending", "loan", "rent"},
    {"exam", "exams", "test", "revision", "syllabus", "study", "studying"},
    {"resume", "cv", "portfolio"},
    {"electronics", "arduino", "iot", "embedded", "sensor", "sensors", "circuit", "hardware"},
    {"design", "ui", "ux", "figma", "graphic"},
    {"stuck", "confused", "doubt", "doubts", "difficult", "understand", "struggling"},
    {"workshop", "workshops", "bootcamp", "training", "course", "courses", "session"},
    {"competition", "contest", "challenge", "challenges", "compete"},
]

SS_KIND_META = {
    "Question": ("💬", "Anonymous Q&A"),
    "Mentor": ("🎓", "Mentor Hub"),
    "Resource": ("📦", "Resource Exchange"),
    "Opportunity": ("🏆", "Opportunity Hub"),
    "Community": ("👥", "Communities"),
    "Student": ("🤝", "Communities"),
    "FAQ": ("❓", "FAQ"),
}

SS_EXAMPLES = [
    "I need a job",
    "someone to guide me with ML",
    "find teammates for a contest",
    "free books for first year",
    "I'm confused about coding basics",
]


def _ss_stem(word):
    for suf in ("ing", "ed", "es", "s"):
        if len(word) > len(suf) + 3 and word.endswith(suf):
            return word[: -len(suf)]
    return word


_SS_SYN_INDEX = {}
for _g in SS_SYN_GROUPS:
    _stems = {_ss_stem(w) for w in _g}
    for _w in _stems:
        _SS_SYN_INDEX.setdefault(_w, set()).update(_stems)


def _ss_tokens(text):
    out = []
    for t in re.findall(r"[a-z0-9+#]+", str(text or "").lower()):
        if t in SS_STOP or len(t) < 2:
            continue
        out.append(_ss_stem(t))
    return out


def build_search_corpus():
    corpus = []
    answers = load_data("answers")
    for q in load_data("questions"):
        ans = " ".join(a["body"] for a in answers if a["question_id"] == q["id"])[:900]
        corpus.append({
            "kind": "Question", "id": q["id"], "title": q["title"],
            "text": f"{q['description']} {ans}", "meta": f"{q['category']} • {len([a for a in answers if a['question_id'] == q['id']])} answer(s)",
        })
    for m in load_data("mentors"):
        corpus.append({
            "kind": "Mentor", "id": m["id"], "title": m["name"],
            "text": f"{m['skills']}. {m['about']} Available: {m.get('availability', '')}", "meta": f"{m['year']} • {m['branch']}",
        })
    for r in load_data("resources"):
        if r["status"] != "available":
            continue
        corpus.append({
            "kind": "Resource", "id": r["id"], "title": r["title"],
            "text": f"{r['description']} {r['kind']} {r.get('category', '')}", "meta": f"{r['kind']} • {r.get('category') or 'General'}",
        })
    for o in load_data("opportunities"):
        corpus.append({
            "kind": "Opportunity", "id": o["id"], "title": o["title"],
            "text": f"{o['type']}. {o['description']}", "meta": f"{o['type']} • deadline {o['deadline']}",
        })
    for c in load_data("communities"):
        corpus.append({"kind": "Community", "id": c["id"], "title": c["name"], "text": c["description"], "meta": "Community"})
    for u in load_data("users"):
        if u.get("interests", "").strip():
            corpus.append({
                "kind": "Student", "id": u["id"], "title": u["name"],
                "text": f"Interests: {u['interests']}. {u['branch']}", "meta": f"{u['year']} • {u['branch']}",
            })
    try:
        for section, data in FAQ_SECTIONS.items():
            for n, item in enumerate(data["items"]):
                corpus.append({
                    "kind": "FAQ", "id": f"{section}-{n}", "title": item["q"],
                    "text": " ".join(item["a"]) + " " + " ".join(item.get("tips", [])), "meta": section,
                })
    except Exception:
        pass
    return corpus


def tfidf_scores(query, corpus):
    """Offline lexical ranking with light stemming + synonym expansion. Returns a list of 0..1 scores."""
    base = _ss_tokens(query)
    qweights = {}
    for t in base:
        qweights[t] = max(qweights.get(t, 0), 1.0)
        for syn in _SS_SYN_INDEX.get(t, ()):
            qweights[syn] = max(qweights.get(syn, 0), 0.5)
    docs = []
    for d in corpus:
        toks = _ss_tokens(d["title"]) * 2 + _ss_tokens(d["text"])
        c = {}
        for t in toks:
            c[t] = c.get(t, 0) + 1
        docs.append(c)
    n = len(docs) or 1
    df = {}
    for c in docs:
        for t in c:
            df[t] = df.get(t, 0) + 1
    idf = {t: math.log((n + 1) / (v + 1)) + 1 for t, v in df.items()}
    qvec = {t: w * idf.get(t, 0) for t, w in qweights.items()}
    qnorm = math.sqrt(sum(v * v for v in qvec.values())) or 1.0
    scores = []
    for c in docs:
        dvec = {t: (1 + math.log(k)) * idf[t] for t, k in c.items()}
        dnorm = math.sqrt(sum(v * v for v in dvec.values())) or 1.0
        dot = sum(qvec[t] * dvec[t] for t in qvec if t in dvec)
        scores.append(dot / (qnorm * dnorm))
    return scores


@st.cache_data(ttl=900, show_spinner=False)
def discover_embed_models(key):
    client = genai.Client(api_key=key)
    found = []
    for m in client.models.list():
        name = (getattr(m, "name", "") or "").replace("models/", "")
        actions = getattr(m, "supported_actions", None)
        if "embed" in name and (not actions or "embedContent" in actions):
            found.append(name)
    return sorted(set(found), key=lambda n: (0 if "gemini-embedding" in n else 1, n))


def embed_texts(texts, task="RETRIEVAL_DOCUMENT"):
    """Returns (vectors, model, error). Tries the last working model first, then discovered ones."""
    problem = _precheck()
    if problem:
        return None, None, problem
    try:
        client = genai.Client(api_key=api_key())
    except Exception as exc:
        return None, None, f"Gemini client error: {str(exc)[:160]}"
    names = []
    if st.session_state.get("ss_embed_model"):
        names.append(st.session_state.ss_embed_model)
    try:
        names += discover_embed_models(api_key())
    except Exception:
        pass
    names += ["gemini-embedding-001", "text-embedding-004"]
    names = list(dict.fromkeys(names))
    last = "no embedding model responded"
    clipped = [str(t)[:1500] for t in texts]
    for model in names:
        try:
            vecs = []
            for i in range(0, len(clipped), 80):
                batch = clipped[i:i + 80]
                try:
                    resp = client.models.embed_content(
                        model=model, contents=batch, config=types.EmbedContentConfig(task_type=task))
                except Exception:
                    resp = client.models.embed_content(model=model, contents=batch)
                vecs += [list(e.values) for e in resp.embeddings]
            if len(vecs) == len(clipped):
                st.session_state.ss_embed_model = model
                return vecs, model, None
        except Exception as exc:
            last = f"{model}: {str(exc)[:160]}"
            if classify_error(exc) == "auth":
                return None, None, "Gemini API key is invalid or lacks access."
    return None, None, last


def _cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _minmax(values):
    if not values:
        return []
    lo, hi = min(values), max(values)
    return [(v - lo) / (hi - lo) if hi > lo else 0.0 for v in values]


def semantic_rank(query, corpus, use_embeddings=True):
    """Returns (ranked list of (relevance 0..1, doc), engine label)."""
    lex = tfidf_scores(query, corpus)
    emb = None
    engine = "Offline keyword + synonym engine"
    if use_embeddings and gemini_enabled() and corpus:
        sig = hashlib.md5("||".join(f"{d['kind']}{d['id']}{d['title']}{d['text']}" for d in corpus).encode()).hexdigest()
        cache = st.session_state.get("ss_cache")
        if not cache or cache.get("sig") != sig:
            vecs, model, err = embed_texts([f"{d['title']}. {d['text']}" for d in corpus], "RETRIEVAL_DOCUMENT")
            if vecs:
                cache = {"sig": sig, "vecs": vecs, "model": model}
                st.session_state.ss_cache = cache
                st.session_state.ss_err = ""
            else:
                cache = None
                st.session_state.ss_err = err or "embedding failed"
        if cache:
            qv, _, err = embed_texts([query], "RETRIEVAL_QUERY")
            if qv:
                emb = [_cosine(qv[0], v) for v in cache["vecs"]]
                engine = f"Gemini embeddings ({cache['model']}) + keyword hybrid"
            else:
                st.session_state.ss_err = err or "query embedding failed"
    if emb:
        e_n, l_n = _minmax(emb), _minmax(lex)
        final = [0.7 * e + 0.3 * l for e, l in zip(e_n, l_n)]
        ranked = [(s, d) for s, d in zip(final, corpus) if s >= 0.15]
    else:
        top = max(lex) if lex else 0
        ranked = [(s / top, d) for s, d in zip(lex, corpus) if s > 0 and top > 0]
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked, engine


def _ss_set_query(text):
    st.session_state.ss_q = text


def semantic_search_page():
    user = st.session_state.user
    page_header("🔎 Semantic Search", "Search by meaning, not just keywords — across Q&A, mentors, resources, opportunities and more.")

    corpus = build_search_corpus()
    c1, c2, c3 = st.columns([2.4, 1.2, 1])
    query = c1.text_input("What are you looking for?", key="ss_q",
                          placeholder="e.g. someone to guide me with machine learning")
    kinds = c2.multiselect("Search in", list(SS_KIND_META), default=list(SS_KIND_META), key="ss_kinds")
    top_k = c3.slider("Results", 3, 15, 8, key="ss_k")

    t1, t2 = st.columns([1, 1])
    use_emb = t1.toggle("🧠 Use Gemini embeddings", value=gemini_enabled(), key="ss_emb",
                        help="Understands meaning. Falls back to the offline engine automatically.")
    if t2.button("♻️ Rebuild index", key="ss_reindex"):
        st.session_state.pop("ss_cache", None)
        st.toast("Index will be rebuilt on next search", icon="♻️")

    st.caption(f"📚 {len(corpus)} items indexed")
    if not query.strip():
        st.caption("Try one of these:")
        cols = st.columns(len(SS_EXAMPLES))
        for i, (col, ex) in enumerate(zip(cols, SS_EXAMPLES)):
            col.button(ex, key=f"ss_ex_{i}", use_container_width=True, on_click=_ss_set_query, args=(ex,))
        return

    allowed = set(kinds)
    scoped = [d for d in corpus if d["kind"] in allowed]
    if not scoped:
        st.info("Pick at least one category to search in.")
        return

    with st.spinner("Searching by meaning..."):
        ranked, engine = semantic_rank(query.strip(), scoped, use_embeddings=use_emb)
    st.caption(f"⚙️ Engine: {engine}")
    if use_emb and gemini_enabled() and st.session_state.get("ss_err") and "Gemini embeddings" not in engine:
        st.caption(f"ℹ️ Embeddings unavailable ({st.session_state.ss_err[:110]}) — using the offline engine.")

    results = ranked[:top_k]
    if not results:
        st.info("No close matches. Try different words — or ask the community in Anonymous Q&A.")
        return

    st.markdown(f"### Top {len(results)} result(s)")
    for i, (score, d) in enumerate(results):
        icon, page = SS_KIND_META[d["kind"]]
        with st.container(border=True):
            st.markdown(f"### {icon} {d['title']}")
            st.caption(f"{d['kind']} • {d['meta']}")
            snippet = " ".join(str(d["text"]).split())
            st.write(snippet[:230] + ("…" if len(snippet) > 230 else ""))
            st.progress(min(1.0, max(0.03, score)), text=f"Relevance {int(score * 100)}%")
            if st.button(f"Open in {page} →", key=f"ss_open_{i}_{d['kind']}_{d['id']}"):
                st.session_state.page = page
                st.rerun()

    if gemini_enabled():
        if st.button("🤖 Answer my search using these results", key="ss_ai", use_container_width=True):
            ctx = "\n".join(f"- [{d['kind']}] {d['title']}: {' '.join(str(d['text']).split())[:260]}" for _, d in results[:6])
            with st.spinner("Writing answer..."):
                text, err = ask_gemini(
                    "Answer the student's search using ONLY the CampusConnect results below. Be concise (under 120 words), "
                    "name the matching items and the section where each lives, and say honestly if nothing fits. "
                    "Do not invent facts.\n\n"
                    f"Student profile:\n{profile_text(user)}\nSearch: {query}\n\nResults:\n{ctx}"
                )
            st.session_state.ss_answer = text if text else f"⚠️ {err}"
        if st.session_state.get("ss_answer"):
            st.markdown(st.session_state.ss_answer)

# ============================================================
# END SEMANTIC SEARCH
# ============================================================

# ============================================================
# MAIN
# ============================================================

PAGES = {
    "Dashboard": dashboard,
    "Anonymous Q&A": anonymous_qa,
    "Mentor Hub": mentor_hub,
    "Communities": communities_page,
    "Resource Exchange": resource_exchange,
    "Opportunity Hub": opportunity_hub,
    "AI Campus Assistant": ai_assistant,
    "AI Tools": ai_tools,
    "Student Growth Path": growth_path,
    "Impact Dashboard": impact_page,
    "FAQ": faq_page,
    "My Profile": profile_page,
}


def main():
    if not st.session_state.logged_in or not st.session_state.user:
        auth_page()
        return
    app_shell()
    PAGES.get(st.session_state.page, dashboard)()


main()
