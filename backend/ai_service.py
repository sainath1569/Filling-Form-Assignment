import os
import re
import json
import uuid
import hashlib
import logging
import unicodedata
from difflib import SequenceMatcher
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger("formpilot-ai-service")

# ---------------------------------------------------------------------------
# Profile Pydantic Schemas
# ---------------------------------------------------------------------------

class PersonalInfo(BaseModel):
    first_name: Optional[str] = Field(default=None)
    last_name: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)
    linkedin: Optional[str] = Field(default=None)
    github: Optional[str] = Field(default=None)
    portfolio: Optional[str] = Field(default=None)
    location: Optional[str] = Field(default=None)

class Education(BaseModel):
    school: Optional[str] = Field(default=None)
    degree: Optional[str] = Field(default=None)
    discipline: Optional[str] = Field(default=None)
    start_year: Optional[str] = Field(default=None)
    end_year: Optional[str] = Field(default=None)

class Experience(BaseModel):
    company: Optional[str] = Field(default=None)
    title: Optional[str] = Field(default=None)
    start_date: Optional[str] = Field(default=None)
    end_date: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)

class Project(BaseModel):
    name: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    technologies: List[str] = Field(default_factory=list)
    link: Optional[str] = Field(default=None)

class AdditionalInfo(BaseModel):
    visa_sponsorship: Optional[str] = Field(default=None)
    current_company: Optional[str] = Field(default=None)
    current_title: Optional[str] = Field(default=None)

class UserProfile(BaseModel):
    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    education: List[Education] = Field(default_factory=list)
    experience: List[Experience] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    additional_info: AdditionalInfo = Field(default_factory=AdditionalInfo)

# ---------------------------------------------------------------------------
# Mock Profile
# ---------------------------------------------------------------------------

MOCK_PROFILE = UserProfile(
    personal_info=PersonalInfo(
        first_name="Jane", last_name="Smith", email="jane.smith@example.com",
        phone="+1 (555) 019-9234", linkedin="https://linkedin.com/in/janesmith-developer",
        github="https://github.com/janesmithdev", portfolio="https://janesmith.dev",
        location="San Francisco, CA"
    ),
    education=[Education(school="Tech State University", degree="Bachelor of Science",
                         discipline="Computer Science", start_year="2018", end_year="2022")],
    experience=[
        Experience(company="InnovateTech Solutions", title="Senior React Developer",
                   start_date="2022-06", end_date="Present",
                   description="Designed and deployed responsive dashboard cards, migrated states from Redux to Zustand."),
        Experience(company="StartupHub Inc", title="Software Developer Intern",
                   start_date="2021-05", end_date="2021-08",
                   description="Implemented responsive navigation menus and maintained unit tests.")
    ],
    skills=["React", "TypeScript", "Next.js", "Zustand", "Node.js", "FastAPI", "Python"],
    projects=[Project(name="FormPilot Autofill Engine",
                      description="AI-powered tool that scans forms and autofills inputs.",
                      technologies=["React", "TypeScript", "Playwright", "FastAPI"],
                      link="https://github.com/janesmithdev/formpilot")],
    additional_info=AdditionalInfo(visa_sponsorship="No", current_company="InnovateTech Solutions",
                                   current_title="Senior React Developer")
)

# ---------------------------------------------------------------------------
# Normalization & Abbreviation Expansion
# ---------------------------------------------------------------------------

ABBREVIATION_MAP: Dict[str, str] = {
    "btech": "bachelor of technology",
    "b.tech": "bachelor of technology",
    "b tech": "bachelor of technology",
    "bachelor tech": "bachelor of technology",
    "be": "bachelor of engineering",
    "b.e": "bachelor of engineering",
    "bs": "bachelor of science",
    "bsc": "bachelor of science",
    "b.sc": "bachelor of science",
    "ba": "bachelor of arts",
    "b.a": "bachelor of arts",
    "ms": "master of science",
    "msc": "master of science",
    "m.sc": "master of science",
    "mtech": "master of technology",
    "m.tech": "master of technology",
    "mba": "master of business administration",
    "phd": "doctor of philosophy",
    "cse": "computer science and engineering",
    "cs": "computer science",
    "comp sci": "computer science",
    "compsci": "computer science",
    "ece": "electronics and communication engineering",
    "ee": "electrical engineering",
    "me": "mechanical engineering",
    "it": "information technology",
    "is": "information systems",
    "ds": "data science",
    "ai": "artificial intelligence",
    "ml": "machine learning",
    "js": "javascript",
    "ts": "typescript",
    "gh": "github",
    "li": "linkedin",
    "py": "python",
    "k8s": "kubernetes",
    "kube": "kubernetes",
}

def normalize_text(s: str) -> str:
    """Lowercase, strip, remove punctuation, collapse spaces, normalize unicode."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)   # remove punctuation
    s = re.sub(r"\s+", " ", s).strip()
    return s

def expand_abbreviation(s: str) -> str:
    """Expand known abbreviations in normalized text."""
    normalized = normalize_text(s)
    # Direct lookup first
    if normalized in ABBREVIATION_MAP:
        return ABBREVIATION_MAP[normalized]
    # Word-by-word expansion
    words = normalized.split()
    expanded = [ABBREVIATION_MAP.get(w, w) for w in words]
    return " ".join(expanded)

def fuzzy_score(a: str, b: str) -> float:
    """Return similarity ratio between two strings (0..1)."""
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()

def best_option_match(value: str, options: List[Dict]) -> Tuple[Optional[str], Optional[str], float, str]:
    """
    Try to match `value` against a list of {value, label} option dicts.
    Returns (matched_value, matched_label, score, strategy).
    """
    if not value or not options:
        return None, None, 0.0, "none"

    val_norm = normalize_text(value)
    val_expanded = expand_abbreviation(value)

    best_val = None
    best_lbl = None
    best_score = 0.0
    best_strategy = "none"

    for opt in options:
        opt_val = str(opt.get("value", ""))
        opt_lbl = str(opt.get("label", ""))
        opt_val_norm = normalize_text(opt_val)
        opt_lbl_norm = normalize_text(opt_lbl)
        opt_expanded_val = expand_abbreviation(opt_val)
        opt_expanded_lbl = expand_abbreviation(opt_lbl)

        # 1. Exact match
        if val_norm in (opt_val_norm, opt_lbl_norm):
            return opt_val, opt_lbl, 1.0, "exact"

        # 2. Degree level matching (e.g. BTech -> Bachelor of Technology)
        val_is_bachelor = "bachelor" in val_expanded or "b.s" in val_norm or "b.a" in val_norm or "btech" in val_norm or " be " in (" " + val_norm + " ")
        val_is_master = "master" in val_expanded or "m.s" in val_norm or "mba" in val_norm
        val_is_doctor = "doctor" in val_expanded or "phd" in val_norm
        
        opt_is_bachelor = "bachelor" in opt_expanded_lbl or "b.s" in opt_val_norm or "b.a" in opt_val_norm or "btech" in opt_val_norm or " be " in (" " + opt_val_norm + " ")
        opt_is_master = "master" in opt_expanded_lbl or "m.s" in opt_val_norm or "mba" in opt_val_norm
        opt_is_doctor = "doctor" in opt_expanded_lbl or "phd" in opt_val_norm

        if val_is_bachelor and opt_is_bachelor:
            score = 0.85
            if "science" in val_expanded and "science" in opt_expanded_lbl:
                score = 0.95
            elif "technology" in val_expanded and ("technology" in opt_expanded_lbl or "engineering" in opt_expanded_lbl):
                score = 0.92
            elif "arts" in val_expanded and "arts" in opt_expanded_lbl:
                score = 0.95
            if score > best_score:
                best_val, best_lbl, best_score, best_strategy = opt_val, opt_lbl, score, "normalized"
            continue

        if val_is_master and opt_is_master:
            score = 0.85
            if "science" in val_expanded and "science" in opt_expanded_lbl:
                score = 0.95
            elif "business" in val_expanded and "business" in opt_expanded_lbl:
                score = 0.95
            if score > best_score:
                best_val, best_lbl, best_score, best_strategy = opt_val, opt_lbl, score, "normalized"
            continue

        if val_is_doctor and opt_is_doctor:
            score = 0.90
            if score > best_score:
                best_val, best_lbl, best_score, best_strategy = opt_val, opt_lbl, score, "normalized"
            continue

        # 3. Word-subset matching (e.g. CS -> Computer Science)
        val_sig_words = [w for w in val_expanded.split() if len(w) > 3 and w not in ("and", "with", "for")]
        opt_sig_words = [w for w in opt_expanded_lbl.split() if len(w) > 3 and w not in ("and", "with", "for")]
        if val_sig_words and opt_sig_words:
            all_opt_in_val = all(w in val_sig_words for w in opt_sig_words)
            all_val_in_opt = all(w in opt_sig_words for w in val_sig_words)
            if all_opt_in_val or all_val_in_opt:
                score = 0.88
                if score > best_score:
                    best_val, best_lbl, best_score, best_strategy = opt_val, opt_lbl, score, "normalized"
                continue

        # 4. Standard normalize/substring matching
        if val_norm and (val_norm in opt_lbl_norm or opt_lbl_norm in val_norm):
            score = 0.92
            if score > best_score:
                best_val, best_lbl, best_score, best_strategy = opt_val, opt_lbl, score, "normalized"
            continue

        if val_expanded and (val_expanded == opt_expanded_val or val_expanded == opt_expanded_lbl
                              or val_expanded in opt_expanded_lbl or opt_expanded_lbl in val_expanded):
            score = 0.90
            if score > best_score:
                best_val, best_lbl, best_score, best_strategy = opt_val, opt_lbl, score, "normalized"
            continue

        # 5. Fuzzy match
        fscore = max(fuzzy_score(val_norm, opt_val_norm), fuzzy_score(val_norm, opt_lbl_norm),
                     fuzzy_score(val_expanded, opt_expanded_lbl))
        val_tokens = [t for t in val_norm.split() if len(t) > 2]
        lbl_tokens = [t for t in opt_lbl_norm.split() if len(t) > 2]
        if val_tokens and lbl_tokens:
            overlap = sum(1 for t in val_tokens if t in opt_lbl_norm) / len(val_tokens)
            if overlap >= 0.6:
                fscore = max(fscore, 0.82 + overlap * 0.15)
        if fscore > best_score:
            best_val, best_lbl, best_score, best_strategy = opt_val, opt_lbl, fscore, "fuzzy"

    if best_score >= 0.80:
        return best_val, best_lbl, best_score, best_strategy
    return None, None, best_score, "none"


def infer_country_from_location(location: Optional[str]) -> Optional[str]:
    """Infer a country from a resume location string."""
    if not location:
        return None
    loc = normalize_text(location)
    country_aliases = {
        "India": ["india", "bharat", "hyderabad", "bengaluru", "bangalore", "chennai", "mumbai", "delhi", "pune", "telangana", "andhra pradesh", "karnataka", "tamil nadu"],
        "United States": ["united states", "usa", "u s a", "us", "california", "new york", "texas", "san francisco", "seattle", "boston"],
        "Canada": ["canada", "toronto", "vancouver", "ontario", "british columbia"],
        "United Kingdom": ["united kingdom", "uk", "england", "london"],
        "Australia": ["australia", "sydney", "melbourne"],
    }
    for country, aliases in country_aliases.items():
        if any(alias in loc for alias in aliases):
            return country
    if "," in location:
        tail = location.split(",")[-1].strip()
        if tail and len(tail) > 2:
            return tail
    return None

def infer_country(profile: dict) -> Optional[str]:
    personal = profile.get("personal_info", {})
    location = personal.get("location")
    country = infer_country_from_location(location)
    if country:
        return country
    phone = personal.get("phone")
    if phone:
        phone_stripped = phone.strip()
        if phone_stripped.startswith("+91") or phone_stripped.startswith("91-"):
            return "India"
        elif phone_stripped.startswith("+1") or phone_stripped.startswith("1-"):
            return "United States"
        elif phone_stripped.startswith("+44") or phone_stripped.startswith("44-"):
            return "United Kingdom"
        elif phone_stripped.startswith("+61") or phone_stripped.startswith("61-"):
            return "Australia"
        elif phone_stripped.startswith("+971") or phone_stripped.startswith("971-"):
            return "United Arab Emirates"
            
        clean_phone = re.sub(r"[^\d+]", "", phone_stripped)
        if clean_phone.startswith("+91"):
            return "India"
        elif clean_phone.startswith("+1"):
            return "United States"
        elif clean_phone.startswith("+44"):
            return "United Kingdom"
        elif clean_phone.startswith("+61"):
            return "Australia"
        elif clean_phone.startswith("+971"):
            return "United Arab Emirates"
    return None

def is_phone_country_selector(field: dict) -> bool:
    field_type = field.get("type", "text")
    if field_type not in ("select", "combobox"):
        return False
    label = normalize_text(field.get("label", ""))
    ph = normalize_text(field.get("placeholder", ""))
    nr = normalize_text(field.get("nearby_text", ""))
    search_text = f"{label} {ph} {nr}"
    
    if any(kw in search_text for kw in ("phone code", "dial code", "country code", "phone country", "dialing code", "phone prefix", "intl code", "dial code", "calling code")):
        return True
    
    if any(kw in label for kw in ("prefix", "code", "country", "region", "dial", "flag")) and any(kw in search_text for kw in ("phone", "tel", "mobile")):
        return True
        
    return False

def parse_phone_number(phone: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Given a phone number string, return (country_name, prefix, local_number).
    """
    if not phone:
        return None, None, None
    
    phone_stripped = phone.strip()
    
    prefixes = [
        ("+91", "India"),
        ("91-", "India"),
        ("+1", "United States"),
        ("1-", "United States"),
        ("+44", "United Kingdom"),
        ("44-", "United Kingdom"),
        ("+61", "Australia"),
        ("61-", "Australia"),
        ("+971", "United Arab Emirates"),
        ("971-", "United Arab Emirates"),
    ]
    
    for prefix_str, country in prefixes:
        if phone_stripped.startswith(prefix_str):
            clean_prefix = "+" + prefix_str.replace("-", "").replace("+", "")
            local = phone_stripped[len(prefix_str):].strip()
            local = re.sub(r"^[ \-()]+", "", local)
            return country, clean_prefix, local
            
    clean_phone = re.sub(r"[\s\(\)\-]", "", phone_stripped)
    if clean_phone.startswith("+91"):
        return "India", "+91", clean_phone[3:]
    elif clean_phone.startswith("+1"):
        return "United States", "+1", clean_phone[2:]
    elif clean_phone.startswith("+44"):
        return "United Kingdom", "+44", clean_phone[3:]
    elif clean_phone.startswith("+61"):
        return "Australia", "+61", clean_phone[3:]
    elif clean_phone.startswith("+971"):
        return "United Arab Emirates", "+971", clean_phone[4:]
        
    m = re.match(r"^(\+\d+)(.*)$", phone_stripped)
    if m:
        return None, m.group(1), m.group(2).strip()
        
    return None, None, phone_stripped

def match_phone_country_option(options: List[dict], country: Optional[str], prefix: Optional[str]) -> Tuple[Optional[str], Optional[str], float]:
    """
    Search options for a phone country dropdown.
    Returns (option_value, option_label, score).
    """
    if not options:
        return None, None, 0.0
        
    country_norm = normalize_text(country) if country else ""
    prefix_digits = re.sub(r"\D", "", prefix) if prefix else ""
    
    best_val = None
    best_lbl = None
    best_score = 0.0
    
    for opt in options:
        val = str(opt.get("value", ""))
        lbl = str(opt.get("label", ""))
        val_norm = normalize_text(val)
        lbl_norm = normalize_text(lbl)
        
        has_country = False
        if country_norm and (country_norm in val_norm or country_norm in lbl_norm):
            has_country = True
            
        has_prefix = False
        if prefix_digits:
            val_digits = re.sub(r"\D", " ", val).split()
            lbl_digits = re.sub(r"\D", " ", lbl).split()
            if prefix_digits in val_digits or prefix_digits in lbl_digits or prefix_digits == val or prefix_digits == lbl:
                has_prefix = True
            elif ("+" + prefix_digits) in val or ("+" + prefix_digits) in lbl:
                has_prefix = True
            elif prefix_digits in val or prefix_digits in lbl:
                has_prefix = True
                
        if has_country and has_prefix:
            return val, lbl, 1.0
            
        if has_prefix:
            score = 0.95
            if score > best_score:
                best_val, best_lbl, best_score = val, lbl, score
                
        if has_country:
            score = 0.90
            if score > best_score:
                best_val, best_lbl, best_score = val, lbl, score
                
    if best_score >= 0.90:
        return best_val, best_lbl, best_score
        
    return None, None, 0.0

def _safe_list_items(items: Any) -> List[dict]:
    """Return a list of dictionaries from pydantic/list-like values."""
    if not items:
        return []
    out = []
    for item in items:
        if isinstance(item, dict):
            out.append(item)
        elif hasattr(item, "model_dump"):
            out.append(item.model_dump())
        elif hasattr(item, "dict"):
            out.append(item.dict())
    return out


def _extract_year(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    m = re.search(r"(19|20)\d{2}", str(text))
    return m.group(0) if m else None


def _add_unique(candidates: List[str], value: Any) -> None:
    if value is None:
        return
    value = str(value).strip()
    if not value:
        return
    if value.lower() not in {c.lower() for c in candidates}:
        candidates.append(value)


def get_candidate_profile_values(field: dict, profile: dict) -> List[str]:
    """Return targeted candidate values for a specific form field.

    Important: this should NOT return the whole resume keyword bag for every
    field. Gemini works best when each field receives only the likely values.
    """
    label = normalize_text(field.get("label", "") or "")
    nearby = normalize_text(field.get("nearby_text", "") or "")
    placeholder = normalize_text(field.get("placeholder", "") or "")
    section = normalize_text(field.get("section", "") or "")
    field_id = normalize_text(field.get("field_id", "") or "")
    field_type = normalize_text(field.get("type", "") or "")
    search_text = f"{field_id} {label} {placeholder} {nearby} {section}"

    label_search = f" {field_id} {label} {placeholder} "
    padded_search = f" {search_text} "

    personal = profile.get("personal_info", {}) or {}
    education = _safe_list_items(profile.get("education", []))
    experience = _safe_list_items(profile.get("experience", []))
    skills = profile.get("skills", []) or []
    projects = _safe_list_items(profile.get("projects", []))
    additional = profile.get("additional_info", {}) or {}

    candidates: List[str] = []

    if is_eeo_field(label, nearby):
        return ["[SKIP]"]

    if field_type == "file" or any(kw in label_search for kw in ("resume", "cv", "curriculum vitae", "attach")):
        return []

    if any(kw in search_text for kw in (
        "visa", "sponsorship", "work authorization", "authorize",
        "legally authorized", "right to work", "employment visa"
    )):
        _add_unique(candidates, additional.get("visa_sponsorship"))
        return candidates

    if any(kw in label_search for kw in (
        "start year", "start date year", "start-year", "enrollment year", "year started"
    )):
        if education:
            start, _ = infer_education_years(education[0])
            _add_unique(candidates, start or _extract_year(education[0].get("start_year")))
        return candidates

    if any(kw in label_search for kw in (
        "end year", "end date year", "end-year", "graduation year", "grad year",
        "year of graduation", "expected graduation"
    )):
        if education:
            _, end = infer_education_years(education[0])
            _add_unique(candidates, end or _extract_year(education[0].get("end_year")))
        return candidates

    if any(kw in label for kw in ("first name", "firstname", "given name", "preferred first name")) or field_id == "first_name":
        _add_unique(candidates, personal.get("first_name"))
        return candidates

    if any(kw in label for kw in ("last name", "lastname", "surname", "family name")) or field_id == "last_name":
        _add_unique(candidates, personal.get("last_name"))
        return candidates

    if "name" in label and not any(kw in label_search for kw in (" company ", " employer ", " school ", " university ", " college ")):
        fn = personal.get("first_name")
        ln = personal.get("last_name")
        _add_unique(candidates, f"{fn} {ln}" if fn and ln else fn)
        return candidates

    if "email" in label_search or "e mail" in label_search or field_id == "email":
        _add_unique(candidates, personal.get("email"))
        return candidates

    if any(f" {kw} " in label_search for kw in ("phone", "tel", "mobile", "cell", "dial code", "phone code", "prefix", "calling code")) or field_id == "phone":
        phone = personal.get("phone")
        _add_unique(candidates, phone)
        country_name, prefix, local = parse_phone_number(phone)
        _add_unique(candidates, prefix)
        _add_unique(candidates, local)
        _add_unique(candidates, country_name)
        return candidates

    if "linkedin" in label_search or "linked in" in label_search:
        _add_unique(candidates, personal.get("linkedin"))
        return candidates

    if "github" in label_search or "git hub" in label_search:
        _add_unique(candidates, personal.get("github"))
        return candidates

    if any(f" {kw} " in label_search for kw in ("portfolio", "website", "web site", "blog", "personal site", "personal link", "url")):
        _add_unique(candidates, personal.get("portfolio"))
        return candidates

    if any(f" {kw} " in label_search for kw in ("country", "country region", "nation", "region")):
        phone_country, prefix, _ = parse_phone_number(personal.get("phone"))
        if is_phone_country_selector(field) or "phone" in section or "phone" in nearby or field_id == "country":
            _add_unique(candidates, phone_country)
            _add_unique(candidates, prefix)
        _add_unique(candidates, infer_country(profile))
        _add_unique(candidates, personal.get("location"))
        return candidates

    if any(f" {kw} " in padded_search for kw in (
        "location", "city", "address", "zip", "postal", "reside", "living in"
    )) or ("state" in search_text and "united states" not in search_text):
        _add_unique(candidates, personal.get("location"))
        return candidates

    if any(f" {kw} " in padded_search for kw in ("school", "university", "college", "institution", "alma mater")):
        for edu in education:
            _add_unique(candidates, edu.get("school"))
        return candidates

    if "degree" in search_text or "qualification" in search_text or "highest education" in search_text:
        for edu in education:
            deg = edu.get("degree")
            _add_unique(candidates, deg)
            expanded = expand_abbreviation(deg or "")
            if expanded and expanded != normalize_text(deg or ""):
                _add_unique(candidates, expanded)
        return candidates

    if any(kw in search_text for kw in ("discipline", "major", "field of study", "concentration", "specialization")):
        for edu in education:
            disc = edu.get("discipline")
            _add_unique(candidates, disc)
            expanded = expand_abbreviation(disc or "")
            if expanded and expanded != normalize_text(disc or ""):
                _add_unique(candidates, expanded)
        return candidates

    is_current = "current" in search_text
    is_past = "past" in search_text or "previous" in search_text
    wants_title = any(kw in search_text for kw in ("title", "role", "position", "designation"))
    wants_company = any(f" {kw} " in padded_search for kw in ("company", "employer", "organization", "firm"))

    if wants_title:
        if is_current:
            _add_unique(candidates, additional.get("current_title"))
            if experience:
                _add_unique(candidates, experience[0].get("title"))
        elif is_past:
            for exp in experience[1:] or experience:
                _add_unique(candidates, exp.get("title"))
        else:
            _add_unique(candidates, additional.get("current_title"))
            for exp in experience:
                _add_unique(candidates, exp.get("title"))
        return candidates

    if wants_company:
        if is_current:
            _add_unique(candidates, additional.get("current_company"))
            if experience:
                _add_unique(candidates, experience[0].get("company"))
        elif is_past:
            for exp in experience[1:] or experience:
                _add_unique(candidates, exp.get("company"))
        else:
            _add_unique(candidates, additional.get("current_company"))
            for exp in experience:
                _add_unique(candidates, exp.get("company"))
        return candidates

    if any(kw in search_text for kw in (
        "software engineer", "engineer are you", "skills", "technologies", "technical skills",
        "tech stack", "keywords", "programming languages"
    )) or field_type in ("checkbox_group", "multiselect"):
        _add_unique(candidates, additional.get("current_title"))
        for exp in experience:
            _add_unique(candidates, exp.get("title"))
        for s in skills[:25]:
            _add_unique(candidates, s)
        for proj in projects[:3]:
            _add_unique(candidates, proj.get("name"))
            for t in proj.get("technologies", []) or []:
                _add_unique(candidates, t)
        return candidates

    if any(kw in search_text for kw in ("project", "projects", "proud of", "list project", "describe project")):
        for proj in projects[:3]:
            _add_unique(candidates, proj.get("name"))
            _add_unique(candidates, (proj.get("description") or "")[:180])
        return candidates

    return candidates

def infer_education_years(edu: dict) -> Tuple[Optional[str], Optional[str]]:
    """Return start/end years, inferring a 4-year B.Tech/Bachelor program if possible."""
    start = edu.get("start_year")
    end = edu.get("end_year")
    degree_text = normalize_text(f"{edu.get('degree', '')} {edu.get('discipline', '')}")
    is_four_year_degree = any(
        kw in degree_text
        for kw in ("btech", "b tech", "bachelor of technology", "bachelor of engineering")
    )
    if is_four_year_degree:
        try:
            if end and not start:
                start = str(int(str(end)[:4]) - 4)
            elif start and not end:
                end = str(int(str(start)[:4]) + 4)
        except ValueError:
            pass
    return start, end

# ---------------------------------------------------------------------------
# EEO / Demographic Safety Rules
# ---------------------------------------------------------------------------

EEO_KEYWORDS = frozenset([
    "gender", "race", "ethnicity", "veteran", "disability",
    "voluntary self-identification", "self-identification", "self identification",
    "hispanic", "latino", "latina", "latinx", "sex ", "sex*", "sexual",
    "protected", "demographic", "minority", "indigenous", "native",
    "african american", "asian american", "pacific islander",
])

def is_eeo_field(label: str, nearby_text: str = "") -> bool:
    combined = normalize_text(f"{label} {nearby_text}")
    return any(kw in combined for kw in EEO_KEYWORDS)

# ---------------------------------------------------------------------------
# Mapping Cache
# ---------------------------------------------------------------------------

_mapping_cache: Dict[str, List[dict]] = {}

def _cache_key(form_url: str, profile: dict) -> str:
    profile_str = json.dumps(profile, sort_keys=True, default=str)
    h = hashlib.sha256(f"{form_url}|{profile_str}".encode()).hexdigest()[:16]
    return h

# ---------------------------------------------------------------------------
# Projects Textarea Generator
# ---------------------------------------------------------------------------

def generate_projects_text(projects: List[dict]) -> Optional[str]:
    if not projects:
        return None
    lines = []
    for i, proj in enumerate(projects[:3], 1):
        name = proj.get("name") or "Project"
        desc = proj.get("description") or ""
        techs = proj.get("technologies", [])
        tech_str = f" | {', '.join(techs)}" if techs else ""
        lines.append(f"{i}. {name} — {desc}{tech_str}".strip(" —"))
    return "\n".join(lines) if lines else None

# ---------------------------------------------------------------------------
# Rule-Based Mapper
# ---------------------------------------------------------------------------

def _make_mapping(
    field: dict,
    profile_path: Optional[str] = None,
    value: Any = None,
    confidence: float = 0.0,
    strategy: str = "unknown",
    reason: str = "",
    action: str = "fill",
    selected_option: Optional[str] = None,
    selected_options: Optional[List[str]] = None,
    selected_option_label: Optional[str] = None,
    selected_option_labels: Optional[List[str]] = None,
    status: Optional[str] = None,
) -> dict:
    """Build a standardized mapping dict.

    This signature is keyword-safe and prevents duplicate `value` crashes.
    """
    if status is None:
        if action == "skip":
            status = "skipped"
        elif action == "requires_review":
            status = "needs_review"
        elif action == "upload_file":
            status = "ready"
        else:
            status = "ready" if float(confidence or 0.0) >= 0.75 else "needs_review"

    return {
        "mapping_id": str(uuid.uuid4()),
        "field_id": field.get("field_id", ""),
        "selector": field.get("selector", ""),
        "field_label": field.get("label", "") or field.get("field_id", ""),
        "type": field.get("type", "text"),
        "action": action,
        "profile_path": profile_path,
        "value": str(value) if value is not None else None,
        "selected_option": selected_option,
        "selected_option_label": selected_option_label,
        "selected_options": selected_options or [],
        "selected_option_labels": selected_option_labels or [],
        "options": field.get("options", []),
        "confidence_score": round(float(confidence or 0.0), 3),
        "strategy": strategy,
        "reason": reason,
        "status": status,
    }

def _mapping_from_option_match(field: dict, profile_path: Optional[str], value: Any,
                               reason: str) -> Optional[dict]:
    options = field.get("options", [])
    if value is None or not options:
        return None
    matched_val, matched_lbl, match_score, strat = best_option_match(str(value), options)
    if not matched_val or match_score < 0.80:
        return None
    return _make_mapping(
        field, profile_path, matched_val, match_score, strat, reason,
        action="select",
        selected_option=matched_val,
        selected_option_label=matched_lbl or matched_val,
    )

def rule_map_field(field: dict, profile: dict, resume_file_path: Optional[str] = None, has_phone_country_dropdown: bool = False) -> Optional[dict]:
    """
    Attempt to match a single field using local rule-based logic.
    Returns a mapping dict or None if no rule matched.
    """
    label = field.get("label", "") or ""
    nearby = field.get("nearby_text", "") or ""
    field_type = field.get("type", "text")
    options = field.get("options", [])
    required = field.get("required", False)

    lbl = normalize_text(label)
    ph = normalize_text(field.get("placeholder", "") or "")
    nr = normalize_text(nearby)
    search_text = f"{lbl} {ph} {nr}"

    personal = profile.get("personal_info", {})
    education = profile.get("education", [])
    experience = profile.get("experience", [])
    skills = profile.get("skills", [])
    projects = profile.get("projects", [])
    additional = profile.get("additional_info", {})
    country = infer_country(profile)

    # ── EEO Safety Skip ──────────────────────────────────────────────────────
    if is_eeo_field(label, nearby):
        return _make_mapping(field, None, None, 1.0, "safety_skip",
                             "Sensitive demographic/EEO field — skipped by default", action="skip")

    # ── File Upload ──────────────────────────────────────────────────────────
    if field_type == "file" or any(kw in search_text for kw in ("resume", " cv ", "curriculum vitae", "attach")):
        path = resume_file_path or personal.get("resume_file_path")
        return _make_mapping(field, "resume_file_path", path, 1.0, "rule",
                             "Resume/CV file upload field", action="upload_file")

    # ── Personal Info ─────────────────────────────────────────────────────────
    if any(kw in lbl for kw in ("first name", "firstname", "given name", "first")):
        val = personal.get("first_name")
        return _make_mapping(field, "personal_info.first_name", val, 1.0, "rule",
                             "Matched first name field")

    if any(kw in lbl for kw in ("last name", "lastname", "surname", "family name")):
        val = personal.get("last_name")
        return _make_mapping(field, "personal_info.last_name", val, 1.0, "rule",
                             "Matched last name field")

    if "email" in lbl or "email" in ph:
        val = personal.get("email")
        return _make_mapping(field, "personal_info.email", val, 1.0, "rule",
                             "Matched email field")

    if any(kw in lbl for kw in ("phone", "tel", "mobile", "cell")):
        phone_val = personal.get("phone")
        country_name, prefix_val, local_val = parse_phone_number(phone_val)
        
        if is_phone_country_selector(field):
            best_val, best_lbl, score = match_phone_country_option(options, country_name, prefix_val)
            if best_val:
                return _make_mapping(
                    field, "personal_info.phone", prefix_val, score, "phone_country_code",
                    "Matched phone country/prefix selector",
                    action="select",
                    selected_option=best_val,
                    selected_option_label=best_lbl
                )
            else:
                return _make_mapping(
                    field, "personal_info.phone", None, 0.0, "failed",
                    "Phone country selector detected but no matching option found in dropdown",
                    action="skip", status="needs_review"
                )
        
        # Main phone input field
        val = phone_val
        reason = "Matched phone field"
        if has_phone_country_dropdown and local_val:
            val = local_val
            reason = "Matched phone field (local number only, prefix-stripped because prefix dropdown is present)"
            
        return _make_mapping(field, "personal_info.phone", val, 0.95, "rule", reason)


    if "linkedin" in lbl or "linkedin" in ph:
        val = personal.get("linkedin")
        return _make_mapping(field, "personal_info.linkedin", val, 0.95, "rule",
                             "Matched LinkedIn field")

    if "github" in lbl or "github" in ph or "git hub" in lbl:
        val = personal.get("github")
        return _make_mapping(field, "personal_info.github", val, 0.95, "rule",
                             "Matched GitHub field")

    if any(kw in lbl for kw in ("portfolio", "personal website", "personal site", "website url", "personal link")):
        val = personal.get("portfolio")
        return _make_mapping(field, "personal_info.portfolio", val, 0.90, "rule",
                             "Matched portfolio/website field")

    if any(kw in lbl for kw in ("country", "country/region", "country region", "nation")):
        val = country
        if field_type in ("select", "radio", "combobox") and options and val:
            matched = _mapping_from_option_match(
                field, "personal_info.location.country", val,
                "Country inferred from location and matched dropdown option",
            )
            if matched:
                return matched
        return _make_mapping(field, "personal_info.location.country", val, 0.88, "rule",
                             "Country inferred from profile location")

    if any(kw in lbl for kw in ("location", "city", "city state", "current location", "address")):
        val = personal.get("location")
        if field_type in ("select", "radio", "combobox") and options and val:
            matched = _mapping_from_option_match(
                field, "personal_info.location", val,
                "Location matched dropdown option",
            )
            if matched:
                return matched
        return _make_mapping(field, "personal_info.location", val, 0.90, "rule",
                             "Matched location/city field")

    # ── Education ─────────────────────────────────────────────────────────────
    if education:
        edu = education[0]
        edu_start_year, edu_end_year = infer_education_years(edu)
        if any(kw in lbl for kw in ("school", "university", "college", "institution", "alma mater")):
            val = edu.get("school")
            if field_type in ("select", "combobox") and options and val:
                # Try to match harvested options directly
                matched = _mapping_from_option_match(
                    field, "education[0].school", val,
                    "School matched dropdown option",
                )
                if matched:
                    return matched
            if field_type in ("select", "combobox"):
                # Typeahead/searchable dropdown — keep as select so client types to search
                return _make_mapping(field, "education[0].school", val, 0.90, "rule",
                                     "School/university typeahead dropdown — client will type to search",
                                     action="select",
                                     selected_option=val,
                                     selected_option_label=val)
            return _make_mapping(field, "education[0].school", val, 0.90, "rule",
                                 "Matched school/university field")

        if "degree" in lbl or "qualification" in lbl or "highest education" in lbl:
            val = edu.get("degree")
            if field_type in ("select", "radio", "combobox") and options and val:
                matched = _mapping_from_option_match(
                    field, "education[0].degree", val,
                    "Degree matched dropdown option",
                )
                if matched:
                    return matched
            return _make_mapping(field, "education[0].degree", val, 0.85, "rule",
                                 "Matched degree field")

        if any(kw in lbl for kw in ("discipline", "major", "field of study", "concentration", "specialization")):
            val = edu.get("discipline")
            if field_type in ("select", "radio", "combobox") and options and val:
                matched = _mapping_from_option_match(
                    field, "education[0].discipline", val,
                    "Discipline matched dropdown option",
                )
                if matched:
                    return matched
            return _make_mapping(field, "education[0].discipline", val, 0.85, "rule",
                                 "Matched discipline/major field")

        if any(kw in lbl for kw in ("graduation year", "grad year", "end year", "year of graduation", "expected graduation")):
            val = edu_end_year
            if field_type in ("select", "radio", "combobox") and options and val:
                matched = _mapping_from_option_match(
                    field, "education[0].end_year", val,
                    "Education end year matched dropdown option",
                )
                if matched:
                    return matched
            return _make_mapping(field, "education[0].end_year", val, 0.85, "rule",
                                 "Matched graduation/end year")

        if any(kw in lbl for kw in ("start year", "enrollment year", "year started")):
            val = edu_start_year
            if field_type in ("select", "radio", "combobox") and options and val:
                matched = _mapping_from_option_match(
                    field, "education[0].start_year", val,
                    "Education start year matched dropdown option",
                )
                if matched:
                    return matched
            return _make_mapping(field, "education[0].start_year", val, 0.85, "rule",
                                 "Matched start year")

    # ── Experience ────────────────────────────────────────────────────────────
    if any(kw in lbl for kw in ("current company", "current employer", "current organization")):
        val = additional.get("current_company") or (experience[0].get("company") if experience else None)
        return _make_mapping(field, "experience[0].company", val, 0.90, "rule",
                             "Matched current company field")

    if any(kw in lbl for kw in ("current title", "current role", "current position", "job title", "your title")):
        val = additional.get("current_title") or (experience[0].get("title") if experience else None)
        return _make_mapping(field, "experience[0].title", val, 0.90, "rule",
                             "Matched current title/role field")

    if any(kw in lbl for kw in ("company", "employer", "organization")) and experience:
        val = experience[0].get("company")
        return _make_mapping(field, "experience[0].company", val, 0.80, "rule",
                             "Matched company/employer field")

    # ── Skills ────────────────────────────────────────────────────────────────
    if any(kw in lbl for kw in ("skills", "technologies", "technical skills", "tech stack", "keywords")):
        val = ", ".join(skills) if skills else None
        return _make_mapping(field, "skills", val, 0.85, "rule",
                             "Matched skills/technologies field")

    # ── Projects Textarea ─────────────────────────────────────────────────────
    if any(kw in lbl for kw in ("project", "projects", "proud of", "list project", "describe project")):
        val = generate_projects_text(projects)
        return _make_mapping(field, "projects", val, 0.85, "rule",
                             "Generated project list from profile.projects")

    # ── Visa / Work Authorization ─────────────────────────────────────────────
    if any(kw in lbl for kw in ("visa", "sponsorship", "work authorization", "authorize", "legally authorized",
                                  "right to work", "employment authorization")):
        val = additional.get("visa_sponsorship")
        if field_type in ("select", "radio", "combobox") and options and val:
            matched = _mapping_from_option_match(
                field, "additional_info.visa_sponsorship", val,
                "Visa sponsorship matched dropdown option",
            )
            if matched:
                return matched
        return _make_mapping(field, "additional_info.visa_sponsorship", val, 0.85, "rule",
                             "Matched visa/work authorization field")

    # ── Checkbox (single) — Acknowledgment ───────────────────────────────────
    if field_type == "checkbox":
        if any(kw in search_text for kw in ("agree", "accept", "acknowledge", "confirm", "certify", "consent")):
            return _make_mapping(field, None, "true", 0.90, "rule",
                                 "Agreement/acknowledgment checkbox — checked by default")
        return None  # Other single checkboxes → unresolved

    # ── Select / Radio — try options matching with profile values ─────────────
    if field_type in ("select", "radio", "combobox") and options:
        # Try matching any profile value against options
        inferred_start_year, inferred_end_year = infer_education_years(education[0]) if education else (None, None)
        profile_values = [
            (personal.get("location"), "personal_info.location"),
            (country, "personal_info.location.country"),
            (inferred_start_year, "education[0].start_year"),
            (inferred_end_year, "education[0].end_year"),
            (education[0].get("degree") if education else None, "education[0].degree"),
            (education[0].get("discipline") if education else None, "education[0].discipline"),
            (additional.get("visa_sponsorship"), "additional_info.visa_sponsorship"),
        ]
        for pv, pp in profile_values:
            if pv:
                matched = _mapping_from_option_match(
                    field, pp, pv, "Matched via dropdown option comparison",
                )
                if matched:
                    return matched

    return None  # No rule matched

def normalized_map_field(field: dict, profile: dict) -> Optional[dict]:
    """
    Secondary pass: normalize the field label and try expanded abbreviation matching
    against the same rule keywords.
    """
    lbl_expanded = expand_abbreviation(field.get("label", "") or "")
    # Re-run rule matcher with expanded label as a synthetic field
    synthetic = {**field, "label": lbl_expanded}
    result = rule_map_field(synthetic, profile)
    if result and result.get("strategy") == "rule":
        result["strategy"] = "normalized"
        result["reason"] = f"Matched after label normalization/expansion: '{lbl_expanded}'"
    return result

# ---------------------------------------------------------------------------
# Checkbox Group Mapper
# ---------------------------------------------------------------------------

def map_checkbox_group(field: dict, profile: dict) -> dict:
    """
    For checkbox_group fields: match profile data (skills, experience titles, projects)
    against each option and select only strongly supported ones.
    """
    options = field.get("options", [])
    skills = [normalize_text(s) for s in profile.get("skills", [])]
    exp_titles = [normalize_text(e.get("title", "") or "") for e in profile.get("experience", [])]
    exp_descs = [normalize_text(e.get("description", "") or "") for e in profile.get("experience", [])]
    proj_descs = [normalize_text(p.get("description", "") or "") + " " +
                  normalize_text(p.get("name", "") or "")
                  for p in profile.get("projects", [])]
    proj_techs = []
    for p in profile.get("projects", []):
        proj_techs.extend([normalize_text(t) for t in p.get("technologies", [])])

    all_profile_text = " ".join(skills + exp_titles + exp_descs + proj_descs + proj_techs)

    role_keywords = {
        "Backend Engineer": ["backend", "fastapi", "node", "express", "api", "server"],
        "API Engineer": ["api", "rest", "fastapi", "express"],
        "Developer Productivity Engineer": ["developer productivity", "ci", "cd", "github actions", "automation", "internal tools", "code review"],
        "Infrastructure Engineer": ["docker", "kubernetes", "linux", "ci cd", "deployment"],
        "Frontend Engineer": ["react", "next", "tailwind", "ui", "frontend"],
        "Fullstack Generalist Engineer": ["react + backend", "full stack", "full-stack"],
        "Data Engineer": ["data", "pipelines", "database", "qdrant", "analytics"]
    }

    selected = []
    for opt in options:
        opt_label = normalize_text(opt.get("label", "") or opt.get("value", ""))
        
        # Check if the option matches a known role
        matched_role = None
        for rname in role_keywords.keys():
            if fuzzy_score(opt_label, rname) >= 0.85 or opt_label == normalize_text(rname):
                matched_role = rname
                break
                
        if matched_role:
            keywords = role_keywords[matched_role]
            # Verify role support (matches count)
            matches = [k for k in keywords if k in all_profile_text]
            # Strong match threshold:
            # - For Fullstack: matches >= 1
            # - For others: matches >= 2
            required_matches = 1 if matched_role == "Fullstack Generalist Engineer" else 2
            if len(matches) >= required_matches:
                selected.append(opt.get("value") or opt.get("label"))
        else:
            # Fallback to general keyword logic
            opt_words = opt_label.split()
            if not opt_words:
                continue
            match_count = sum(1 for w in opt_words if len(w) > 3 and w in all_profile_text)
            match_ratio = match_count / len(opt_words)
            if match_ratio >= 0.5:
                fscore = max(fuzzy_score(opt_label, t) for t in (skills + [all_profile_text[:500]]))
                if fscore >= 0.65 or match_ratio >= 0.7:
                    selected.append(opt.get("value") or opt.get("label"))

    if selected:
        return _make_mapping(field, "skills+experience", ",".join(selected),
                             0.85, "rule",
                             f"Selected {len(selected)} options matching profile skills/experience",
                             action="multi_select", selected_options=selected)
    return _make_mapping(field, None, None, 0.0, "rule",
                         "No checkbox options matched profile skills/experience",
                         action="skip")

# ---------------------------------------------------------------------------
# Gemini Fallback
# ---------------------------------------------------------------------------

class GeminiFieldMapping(BaseModel):
    field_id: str
    action: str
    fill_value: Optional[str] = None
    selected_option: Optional[str] = None
    selected_option_label: Optional[str] = None
    selected_options: List[str] = Field(default_factory=list)
    selected_option_labels: List[str] = Field(default_factory=list)
    confidence: float
    reason: str

class GeminiFormMapperResult(BaseModel):
    mappings: List[GeminiFieldMapping]

def rank_local_options(candidate_values: List[str], options: List[dict], field_type: str, label: str) -> List[dict]:
    if not options:
        return []
    
    # Gemini 2.5 has a massive context window, so we don't need to aggressively truncate.
    # Pass up to 400 options to ensure countries and standard lists are fully covered.
    top_k = 400
        
    if not candidate_values:
        return options[:top_k]
        
    scored_options = []
    for opt in options:
        max_score = 0.0
        for cv in candidate_values:
            _, _, score, _ = best_option_match(cv, [opt])
            if score > max_score:
                max_score = score
        scored_options.append((max_score, opt))
        
    # Sort by score descending
    scored_options.sort(key=lambda x: x[0], reverse=True)
    return [opt for score, opt in scored_options][:top_k]

def _parse_gemini_json(response_text: str) -> dict:
    """Safely strips markdown fences and parses JSON from Gemini's response."""
    if not response_text:
        logger.error("Empty response text passed to _parse_gemini_json")
        return {}
    clean = response_text.strip()
    if clean.startswith("```"):
        parts = clean.split("```")
        if len(parts) >= 3:
            clean = parts[1]
        else:
            clean = parts[0]
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from Gemini response: {e}\nRaw text:\n{response_text}")
        raise e
import json
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.genai.errors import APIError

@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1.5, min=2, max=15),
    reraise=True
)
def query_gemini_form_mapper(client, profile: dict, all_fields: List[dict]) -> List[dict]:
    """
    Unified Gemini Form Mapper.
    """
    from google.genai import types

    personal = profile.get("personal_info", {})
    education = profile.get("education", [])
    experience = profile.get("experience", [])
    skills = profile.get("skills", [])
    projects = profile.get("projects", [])
    additional = profile.get("additional_info", {})

    profile_summary = {
        "personal_info": {k: v for k, v in personal.items() if v},
        "education": [
            {k: v for k, v in edu.items() if v}
            for edu in education[:2]
        ],
        "experience": [
            {k: v for k, v in exp.items() if v and k != "description"}
            for exp in experience[:2]
        ],
        "skills": skills[:25],
        "projects": [{"name": p.get("name"), "description": p.get("description", "")[:120],
                      "technologies": p.get("technologies", [])} for p in projects[:3]],
        "additional_info": {k: v for k, v in additional.items() if v},
    }

    compact_fields = []
    for f in all_fields:
        compact_fields.append({
            "field_id": f.get("field_id"),
            "label": f.get("label"),
            "type": f.get("type"),
            "required": f.get("required", False),
            "options": f.get("options", []),
            "candidate_profile_values": f.get("candidate_profile_values", [])
        })

    system_prompt = (
        "You are an expert form autofill AI. Your job is to make the final mapping decision for every logical field provided.\n"
        "Rules:\n"
        "1. For text/plain fields (type: text, email, tel, number, url, textarea, date): Set action='fill' and set fill_value to the extracted profile string.\n"
        "2. For option fields (type: select, radio, checkbox, multiselect, checkbox_group): Select EXACTLY from the provided options. Never invent option values or labels.\n"
        "3. Advanced Semantic Matching: If an exact match isn't found, find the closest semantic meaning. For example:\n"
        "   - 'Male' matches 'Man' or 'Male/Man'\n"
        "   - 'United States' matches 'USA' or 'United States of America'\n"
        "   - 'B.Tech' matches 'Bachelor of Technology' or 'Bachelor\\'s Degree'\n"
        "   - 'Yes' matches 'I identify as one or more of the classifications'\n"
        "4. Understand similarity, abbreviations, and aliases (e.g., IIT Bombay = Indian Institute of Technology Bombay, CSE = Computer Science, +91 = India).\n"
        "5. For type 'checkbox_group' or 'multiselect', set action='multi_select', and fill selected_options / selected_option_labels with one or more matched option values/labels.\n"
        "6. For type 'radio', set action='select', and select exactly ONE option in selected_option / selected_option_label.\n"
        "7. For type 'select' or 'combobox', try to pick an exact option with action='select'. If NO options match (or options are empty), you MAY set action='fill' and provide the best text string to type into the search box as fill_value.\n"
        "8. For file uploads (type: file): set action='upload_file' and set fill_value='resume' or 'cover_letter' based on the label.\n"
        "8. If a field's candidate_profile_values indicates '[SKIP]', set action='skip'.\n"
        "9. If you cannot find a reasonable semantic match for a required field, set action='requires_review'.\n"
        "10. You MUST return exactly one mapping entry for every field_id provided in the input.\n"
        "11. Return JSON only conforming to the schema."
    )

    user_content = (
        f"Profile Summary:\n{json.dumps(profile_summary, indent=2)}\n\n"
        f"Fields to Map:\n{json.dumps(compact_fields, indent=2)}\n\n"
        "Map every field to the profile and return mappings."
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=GeminiFormMapperResult,
        ),
    )
    raw = _parse_gemini_json(response.text)
    return raw.get("mappings", [])

def convert_gemini_item_to_mapping(field: dict, item: Any) -> dict:
    """Safely convert Gemini output into the standard mapping format.

    The converter never forwards the raw Gemini item as **kwargs, so it cannot
    pass duplicate values to _make_mapping.
    """
    if not isinstance(item, dict):
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        elif hasattr(item, "dict"):
            item = item.dict()
        else:
            item = dict(item)
    item = dict(item)

    action = item.get("action") or "skip"
    fill_value = item.get("fill_value")
    selected_option = item.get("selected_option")
    selected_option_label = item.get("selected_option_label")
    selected_options = item.get("selected_options") or []
    selected_option_labels = item.get("selected_option_labels") or []
    confidence = float(item.get("confidence") or 0.0)
    reason = item.get("reason") or ""

    if action == "select":
        value = selected_option or selected_option_label
    elif action == "multi_select":
        value = ",".join(str(x) for x in selected_options)
    elif action == "upload_file":
        value = fill_value or "resume"
    else:
        value = fill_value

    if action == "requires_review":
        status = "needs_review"
    elif action == "skip":
        status = "skipped"
    elif action == "upload_file":
        status = "ready"
    else:
        status = "ready" if confidence >= 0.75 else "needs_review"

    return _make_mapping(
        field=field,
        profile_path=None,
        value=value,
        confidence=confidence,
        strategy="gemini",
        reason=reason,
        action=action,
        selected_option=selected_option,
        selected_option_label=selected_option_label,
        selected_options=selected_options,
        selected_option_labels=selected_option_labels,
        status=status,
    )

def _enrich_mapping_from_field(mapping: dict, field: dict) -> dict:
    """Attach field options and resolve human-readable labels for dropdown injection."""
    if not mapping.get("options"):
        mapping["options"] = field.get("options", [])

    if mapping.get("action") == "select" and mapping.get("selected_option"):
        if not mapping.get("selected_option_label"):
            for opt in mapping.get("options", []):
                if str(opt.get("value")) == str(mapping["selected_option"]):
                    mapping["selected_option_label"] = opt.get("label")
                    break
                if normalize_text(str(opt.get("label", ""))) == normalize_text(str(mapping["selected_option"])):
                    mapping["selected_option_label"] = opt.get("label")
                    mapping["selected_option"] = opt.get("value") or opt.get("label")
                    break
            if not mapping.get("selected_option_label"):
                _, lbl, score, _ = best_option_match(str(mapping["selected_option"]), mapping.get("options", []))
                if lbl and score >= 0.80:
                    mapping["selected_option_label"] = lbl
                else:
                    mapping["selected_option_label"] = mapping["selected_option"]
    return mapping

# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------

def map_profile_to_fields(profile: dict, fields: List[dict],
                           form_url: str = "", resume_file_path: Optional[str] = None) -> List[dict]:
    """
    Unified mapping pipeline:
    1. Scan stats logging
    2. Extract candidate values for each field
    3. Rank local options for option fields
    4. Pass all fields to Gemini
    5. Post-process
    """
    from services.gemini_service import get_gemini_client

    cache_key = _cache_key(form_url, profile)
    if cache_key in _mapping_cache:
        logger.info(f"Cache hit for form_url='{form_url}' (key={cache_key}). Returning cached mapping.")
        return _mapping_cache[cache_key]

    final_mappings: Dict[str, dict] = {}
    gemini_payload = []
    
    # ── STEP 1: Scan Statistics Logging ──
    total_logical = len(fields)
    plain_fields_count = 0
    option_fields_count = 0
    for f in fields:
        if f.get("type", "text") in ("select", "combobox", "radio", "radio_group", "checkbox_group", "multiselect"):
            option_fields_count += 1
        else:
            plain_fields_count += 1
            
    logger.info(f"[Form Mapper Stats] Total logical fields: {total_logical}")
    logger.info(f"  Plain fields: {plain_fields_count}")
    logger.info(f"  Option fields: {option_fields_count}")

    # ── STEP 2 & 3: Pre-processing & Ranking ──
    for field in fields:
        fid = field.get("field_id", "")
        ftype = field.get("type", "text")
        label = field.get("label", "")
        
        # Determine candidate values
        if is_eeo_field(label, field.get("nearby_text", "")) or "submit" in ftype.lower():
            candidate_vals = ["[SKIP]"]
        else:
            candidate_vals = get_candidate_profile_values(field, profile)
            if not candidate_vals:
                candidate_vals = []
                
        # Handle options
        is_option_field = ftype in ("select", "combobox", "radio", "radio_group", "checkbox_group", "multiselect")
        opts = field.get("options") or []
        
        if is_option_field:
            orig_count = len(opts)
            if candidate_vals == ["[SKIP]"]:
                ranked_opts = []
            else:
                ranked_opts = rank_local_options(candidate_vals, opts, ftype, label)
            logger.info(f"  Field '{label or fid}' - original options: {orig_count}, top ranked: {len(ranked_opts)}, candidates: {candidate_vals}")
            
            gemini_payload.append({
                "field_id": fid,
                "label": label,
                "type": ftype,
                "required": field.get("required", False),
                "options": ranked_opts,
                "candidate_profile_values": candidate_vals
            })
        else:
            logger.info(f"  Field '{label or fid}' (Plain) - candidates: {candidate_vals}")
            gemini_payload.append({
                "field_id": fid,
                "label": label,
                "type": ftype,
                "required": field.get("required", False),
                "options": [],
                "candidate_profile_values": candidate_vals
            })

    # ── STEP 4: Gemini Form Mapper ──
    client = get_gemini_client()
    if not client:
        logger.warning("No Gemini client available. Falling back to empty plan.")
        for field in fields:
            fid = field.get("field_id", "")
            final_mappings[fid] = _make_mapping(
                field, None, None, 0.0, "rule",
                "No Gemini client available", action="skip", status="needs_review"
            )
    else:
        logger.info(f"[Gemini Mapper] Payload items: {len(gemini_payload)}")
        try:
            gemini_results = query_gemini_form_mapper(client, profile, gemini_payload)
            logger.info(f"[Gemini Mapper] Response items: {len(gemini_results)}")
            
            fields_lookup = {f["field_id"]: f for f in fields}
            for gr in gemini_results:
                fid = gr.get("field_id") if isinstance(gr, dict) else getattr(gr, "field_id", None)
                if not fid or fid not in fields_lookup:
                    continue
                orig = fields_lookup[fid]
                m = convert_gemini_item_to_mapping(orig, gr)
                final_mappings[fid] = m
                
        except Exception as e:
            logger.error(f"Gemini Form Mapper failed: {e}")
            for field in fields:
                fid = field.get("field_id", "")
                final_mappings[fid] = _make_mapping(
                    field, None, None, 0.0, "error",
                    f"Gemini mapper failed: {e}",
                    action="skip", status="needs_review"
                )

    # ── STEP 5: Merge & Post-Process Checks ──
    ordered = []
    for field in fields:
        fid = field.get("field_id", "")
        m = final_mappings.get(fid)
        if not m:
            is_req = field.get("required", False)
            m = _make_mapping(
                field, None, None, 0.0, "rule",
                "Gemini skipped or missed this field",
                action="skip", status="needs_review" if is_req else "skipped"
            )
            
        if "selected_option_labels" not in m:
            m["selected_option_labels"] = []
        if m.get("selected_option_label") and not m.get("selected_option_labels"):
            m["selected_option_labels"] = [m["selected_option_label"]]

        ordered.append(_enrich_mapping_from_field(m, field))
        
    logger.info(f"[Rule Mapping Stats] Final mapping plan count: {len(ordered)}")
    
    if form_url:
        _mapping_cache[cache_key] = ordered
    return ordered

