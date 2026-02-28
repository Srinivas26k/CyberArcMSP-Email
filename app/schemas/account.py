from pydantic import BaseModel

class AccountIn(BaseModel):
    email:        str
    app_password: str
    provider:     str = "outlook"   # "gmail" | "outlook" | "m365" | "resend"
    display_name: str = ""
