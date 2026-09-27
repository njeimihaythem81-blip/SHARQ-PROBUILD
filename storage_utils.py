"""
Storage layer -- uses the app's own GitHub repository as the file store,
via the GitHub Contents API. This avoids Google Cloud Console entirely
(no service account, no project, no Google 2-Step Verification wall).

Repo layout:
  data/
    index.json                 <- lightweight list of all panels
    <panel_id>/
      metadata.json
      parts.xlsx
      diagram.pdf

Auth: a GitHub Personal Access Token with "repo" access, created from
github.com/settings/tokens (plain GitHub website, no Google Console
involved), stored under st.secrets["github_token"].
"""
import base64
import json
import uuid
from datetime import datetime

import requests
import streamlit as st

API_ROOT = "https://api.github.com"
INDEX_PATH = "data/index.json"


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


def _load_index() -> dict:
    idx = _get_json(INDEX_PATH)
    return idx if idx else {"panels": []}


def create_panel(panel_name, install_date, warranty_months, excel_file, pdf_file) -> str:
    panel_id = uuid.uuid4().hex[:8].upper()
    base = f"data/{panel_id}"

    excel_bytes = excel_file.read()
    pdf_bytes = pdf_file.read()

    excel_path = f"{base}/parts.xlsx"
    pdf_path = f"{base}/diagram.pdf"

    _put_file(excel_path, excel_bytes, f"SHARQ: add parts list for panel {panel_id}")
    _put_file(pdf_path, pdf_bytes, f"SHARQ: add diagram for panel {panel_id}")

    metadata = {
        "panel_id": panel_id,
        "panel_name": panel_name,
        "install_date": install_date,
        "warranty_months": warranty_months,
        "excel_path": excel_path,
        "pdf_path": pdf_path,
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


def list_panels() -> list:
    return _load_index()["panels"]


def get_excel_rows(excel_path: str) -> list:
    from modules import excel_utils
    raw = get_file_bytes(excel_path)
    return excel_utils.parse_rows(raw)


def get_pdf_context(pdf_path: str) -> str:
    from modules import pdf_utils
    raw = get_file_bytes(pdf_path)
    return pdf_utils.extract_text(raw)
