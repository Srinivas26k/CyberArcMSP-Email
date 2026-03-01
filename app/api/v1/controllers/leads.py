from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlmodel import Session
from app.api.dependencies import get_db_session
from app.models.lead import Lead
from app.schemas.lead import LeadIn, ApolloQuery
from app.services.lead_service import lead_service
from app.utils.apollo_search import apollo_search as _apollo_search
from app.core.config import settings
from app.repositories.lead_repository import lead_repository

router = APIRouter()

def _lead_to_dict(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "email": lead.email,
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "company": lead.company,
        "role": lead.role,
        "industry": lead.industry,
        "status": lead.status,
        "created_at": lead.created_at
    }

@router.get("/")
def list_leads(session: Session = Depends(get_db_session)):
    leads = lead_repository.get_all(session)
    # Simple mapping without join for now
    res = [_lead_to_dict(lead) for lead in leads]
    return {"leads": res, "total": len(leads)}

@router.post("/", status_code=201)
def add_lead(body: LeadIn, session: Session = Depends(get_db_session)):
    existing = lead_repository.get_by_email(session, body.email)
    if existing:
        raise HTTPException(400, f"Lead {body.email} already exists")
        
    lead = Lead(**body.model_dump())
    lead = lead_repository.create(session, lead)
    return {"lead": _lead_to_dict(lead)}

@router.post("/csv")
async def upload_csv(file: UploadFile = File(...), session: Session = Depends(get_db_session)):
    content = await file.read()
    return lead_service.process_csv_upload(session, content)

@router.delete("/{lead_id}")
def delete_lead(lead_id: int, session: Session = Depends(get_db_session)):
    lead = lead_repository.get(session, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    lead_repository.remove(session, lead_id)
    return {"status": "deleted"}

@router.delete("/")
def delete_all_leads(session: Session = Depends(get_db_session)):
    leads = lead_repository.get_all(session)
    for lead in leads:
        lead_repository.remove(session, lead.id)
    return {"deleted": len(leads)}

@router.post("/apollo/search")
async def search_apollo(q: ApolloQuery, session: Session = Depends(get_db_session)):
    key = settings.apollo_api_key
    if not key:
        raise HTTPException(400, "Apollo API key not configured. Set it in Settings.")

    try:
        results = await _apollo_search(
            api_key=key,
            titles=q.titles,
            industry=q.industry,
            locations=q.locations,
            company_sizes=q.company_sizes,
            target_count=q.target_count,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))

    return lead_service.add_imported_leads(session, results)
