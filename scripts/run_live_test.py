import os
import sys
import asyncio
import httpx
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

TARGET_EMAIL = "srinivasvarma764@gmail.com"

# Read credentials set by the User in `.env`
TEST_IMAP_EMAIL = os.getenv("GMAIL_EMAIL")
TEST_IMAP_PASSWORD = os.getenv("GMAIL_PASS")

async def run_live_pipeline():
    print("🚀 Starting End-to-End Live Email Pipeline Test...")
    
    if not TEST_IMAP_EMAIL or not TEST_IMAP_PASSWORD:
        print("❌ CRITICAL: TEST_IMAP_EMAIL or TEST_IMAP_PASSWORD not found in .env!")
        sys.exit(1)
        
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8002", timeout=60.0) as client:
        # 1. Healthcheck
        print("\n[1/5] Checking Server Health...")
        try:
            r = await client.get("/api/health")
            if r.status_code != 200:
                print(f"❌ Server not available on port 8002. Response: {r.text}")
                sys.exit(1)
            print(f"✅ Server Health: OK (v{r.json().get('version')})")
        except Exception as e:
            print(f"❌ Server not reachable: {e}. Please ensure it is running.")
            sys.exit(1)

        # 2. Reset Database (Leads & Accounts)
        print("\n[2/5] Cleaning old database testing state...")
        # Stop any stuck campaigns
        await client.post("/api/campaigns/stop")
        
        # Get accounts
        accs = await client.get("/api/accounts/")
        for acc in accs.json().get("accounts", []):
            await client.delete(f"/api/accounts/{acc['id']}")
            
        await client.delete("/api/leads/")
        print("✅ Database cleared.")

        # 3. Add Account & Test Connection
        print(f"\n[3/5] Injecting test account: {TEST_IMAP_EMAIL}")
        acc_payload = {
            "email": TEST_IMAP_EMAIL,
            "app_password": TEST_IMAP_PASSWORD,
            "provider": "gmail" if "gmail" in TEST_IMAP_EMAIL else "m365",
            "display_name": "Srinivas Outreach"
        }
        r = await client.post("/api/accounts/", json=acc_payload)
        if r.status_code != 201:
            print(f"❌ Failed to add account: {r.text}")
            sys.exit(1)
            
        acc_id = r.json()["id"]
        
        print("⏳ Testing SMTP/IMAP credentials with remote server...")
        r = await client.post(f"/api/accounts/{acc_id}/test")
        res = r.json()
        if not res.get("ok"):
            print(f"❌ Account Connection Failed: {res.get('error')}")
            sys.exit(1)
        print("✅ Account Connection Validated successfully!")

        # 4. Add Lead
        print(f"\n[4/5] Adding Target Lead: {TARGET_EMAIL}")
        lead_payload = {
            "email": TARGET_EMAIL,
            "first_name": "Srinivas",
            "last_name": "Varma",
            "company": "Tech Innovations Ltd",
            "industry": "Software Engineering"
        }
        r = await client.post("/api/leads/", json=lead_payload)
        if r.status_code != 201:
            print(f"❌ Failed to add lead: {r.text}")
            sys.exit(1)
        print("✅ Lead Injected.")

        # 5. Execute Campaign
        print("\n[5/5] Launching AI Campaign Pipeline...")
        camp_payload = {
            "strategy": "round_robin",
            "batch_size": 1,
            "delay_seconds": 1
        }
        r = await client.post("/api/campaigns/start", json=camp_payload)
        if r.status_code != 200:
            print(f"❌ Failed to start campaign: {r.text}")
            sys.exit(1)
            
        print("✅ Campaign executing in background...")
        
        # 6. Monitor Status via Polling
        print("\n⏳ Polling Lead Status (waiting for LLM & SMTP) ...")
        for i in range(20): # Max wait 60s
            await asyncio.sleep(3)
            r = await client.get("/api/leads/")
            leads = r.json().get("leads", [])
            if not leads:
                continue
            
            lead = list(filter(lambda x: x["email"] == TARGET_EMAIL, leads))[0]
            status = lead.get("status")
            print(f"   [{i}] Status loop: {status.upper()}")
            
            if status == "sent":
                print("\n🎉 SUCCESS: The AI Pipeline generated and dispatched the email successfully!")
                sys.exit(0)
            elif status == "failed":
                # Print explicit reason if possible
                print("\n❌ FAILED: Campaign errored out during LLM generation or SMTP.")
                # Could fetch campaign export
                sys.exit(1)

        print("\n⚠️ TIMEOUT: Pipeline took too long to resolve.")

if __name__ == "__main__":
    asyncio.run(run_live_pipeline())
