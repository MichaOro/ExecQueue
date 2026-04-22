from fastapi import APIRouter, Depends, status
from sqlmodel import Session, select

from execqueue.db.engine import get_session
from execqueue.models.work_package import WorkPackage
from execqueue.runtime import is_test_mode

router = APIRouter(prefix="/work-packages", tags=["work-packages"])


@router.get("/")
def get_work_packages(session: Session = Depends(get_session)):
    statement = select(WorkPackage).where(WorkPackage.is_test == is_test_mode())
    return session.exec(statement).all()


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_work_package(wp: WorkPackage, session: Session = Depends(get_session)):
    wp.is_test = is_test_mode()
    session.add(wp)
    session.commit()
    session.refresh(wp)
    return wp
