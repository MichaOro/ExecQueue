from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from execqueue.db.session import get_session
from execqueue.models.requirement import Requirement
from execqueue.runtime import is_test_mode

router = APIRouter()


@router.get("/")
def list_requirements(session: Session = Depends(get_session)):
    requirements = session.exec(
        select(Requirement).where(Requirement.is_test == is_test_mode())
    ).all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "description": r.description,
            "status": r.status,
        }
        for r in requirements
    ]


@router.post("/")
def create_requirement(req: Requirement, session: Session = Depends(get_session)):
    req.is_test = is_test_mode()
    session.add(req)
    session.commit()
    session.refresh(req)
    return req
