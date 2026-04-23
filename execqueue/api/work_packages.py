from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from execqueue.db.session import get_session
from execqueue.models.work_package import WorkPackage
from execqueue.runtime import is_test_mode

router = APIRouter()


@router.get("/")
def list_work_packages(session: Session = Depends(get_session)):
    wps = session.exec(
        select(WorkPackage).where(WorkPackage.is_test == is_test_mode())
    ).all()
    return [
        {
            "id": w.id,
            "title": w.title,
            "requirement_id": w.requirement_id,
            "status": w.status,
        }
        for w in wps
    ]


@router.post("/")
def create_work_package(wp: WorkPackage, session: Session = Depends(get_session)):
    wp.is_test = is_test_mode()
    session.add(wp)
    session.commit()
    session.refresh(wp)
    return wp
