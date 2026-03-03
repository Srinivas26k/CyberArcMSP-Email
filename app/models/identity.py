import os
import json
from sqlmodel import SQLModel, Field
from typing import Optional, Dict, Any, List

# srvdb is a Rust-compiled extension — not available on Windows yet.
# All call-sites already have try/except, so we degrade gracefully.
try:
    import srvdb as _srvdb_mod
    SRVDB_AVAILABLE = True
except ImportError:
    _srvdb_mod = None          # type: ignore[assignment]
    SRVDB_AVAILABLE = False

class IdentityProfile(SQLModel, table=True):
    """
    Replaces the hardcoded `COMPANY_PROFILE` in company.py.
    Stores the white-labeled identity of the user running the software.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    mode: str = Field(default="b2b") # "b2b", "personal", "agency"
    
    # Core Identity
    name: str = Field(default="")
    tagline: str = Field(default="")
    website: str = Field(default="")
    
    # Branding
    primary_color: str = Field(default="#1A56DB")
    logo_url: str = Field(default="")
    
    # Personalization Fallbacks
    calendly_url: str = Field(default="")
    sender_name: str = Field(default="")
    sender_title: str = Field(default="")
    
    # JSON String representation of dictionary lists (e.g. offices)
    offices_json: str = Field(default="[]")

    @property
    def offices(self) -> List[Dict[str, Any]]:
        try:
            return json.loads(self.offices_json)
        except json.JSONDecodeError:
            return []
    
    @offices.setter
    def offices(self, val: List[Dict[str, Any]]):
        self.offices_json = json.dumps(val)


class KnowledgeBase(SQLModel, table=True):
    """
    Replaces the hardcoded `SERVICE_PORTFOLIO`.
    Stores services, case studies, or personal projects.
    These get embedded into SrvDB for semantic retrieval.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    identity_id: int = Field(default=1, foreign_key="identityprofile.id")
    
    title: str = Field(default="")
    description: str = Field(default="")
    value_prop: str = Field(default="")
    case_study: str = Field(default="")
    
    # Determines if this entry has been synced to the SrvDB vector store yet
    is_embedded: bool = Field(default=False)


# ==========================================
# SrvDB Integration Layer
# ==========================================

def get_srvdb_instance():
    """
    Initializes a local SrvDB instance in the AppData directory.
    Returns None (with a warning) if the srvdb Rust extension is unavailable
    (e.g. on Windows before a native binary is compiled).
    """
    if not SRVDB_AVAILABLE:
        import logging
        logging.getLogger(__name__).warning(
            "srvdb not available on this platform — vector DB features disabled."
        )
        return None

    app_data_dir = os.environ.get("APP_DATA_DIR", "").strip()
    if not app_data_dir:
        app_data_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    srvdb_path = os.path.join(app_data_dir, "data", "srvdb_store")
    os.makedirs(srvdb_path, exist_ok=True)

    # Initialize SrvDB (dimension 384 → all-MiniLM-L6-v2 compatible)
    db = _srvdb_mod.SrvDBPython(srvdb_path, dimension=384)
    return db
