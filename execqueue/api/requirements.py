from fastapi import APIRouter, Depends, status
from sqlmodel import Session, select

from execqueue.db.engine import get_session
from execqueue.models import Requirement
from execqueue.runtime import is_test_mode

router = APIRouter(prefix="/requirements", tags=["requirements"])


@router.get("/")
def get_requirements(session: Session = Depends(get_session)):
    statement = select(Requirement).where(Requirement.is_test == is_test_mode())
    return session.exec(statement).all()


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_requirement(req: Requirement, session: Session = Depends(get_session)):
    req.is_test = is_test_mode()
    session.add(req)
    session.commit()
    session.refresh(req)
    return req
