from fastapi import APIRouter, Depends, status
from sqlmodel import Session, select

from execqueue.db.engine import get_session
from execqueue.models import Requirement

router = APIRouter(prefix="/requirements", tags=["requirements"])


@router.get("/")
def get_requirements(session: Session = Depends(get_session)):
    return session.exec(select(Requirement)).all()


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_requirement(req: Requirement, session: Session = Depends(get_session)):
    session.add(req)
    session.commit()
    session.refresh(req)
    return req
