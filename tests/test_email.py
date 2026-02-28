import asyncio
import sys
import os
from dotenv import load_dotenv

# Ensure the app module can be found when running from tests/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.utils.email_engine import EmailEngine

load_dotenv()

async def test_email_flow():
    accounts = settings.get_o365_accounts()
    if not accounts:
        print("❌ No O365 accounts configured in .env")
        return
        
    print(f"✅ Found {len(accounts)} accounts. Testing first one: {accounts[0]['email']}")
    
    # Initialize EmailEngine with the first account as active
    engine = EmailEngine([
        {
            "id": 1,
            "email": accounts[0]["email"],
            "app_password": accounts[0]["password"], # Note config maps it to password
            "provider": "outlook",
            "display_name": accounts[0]["name"]
        }
    ])
    
    # 1. Test Connection
    print("\n--- Testing Connection ---")
    connection_result = await engine.test_account(accounts[0]["email"])
    if connection_result.get("ok"):
        print("✅ SMTP and IMAP connection successful!")
    else:
        print(f"❌ Connection failed: {connection_result.get('error')}")
        return
        
    # Skip actual email sending in automated CI unless desired
    print("\n--- Test complete ---")

if __name__ == "__main__":
    asyncio.run(test_email_flow())
