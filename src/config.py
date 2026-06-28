"""Configuration for SiftStack — full-stack REI operations platform."""

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
LOG_DIR = PROJECT_ROOT / "logs"
STATE_FILE = PROJECT_ROOT / "last_run.json"
SEEN_IDS_FILE = PROJECT_ROOT / "seen_ids.json"
SEEN_IDS_PRUNE_DAYS = 90
# Notices that exhausted all CAPTCHA retries during scraping.
# Persisted so the next run's summary can surface them instead of
# silently dropping — and a future retry pass can prioritize them.
CAPTCHA_FAILED_IDS_FILE = PROJECT_ROOT / "captcha_failed_ids.json"
CAPTCHA_FAILED_PRUNE_DAYS = 14
COOKIES_FILE = PROJECT_ROOT / "cookies.json"
DROPBOX_STATE_FILE = PROJECT_ROOT / "dropbox_state.json"
PHOTO_STATE_FILE = PROJECT_ROOT / "photo_state.json"

# ── Dropbox Watcher ────────────────────────────────────────────────────
DROPBOX_POLL_INTERVAL = int(os.getenv("DROPBOX_POLL_INTERVAL", "900"))  # seconds (default 15 min)
DROPBOX_ROOT_FOLDER = os.getenv("DROPBOX_ROOT_FOLDER", "")  # root folder path in Dropbox, e.g. "/TN Public Notice"
DROPBOX_STORAGE_WARN_PERCENT = 80  # warn when storage usage exceeds this %

OUTPUT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# ── Credentials ────────────────────────────────────────────────────────
TNPN_EMAIL = os.getenv("TNPN_EMAIL", "")
TNPN_PASSWORD = os.getenv("TNPN_PASSWORD", "")
CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY", "")  # 2Captcha API key
CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY", "")  # CapSolver API key (AWS WAF for NC eCourts)
ECOURTS_EMAIL = os.getenv("ECOURTS_EMAIL", "")          # NC eCourts portal login (required for case detail / parties)
ECOURTS_PASSWORD = os.getenv("ECOURTS_PASSWORD", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")  # Claude Haiku for LLM parsing
SMARTY_AUTH_ID = os.getenv("SMARTY_AUTH_ID", "")        # Smarty address standardization
SMARTY_AUTH_TOKEN = os.getenv("SMARTY_AUTH_TOKEN", "")
OPENWEBNINJA_API_KEY = os.getenv("OPENWEBNINJA_API_KEY", "")  # Zillow property enrichment
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")              # Serper.dev Google Search API
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")        # Firecrawl JS-rendered scraping
TRACERFY_API_KEY = os.getenv("TRACERFY_API_KEY", "")          # Tracerfy skip tracing
TRESTLE_API_KEY = os.getenv("TRESTLE_API_KEY", "")            # Trestle phone validation
DATASIFT_EMAIL = os.getenv("DATASIFT_EMAIL", "")              # DataSift.ai login
DATASIFT_PASSWORD = os.getenv("DATASIFT_PASSWORD", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")        # Slack/Discord webhook
ANCESTRY_EMAIL = os.getenv("ANCESTRY_EMAIL", "")              # Ancestry.com login
ANCESTRY_PASSWORD = os.getenv("ANCESTRY_PASSWORD", "")
DROPBOX_APP_KEY = os.getenv("DROPBOX_APP_KEY", "")            # Dropbox OAuth2 app key
DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET", "")
DROPBOX_REFRESH_TOKEN = os.getenv("DROPBOX_REFRESH_TOKEN", "")

# ── LLM Backend ──────────────────────────────────────────────────────
LLM_BACKEND = os.getenv("LLM_BACKEND", "anthropic")           # "anthropic", "ollama", or "openrouter"
LLM_MODEL = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")  # Anthropic model name (default for all LLM calls)
# High-stakes obituary identity + heir/survivor extraction uses a stronger model.
# Getting the heir/decision-maker chain right is critical: a wrong heir map sends
# the whole deal down the wrong path, so this defaults to Sonnet rather than Haiku.
OBITUARY_LLM_MODEL = os.getenv("OBITUARY_LLM_MODEL", "claude-sonnet-4-6")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")        # Local Ollama model
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1/")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")       # OpenRouter API key
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "qwen/qwen-2.5-72b-instruct")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# ── Site URLs ──────────────────────────────────────────────────────────
BASE_URL = "https://www.tnpublicnotice.com"
LOGIN_URL = f"{BASE_URL}/authenticate.aspx"
SMART_SEARCH_URL = f"{BASE_URL}/Smartsearch/Default.aspx"

# ── NC Site (ncnotices.com — NC Press Association, ASP.NET, no login, no CAPTCHA) ──
NC_BASE_URL = "https://www.ncnotices.com"
NC_SEARCH_URL = f"{NC_BASE_URL}/Search.aspx"
NC_STATE_FILE = PROJECT_ROOT / "nc_last_run.json"
NC_SEEN_IDS_FILE = PROJECT_ROOT / "nc_seen_ids.json"

# ── NC Selectors (ncnotices.com — same vendor as TN, shares ctl00$...$as1$ namespace) ──
NC_SEL_CATEGORY = "#ctl00_ContentPlaceHolder1_as1_ddlPopularSearches"
NC_SEL_KEYWORD = "#ctl00_ContentPlaceHolder1_as1_txtSearch"
NC_SEL_EXCLUDE = "#ctl00_ContentPlaceHolder1_as1_txtExclude"
NC_SEL_MATCH_ALL = "#ctl00_ContentPlaceHolder1_as1_rdoType_0"
NC_SEL_MATCH_ANY = "#ctl00_ContentPlaceHolder1_as1_rdoType_1"
NC_SEL_MATCH_EXACT = "#ctl00_ContentPlaceHolder1_as1_rdoType_2"
NC_SEL_DATE_LAST_DAYS_RADIO = "#ctl00_ContentPlaceHolder1_as1_rbLastNumDays"
NC_SEL_DATE_LAST_DAYS_INPUT = "#ctl00_ContentPlaceHolder1_as1_txtLastNumDays"
NC_SEL_SUBMIT = "#ctl00_ContentPlaceHolder1_as1_btnGo"
NC_SEL_RESET = "#ctl00_ContentPlaceHolder1_as1_btnReset1"
NC_SEL_PER_PAGE = "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1_ctl01_ddlPerPage"
NC_SEL_VIEW_BUTTON_PATTERN = "input.viewButton[name$='btnView2']"
NC_SEL_NEXT_PAGE = "input[name$='btnNext'][title='Next page']"
NC_SEL_CURRENT_PAGE = "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1_ctl01_lblCurrentPage"
NC_SEL_TOTAL_PAGES = "#ctl00_ContentPlaceHolder1_WSExtendedGridNP1_GridView1_ctl01_lblTotalPages"

# NC counties currently in scope (subset of 100 NC counties on the site)
NC_TARGET_COUNTIES = [
    "Cabarrus", "Catawba", "Gaston", "Iredell", "Lincoln", "Mecklenburg", "Rowan",
]

# ── ASP.NET Selectors ─────────────────────────────────────────────────
# Login form
SEL_LOGIN_EMAIL = "#ctl00_ContentPlaceHolder1_AuthenticateIPA1_txtEmailAddress"
SEL_LOGIN_PASSWORD = "#ctl00_ContentPlaceHolder1_AuthenticateIPA1_txtPassword"
SEL_LOGIN_SUBMIT = "#ctl00_ContentPlaceHolder1_AuthenticateIPA1_btnAuth"

# Smart Search dashboard
SEL_SAVED_SEARCHES_DROPDOWN = "#ctl00_ContentPlaceHolder1_as1_ddlSavedSearches"
SEL_PER_PAGE_DROPDOWN = 'select[name$="ddlPerPage"]'

# Search results (authenticated grid)
SEL_RESULTS_GRID = "#ctl00_ContentPlaceHolder1_WSExtendedGrid1_GridView1"
SEL_VIEW_BUTTON_PATTERN = "input[name$='btnView']"
SEL_NEXT_PAGE_BUTTON = "input[title='Next page']"
SEL_PAGE_INFO = "td:has-text('Page ')"

# Notice detail page
SEL_CAPTCHA_IFRAME = "iframe[src*='recaptcha']"
SEL_VIEW_NOTICE_BUTTON = "#ctl00_ContentPlaceHolder1_PublicNoticeDetailsBody1_btnViewNotice"
RECAPTCHA_SITEKEY = "6LdtSg8sAAAAADTdRyZxJ2R2sS82pKALNMvMqSyL"

# ── Rate Limiting ──────────────────────────────────────────────────────
REQUEST_DELAY_MIN = 2.0  # seconds between requests
REQUEST_DELAY_MAX = 3.0
MAX_RETRIES = 3
RESULTS_PER_PAGE = 50  # max the site allows

# ── Image Processing ───────────────────────────────────────────────────
BLUR_THRESHOLD = int(os.getenv("BLUR_THRESHOLD", "100"))   # Laplacian variance; below = rejected as blurry
TESSERACT_PSM_PDF = 3    # fully automatic — best for PDF tax sale tables
TESSERACT_PSM_PHOTO = 4  # assume single column of variable-size text — best for terminal screen photos

# ── Notice Types ───────────────────────────────────────────────────────
NOTICE_TYPES = ["foreclosure", "probate"]


@dataclass
class SavedSearch:
    """Represents a saved search on tnpublicnotice.com."""
    county: str
    notice_type: str  # One of NOTICE_TYPES
    saved_search_name: str  # Exact name in the Saved Searches dropdown


# ── Saved Searches ─────────────────────────────────────────────────────
# These names must match exactly what appears in the dropdown on the site.
SAVED_SEARCHES: list[SavedSearch] = [
    SavedSearch("Knox", "foreclosure", "Foreclosure V2 Knox"),
    SavedSearch("Blount", "foreclosure", "Foreclosure V2 Blount"),
]


@dataclass
class NCSavedSearch:
    """A search definition for ncnotices.com.

    The site has no saved-search dropdown — each search is built up on the
    form: optional category dropdown, optional keyword, and a county checkbox.
    One NCSavedSearch = one (county, notice_type) combination.
    """
    county: str            # Single NC county name (matches checkbox label)
    notice_type: str       # foreclosure | probate | tax_sale | tax_delinquent
    category: str | None   # "Foreclosure" or None
    keyword: str | None    # e.g. "notice to creditors", or None
    match_type: str = "EXACT"  # ALL / ANY / EXACT (only used when keyword is set)


# 7 counties × 3 search variants = 21 NC searches.
# tax_sale and tax_delinquent overlap heavily on this site (both surface "tax
# foreclosure" notices) — we keep just one "tax_sale" search per county to
# avoid duplicate hits; classification can refine later.
NC_SAVED_SEARCHES: list[NCSavedSearch] = (
    [NCSavedSearch(c, "foreclosure", "Foreclosure", None) for c in NC_TARGET_COUNTIES]
    + [NCSavedSearch(c, "probate", None, "notice to creditors", "EXACT") for c in NC_TARGET_COUNTIES]
    + [NCSavedSearch(c, "tax_sale", None, "tax foreclosure", "EXACT") for c in NC_TARGET_COUNTIES]
)

# ── Entity Detection ──────────────────────────────────────────────────
# Business entity patterns — shared across obituary_enricher, tax_enricher,
# and enrichment_pipeline for entity filtering.
BUSINESS_RE = re.compile(
    r"\b(?:LLC|L\.L\.C|INC|CORP|CORPORATION|COMPANY|CO\b|LTD|LP|L\.P|"
    r"PARTNERSHIP|ASSOCIATION|ASSOC|BANK|CREDIT UNION|CHURCH|MINISTRIES|"
    r"HOUSING|AUTHORITY|DEVELOPMENT|ENTERPRISES|PROPERTIES|INVESTMENTS|"
    r"GROUP|HOLDINGS|MANAGEMENT|SERVICES|FOUNDATION|ORGANIZATION)\b",
    re.IGNORECASE,
)

# Trust/estate patterns — personal trusts are NOT business entities
TRUST_NAME_RE = re.compile(
    r"^(?:THE\s+)?([\w]+(?:\s+[\w.]+)+?)\s+(?:REVOCABLE\s+)?(?:LIVING\s+)?TRUST\b",
    re.IGNORECASE,
)
ESTATE_OF_RE = re.compile(
    r"^(?:THE\s+)?ESTATE\s+OF\s+([\w]+(?:\s+[\w.]+)+?)(?:\s*,|\s*$)",
    re.IGNORECASE,
)

_config_logger = logging.getLogger(__name__)


# ── State File Utilities ─────────────────────────────────────────────


def save_state(path: Path, data: dict) -> None:
    """Write JSON state to disk atomically (write tmp → rename).

    Creates a .bak copy of the previous file before overwriting.
    """
    # Back up current file
    if path.exists():
        try:
            bak = path.with_suffix(path.suffix + ".bak")
            bak.write_bytes(path.read_bytes())
        except OSError:
            pass  # Best-effort backup

    # Atomic write: tmp → rename
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_state(path: Path) -> dict:
    """Load JSON state from disk, falling back to .bak if corrupt."""
    for candidate in [path, path.with_suffix(path.suffix + ".bak")]:
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                _config_logger.warning("Failed to read %s: %s", candidate, e)
    return {}
