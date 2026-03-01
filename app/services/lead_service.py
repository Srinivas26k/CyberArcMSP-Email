import csv
import io
from typing import Dict, Any
from sqlmodel import Session
from app.repositories.lead_repository import lead_repository
from app.models.lead import Lead

class LeadService:
    @staticmethod
    def add_imported_leads(session: Session, leads_data: list[Dict[str, Any]]) -> dict:
        existing_leads = lead_repository.get_all(session)
        existing_emails = {lead.email.lower() for lead in existing_leads}
        added = 0
        skipped = 0

        for norm in leads_data:
            email = norm.get("email", "").strip().lower()
            if not email or email in existing_emails:
                skipped += 1
                continue

            lead_in = Lead(
                email=email,
                first_name=norm.get("first_name", ""),
                last_name=norm.get("last_name", ""),
                company=norm.get("company", ""),
                role=norm.get("role", ""),
                industry=norm.get("industry", "Technology"),
                location=norm.get("location", ""),
                seniority=norm.get("seniority", ""),
                employees=norm.get("employees", ""),
                website=norm.get("website", ""),
                linkedin=norm.get("linkedin", "")
            )
            lead_repository.create(session, lead_in)
            existing_emails.add(email)
            added += 1

        return {
            "added":   added,
            "skipped": skipped,
            "found":   len(leads_data),
            "total":   len(lead_repository.get_all(session)),
            "leads":   leads_data,          # full objects for the results panel
        }

    @staticmethod
    def process_csv_upload(session: Session, content: bytes) -> dict:
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        
        ALIAS = {
            "first name": "first_name",  "firstname": "first_name",
            "last name":  "last_name",   "lastname":  "last_name",
            "job title":  "role",        "title":     "role",
            "num employees": "employees","# employees": "employees",
        }
        
        if not reader.fieldnames:
            from fastapi import HTTPException
            raise HTTPException(422, "CSV file is completely empty or invalid.")

        normalized_fields = [ALIAS.get(str(f).strip().lower(), str(f).strip().lower().replace(" ", "_")) for f in reader.fieldnames]
        if "email" not in normalized_fields:
            from fastapi import HTTPException
            raise HTTPException(422, "Malformed CSV: 'email' column is required.")
        
        processed_data = []
        for row in reader:
            norm = {}
            for k, v in row.items():
                if k is None:
                    continue
                k_low = k.strip().lower()
                norm[ALIAS.get(k_low, k_low.replace(" ", "_"))] = (v or "").strip()
            processed_data.append(norm)

        return LeadService.add_imported_leads(session, processed_data)

lead_service = LeadService()
