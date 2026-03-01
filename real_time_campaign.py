import os
import asyncio
from dotenv import load_dotenv
from sqlmodel import Session, select
from app.core.db import engine, init_db
from app.models.setting import Setting
from app.models.identity import IdentityProfile, KnowledgeBase, get_srvdb_instance
from app.utils.prompt import build_email_prompt
from app.utils.llm_client import generate_email
from app.utils.company import wrap_email_template
from app.core.vault import VaultManager

# Ensure DB forms and PBKDF2 vault derivations are pre-heated
init_db()

async def true_real_time_e2e():
    """Execute the full real pipeline utilizing exact Vault encryption
    and actual LLM invocation—zero mocking, zero .env files."""
    
    with Session(engine) as session:
        # 1. Fetch Key from Vault Securely
        print("1. Fetching API Key strictly from SQLite Vault...")
        setting = session.exec(select(Setting).where(Setting.key == "groq_key")).first()
        if not setting or not setting.value:
            print("❌ No groq_key found in the SQLite database. Please add it via the UI Settings Panel first.")
            return
            
        unlocked_groq = setting.get_decrypted_value()
        print(f"   Success: Groq Vault Decryption Valid. Length: {len(unlocked_groq)}")
        
        # Identity Profile Setup
        print("2. Writing 'Zenith Logistics' Identity & SrvDB Pillars to Database...")
        identity = session.exec(select(IdentityProfile)).first()
        if not identity:
            identity = IdentityProfile()
            session.add(identity)
        
        identity.name = "Zenith Logistics"
        identity.tagline = "Next-Generation Supply Chain & Fleet Management"
        identity.sender_name = "Marcus Vance"
        identity.sender_title = "VP of Global Supply Chain"
        identity.calendly_url = "https://calendly.com/zenith-logistics-demo"
        
        # Clear old knowledge base for fresh run
        kbs = session.exec(select(KnowledgeBase)).all()
        for kb in kbs:
            session.delete(kb)
            
        session.flush()

        # Add genuine Service Pillars
        p1 = KnowledgeBase(identity_id=identity.id, title="AI Route Optimization", value_prop="We reduce fleet fuel consumption by 15% using predictive machine learning routing.")
        p2 = KnowledgeBase(identity_id=identity.id, title="Cold-Chain Tracking", value_prop="Real-time IoT temperature monitoring ensuring 0% spoilage on cross-country transit.")
        p3 = KnowledgeBase(identity_id=identity.id, title="Automated Customs Brokerage", value_prop="Our APIs clear international freight 3 days faster than traditional manual paperwork.")
        session.add_all([p1, p2, p3])
        session.commit()
    
    # Reload from DB specifically to prove Pipeline operates off the Data Layer
    with Session(engine) as session:
        active_identity = session.exec(select(IdentityProfile)).first()
        active_kbs = session.exec(select(KnowledgeBase)).all()
    
    lead = {
        "first_name": "Sarah",
        "company": "Oceanic Imports",
        "role": "Director of Operations",
        "industry": "Retail Imports",
        "location": "West Coast Ports"
    }

    print("3. Executing Real-Time Prompt Construction...")
    sys_p, usr_p = build_email_prompt(lead, active_identity, active_kbs)
    print("   [SYSTEM PROMPT BUILT SUCCESS]\n")
    
    print("4. Invoking Groq LLM (Real Network Call)...")
    try:
        pkg = await generate_email(
            system_prompt=sys_p,
            user_prompt=usr_p,
            groq_key=unlocked_groq,
            preferred_provider="groq"
        )
        print("   ✅ Valid LLM response received!")
        print(f"   Subject: {pkg.get('subject')}\n")
        
        # Wrap the LLM HTML to inject the sender profile
        final_html = wrap_email_template(
            inner_html=pkg.get("bodyHtml", ""),
            sender_email="marcus@zenithlogistics.com",
            sender_name=active_identity.sender_name,
            sender_title=active_identity.sender_title,
            company_name=active_identity.name,
            company_tagline=active_identity.tagline,
            company_logo="https://via.placeholder.com/150", # Dummy logo
            company_website="https://zenithlogistics.mock"
        )
        
        print("5. HTML Export complete. Sending to output file: final_real_email.html")
        with open("final_real_email.html", "w") as f:
            f.write(final_html)
            
        print("\nPipeline execution sequence completed successfully.")
        
    except Exception as e:
        print(f"❌ Real-time run failed: {str(e)}")


if __name__ == "__main__":
    asyncio.run(true_real_time_e2e())
