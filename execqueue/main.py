from fastapi import FastAPI

from execqueue.db.engine import create_db_and_tables
from execqueue.api.requirements import router as requirements_router
from execqueue.api.work_packages import router as work_packages_router

app = FastAPI()


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


@app.get("/")
def root():
    return {"status": "ExecQueue running"}


app.include_router(requirements_router)
app.include_router(work_packages_router)