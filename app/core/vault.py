import os
import base64
import secrets
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class VaultManager:
    """
    Application-layer AES-256 encryption utility.
    Ensures sensitive fields (API Keys, Passwords) are encrypted at rest in the SQLite database
    without requiring complex OS-level SQLCipher C-bindings.
    """
    _cipher = None

    @classmethod
    def _initialize(cls):
        if cls._cipher is not None:
            return

        app_data_dir = os.environ.get("APP_DATA_DIR", "").strip()
        if not app_data_dir:
            app_data_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Salt path
        salt_path = os.path.join(app_data_dir, ".vault_salt")
        if os.path.exists(salt_path):
            with open(salt_path, "rb") as f:
                salt = f.read()
        else:
            salt = os.urandom(16)
            os.makedirs(app_data_dir, exist_ok=True)
            with open(salt_path, "wb") as f:
                f.write(salt)
            try:
                os.chmod(salt_path, 0o600)
            except OSError:
                pass

        # Hardware/OS Key (Mocked here to standard file for now, ideally derived from Machine GUID)
        key_path = os.path.join(app_data_dir, ".vault_key")
        if os.path.exists(key_path):
            with open(key_path, "rb") as f:
                master_pass = f.read()
        else:
            master_pass = secrets.token_bytes(32)
            with open(key_path, "wb") as f:
                f.write(master_pass)
            try:
                os.chmod(key_path, 0o600)
            except OSError:
                pass

        # Derive AES key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_pass))
        cls._cipher = Fernet(key)

    @classmethod
    def encrypt(cls, plaintext: str) -> str:
        if not plaintext:
            return plaintext
        cls._initialize()
        return cls._cipher.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    @classmethod
    def decrypt(cls, ciphertext: str) -> str:
        if not ciphertext:
            return ciphertext
        cls._initialize()
        try:
            return cls._cipher.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except Exception:
            # Fallback if the database contained unencrypted legacy strings
            return ciphertext
