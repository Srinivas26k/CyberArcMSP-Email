"""
sequences.py — Follow-up sequence API controller.

Endpoints:
  GET    /api/sequences/                        list all sequence templates
  POST   /api/sequences/                        create a new sequence template
  GET    /api/sequences/{id}                    get sequence details
  PUT    /api/sequences/{id}                    update a sequence template
  DELETE /api/sequences/{id}                    delete a sequence template

  GET    /api/sequences/enrollments             list enrollments (filter by lead/status)
  POST   /api/sequences/{id}/enroll             enroll leads in a sequence
  POST   /api/sequences/enrollments/{id}/stop   stop a specific enrollment

A sequence template step looks like:
  {
    "delay_days": 3,
    "subject_hint": "Re:",
    "instructions": "Short 2-line follow-up. Mention their reply wasn't received yet."
  }
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.dependencies import get_db_session
from app.models.sequence import SequenceEnrollment, SequenceTemplate

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# SEQUENCE TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────

def _tpl_dict(t: SequenceTemplate) -> dict:
    return {
        "id":          t.id,
        "name":        t.name,
        "description": t.description,
        "steps":       json.loads(t.steps_json or "[]"),
        "is_active":   t.is_active,
        "created_at":  t.created_at,
    }


@router.get("/")
def list_sequences(session: Session = Depends(get_db_session)):
    templates = session.exec(select(SequenceTemplate)).all()
    result = []
    for t in templates:
        d = _tpl_dict(t)
        # Count active enrollments
        active = session.exec(
            select(SequenceEnrollment).where(
                SequenceEnrollment.sequence_id == t.id,
                SequenceEnrollment.status == "active",
            )
        ).all()
        d["active_enrollments"] = len(active)
        result.append(d)
    return {"sequences": result}


@router.post("/", status_code=201)
def create_sequence(body: dict, session: Session = Depends(get_db_session)):
    steps = body.get("steps", [])
    tpl = SequenceTemplate(
        name=body.get("name", "New Sequence"),
        description=body.get("description", ""),
        steps_json=json.dumps(steps),
        is_active=body.get("is_active", True),
    )
    session.add(tpl)
    session.commit()
    session.refresh(tpl)
    return {"sequence": _tpl_dict(tpl)}


@router.get("/{seq_id}")
def get_sequence(seq_id: int, session: Session = Depends(get_db_session)):
    tpl = session.get(SequenceTemplate, seq_id)
    if not tpl:
        raise HTTPException(404, "Sequence not found")
    return {"sequence": _tpl_dict(tpl)}


@router.put("/{seq_id}")
def update_sequence(seq_id: int, body: dict, session: Session = Depends(get_db_session)):
    tpl = session.get(SequenceTemplate, seq_id)
    if not tpl:
        raise HTTPException(404, "Sequence not found")
    if "name"        in body:
        tpl.name        = body["name"]
    if "description" in body:
        tpl.description = body["description"]
    if "steps"       in body:
        tpl.steps_json  = json.dumps(body["steps"])
    if "is_active"   in body:
        tpl.is_active   = body["is_active"]
    session.add(tpl)
    session.commit()
    session.refresh(tpl)
    return {"sequence": _tpl_dict(tpl)}


@router.delete("/{seq_id}", status_code=204)
def delete_sequence(seq_id: int, session: Session = Depends(get_db_session)):
    tpl = session.get(SequenceTemplate, seq_id)
    if not tpl:
        raise HTTPException(404, "Sequence not found")
    # Stop all active enrollments first
    enrollments = session.exec(
        select(SequenceEnrollment).where(SequenceEnrollment.sequence_id == seq_id)
    ).all()
    for e in enrollments:
        e.status = "stopped"
        session.add(e)
    session.delete(tpl)
    session.commit()


# ─────────────────────────────────────────────────────────────────────────────
# ENROLLMENTS
# ─────────────────────────────────────────────────────────────────────────────

def _enroll_dict(e: SequenceEnrollment) -> dict:
    return {
        "id":              e.id,
        "lead_id":         e.lead_id,
        "sequence_id":     e.sequence_id,
        "current_step":    e.current_step,
        "status":          e.status,
        "enrolled_at":     e.enrolled_at,
        "next_send_at":    e.next_send_at,
        "last_sent_at":    e.last_sent_at,
        "initial_subject": e.initial_subject,
    }


@router.get("/enrollments/all")
def list_enrollments(
    lead_id: Optional[int] = None,
    status: Optional[str] = None,
    session: Session = Depends(get_db_session),
):
    q = select(SequenceEnrollment)
    if lead_id is not None:
        q = q.where(SequenceEnrollment.lead_id == lead_id)
    if status:
        q = q.where(SequenceEnrollment.status == status)
    enrollments = session.exec(q).all()
    return {"enrollments": [_enroll_dict(e) for e in enrollments]}


@router.post("/{seq_id}/enroll", status_code=201)
def enroll_leads(seq_id: int, body: dict, session: Session = Depends(get_db_session)):
    """
    Enroll one or more leads in a sequence.

    Body: {
      "lead_ids": [1, 2, 3],
      "initial_subject": "...",   # optional — subject of initial email sent
      "delay_first_step": true    # if true, wait delay_days before step 0 too
    }
    """
    tpl = session.get(SequenceTemplate, seq_id)
    if not tpl:
        raise HTTPException(404, "Sequence not found")

    steps = json.loads(tpl.steps_json or "[]")
    if not steps:
        raise HTTPException(400, "Sequence has no steps defined")

    lead_ids        = body.get("lead_ids", [])
    initial_subject = body.get("initial_subject", "")
    delay_first     = body.get("delay_first_step", True)

    enrolled = 0
    for lead_id in lead_ids:
        # Skip if already enrolled and active
        existing = session.exec(
            select(SequenceEnrollment).where(
                SequenceEnrollment.lead_id == lead_id,
                SequenceEnrollment.sequence_id == seq_id,
                SequenceEnrollment.status == "active",
            )
        ).first()
        if existing:
            continue

        step0 = steps[0]
        if delay_first:
            delay = step0.get("delay_days", 3)
            next_dt = datetime.now(timezone.utc) + timedelta(days=delay)
        else:
            next_dt = datetime.now(timezone.utc)  # send immediately

        e = SequenceEnrollment(
            lead_id=lead_id,
            sequence_id=seq_id,
            current_step=0,
            status="active",
            next_send_at=next_dt.isoformat(),
            initial_subject=initial_subject,
        )
        session.add(e)
        enrolled += 1

    session.commit()
    return {"enrolled": enrolled, "sequence_id": seq_id}


@router.post("/enrollments/{enroll_id}/stop")
def stop_enrollment(enroll_id: int, session: Session = Depends(get_db_session)):
    e = session.get(SequenceEnrollment, enroll_id)
    if not e:
        raise HTTPException(404, "Enrollment not found")
    e.status = "stopped"
    session.add(e)
    session.commit()
    return {"status": "stopped"}
