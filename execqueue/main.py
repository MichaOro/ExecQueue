from fastapi import FastAPI

from execqueue.db.engine import create_db_and_tables
from execqueue.api.requirements import router as requirements_router
from execqueue.api.work_packages import router as work_packages_router
from execqueue.api.tasks import router as tasks_router
from execqueue.api.queue import router as queue_router
from execqueue.api.runner import router as runner_router

app = FastAPI()


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


@app.get("/")
def root():
    return {"status": "ExecQueue running"}


app.include_router(requirements_router)
app.include_router(work_packages_router)
app.include_router(tasks_router)
app.include_router(queue_router)
app.include_router(runner_router)