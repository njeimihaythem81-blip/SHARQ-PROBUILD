"""
Storage layer -- uses the app's own GitHub repository as the file store,
via the GitHub Contents API. This avoids Google Cloud Console entirely
(no service account, no project, no Google 2-Step Verification wall).

Repo layout:
  data/
    index.json                 <- lightweight list of all panels
    employees.json              <- employee names, codes, permissions, contributions
    login_log.json               <- login/download log (auto-purged after 60 days)
    <panel_id>/
      metadata.json
      parts.xlsx
      diagram.<pdf|jpg|jpeg|png>

Auth: a GitHub Personal Access Token with "repo" access, created from
github.com/settings/tokens (plain GitHub website, no Google Console
involved), stored under st.secrets["github_token"].
"""
import base64
import json
import uuid
from datetime import datetime, timedelta

import requests
import streamlit as st

API_ROOT = "https://api.github.com"
INDEX_PATH = "data/index.json"
EMPLOYEES_PATH = "data/employees.json"
LOGIN_LOG_PATH = "data/login_log.json"
LOG_RETENTION_DAYS = 60


def _repo() -> str:
    return st.secrets["github_repo"]  # e.g. "your-username/sharq-app"


def _branch() -> str:
    return st.secrets.get("github_branch", "main")


def _headers(raw: bool = False) -> dict:
    return {
        "Authorization": f"token {st.secrets['github_token']}",
        "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
    }


def _contents_url(path: str) -> str:
    return f"{API_ROOT}/repos/{_repo()}/contents/{path}"


def _get_sha_if_exists(path: str):
    r = requests.get(_contents_url(path), headers=_headers(), params={"ref": _branch()}, timeout=30)
    if r.status_code == 200:
        return r.json().get("sha")
    return None


def _put_file(path: str, data: bytes, message: str):
    body = {
        "message": message,
        "content": base64.b64encode(data).decode("utf-8"),
        "branch": _branch(),
    }
    sha = _get_sha_if_exists(path)
    if sha:
        body["sha"] = sha
    r = requests.put(_contents_url(path), headers=_headers(), json=body, timeout=60)
    r.raise_for_status()
    return r.json()


def _delete_file(path: str, message: str):
    sha = _get_sha_if_exists(path)
    if not sha:
        return
    body = {"message": message, "sha": sha, "branch": _branch()}
    r = requests.delete(_contents_url(path), headers=_headers(), json=body, timeout=30)
    r.raise_for_status()
    get_file_bytes.clear()


@st.cache_data(ttl=300, show_spinner=False)
def get_file_bytes(path: str) -> bytes:
    r = requests.get(_contents_url(path), headers=_headers(raw=True), params={"ref": _branch()}, timeout=60)
    r.raise_for_status()
    return r.content


def _get_json(path: str):
    try:
        raw = get_file_bytes(path)
    except requests.HTTPError:
        return None
    return json.loads(raw.decode("utf-8"))


def _save_json(path: str, data: dict, message: str):
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    _put_file(path, payload, message)
    get_file_bytes.clear()


# ============================================================
#                          PANELS
# ============================================================

def _load_index() -> dict:
    idx = _get_json(INDEX_PATH)
    return idx if idx else {"panels": []}


def create_panel(panel_name, install_date, warranty_months, excel_file, diagram_file) -> str:
    """diagram_file can be a PDF or an image (jpg/jpeg/png) -- stored as-is, no conversion."""
    panel_id = uuid.uuid4().hex[:8].upper()
    base = f"data/{panel_id}"

    excel_bytes = excel_file.read()
    diagram_bytes = diagram_file.read()

    diagram_ext = diagram_file.name.rsplit(".", 1)[-1].lower()
    diagram_type = "image" if diagram_ext in ("jpg", "jpeg", "png") else "pdf"
    diagram_mime = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "pdf": "application/pdf",
    }.get(diagram_ext, "application/octet-stream")

    excel_path = f"{base}/parts.xlsx"
    diagram_path = f"{base}/diagram.{diagram_ext}"

    _put_file(excel_path, excel_bytes, f"SHARQ: add parts list for panel {panel_id}")
    _put_file(diagram_path, diagram_bytes, f"SHARQ: add diagram for panel {panel_id}")

    metadata = {
        "panel_id": panel_id,
        "panel_name": panel_name,
        "install_date": install_date,
        "warranty_months": warranty_months,
        "excel_path": excel_path,
        "diagram_path": diagram_path,
        "diagram_type": diagram_type,
        "diagram_mime": diagram_mime,
        "verified": False,
        "notes_admin": "",
        "notes_public": "",
        "created_at": datetime.now().isoformat(),
    }
    _save_json(f"{base}/metadata.json", metadata, f"SHARQ: add metadata for panel {panel_id}")

    index_data = _load_index()
    index_data["panels"].append(
        {"panel_id": panel_id, "panel_name": panel_name,
         "install_date": install_date, "warranty_months": warranty_months}
    )
    _save_json(INDEX_PATH, index_data, f"SHARQ: index panel {panel_id}")

    get_file_bytes.clear()
    return panel_id


@st.cache_data(ttl=120, show_spinner=False)
def load_panel_metadata(panel_id: str):
    return _get_json(f"data/{panel_id}/metadata.json")


def update_panel_meta(panel_id: str, **fields):
    """Admin-only in the UI: update verified / notes_admin / notes_public / etc."""
    meta = load_panel_metadata(panel_id)
    if not meta:
        return
    meta.update(fields)
    _save_json(f"data/{panel_id}/metadata.json", meta, f"SHARQ: update panel {panel_id}")
    load_panel_metadata.clear()


def delete_panel(panel_id: str):
    """Admin-only in the UI."""
    meta = load_panel_metadata(panel_id)
    if meta:
        for p in (meta.get("excel_path"), meta.get("diagram_path"), f"data/{panel_id}/metadata.json"):
            if p:
                _delete_file(p, f"SHARQ: delete panel {panel_id}")
    index_data = _load_index()
    index_data["panels"] = [p for p in index_data["panels"] if p["panel_id"] != panel_id]
    _save_json(INDEX_PATH, index_data, f"SHARQ: remove panel {panel_id} from index")
    load_panel_metadata.clear()


def list_panels() -> list:
    return _load_index()["panels"]


def get_excel_rows(excel_path: str) -> list:
    from modules import excel_utils
    raw = get_file_bytes(excel_path)
    return excel_utils.parse_rows(raw)


# ============================================================
#                         EMPLOYEES
# ============================================================

def _load_employees() -> dict:
    data = _get_json(EMPLOYEES_PATH)
    return data if data else {"employees": []}


def list_employees() -> list:
    return _load_employees()["employees"]


def find_employee(name: str, code: str):
    name = (name or "").strip().lower()
    code = (code or "").strip()
    for e in list_employees():
        if e["name"].strip().lower() == name and str(e["code"]).strip() == code:
            return e
    return None


def save_employee(name: str, code: str, can_upload: bool, allowed_downloads: list):
    """Admin-only in the UI. Adds a new employee, or updates one with the same name."""
    data = _load_employees()
    existing = next((e for e in data["employees"] if e["name"].strip().lower() == name.strip().lower()), None)
    if existing:
        existing.update({"code": code, "can_upload": can_upload, "allowed_downloads": allowed_downloads})
    else:
        data["employees"].append({
            "name": name, "code": code, "can_upload": can_upload,
            "allowed_downloads": allowed_downloads, "contributions": 0,
        })
    _save_json(EMPLOYEES_PATH, data, f"SHARQ: save employee {name}")


def delete_employee(name: str):
    """Admin-only in the UI."""
    data = _load_employees()
    data["employees"] = [e for e in data["employees"] if e["name"] != name]
    _save_json(EMPLOYEES_PATH, data, f"SHARQ: delete employee {name}")


def increment_contribution(name: str):
    data = _load_employees()
    for e in data["employees"]:
        if e["name"] == name:
            e["contributions"] = e.get("contributions", 0) + 1
    _save_json(EMPLOYEES_PATH, data, f"SHARQ: +1 contribution for {name}")


# ============================================================
#                        LOGIN / ACTIVITY LOG
# ============================================================

def _purge_old(entries: list) -> list:
    cutoff = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
    kept = []
    for e in entries:
        try:
            if datetime.fromisoformat(e["timestamp"]) > cutoff:
                kept.append(e)
        except Exception:
            continue
    return kept


def record_log(employee_name: str, panel_id: str, action: str, detail: str = ""):
    data = _get_json(LOGIN_LOG_PATH) or {"entries": []}
    data["entries"] = _purge_old(data["entries"])
    data["entries"].append({
        "timestamp": datetime.now().isoformat(),
        "employee": employee_name,
        "panel_id": panel_id,
        "action": action,
        "detail": detail,
    })
    _save_json(LOGIN_LOG_PATH, data, f"SHARQ: log {action} by {employee_name}")


def get_login_log() -> list:
    data = _get_json(LOGIN_LOG_PATH) or {"entries": []}
    entries = _purge_old(data["entries"])
    return sorted(entries, key=lambda e: e["timestamp"], reverse=True)


# ============================================================
#                    COMPANY LOGO (optional)
# ============================================================
LOGO_META_PATH = "data/logo_meta.json"


def save_logo(file_obj):
    """Admin-only in the UI. Stores the logo as-is (no conversion) and remembers its path/mime."""
    ext = file_obj.name.rsplit(".", 1)[-1].lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "image/png")
    path = f"data/logo.{ext}"
    _put_file(path, file_obj.read(), "SHARQ: update company logo")
    _save_json(LOGO_META_PATH, {"path": path, "mime": mime}, "SHARQ: update logo metadata")


def get_logo_bytes():
    """Returns (bytes, mime) or (None, None) if no logo was uploaded yet."""
    meta = _get_json(LOGO_META_PATH)
    if not meta:
        return None, None
    try:
        return get_file_bytes(meta["path"]), meta["mime"]
    except requests.HTTPError:
        return None, None


# ============================================================
#                    FULL DATA EXPORT (backup)
# ============================================================
def export_all_data() -> dict:
    """Admin-only in the UI. A single JSON snapshot of panels index, employees,
    and the current login log -- for the person's own backup/archiving."""
    return {
        "exported_at": datetime.now().isoformat(),
        "panels_index": _load_index(),
        "employees": _load_employees(),
        "login_log": get_login_log(),
    }
