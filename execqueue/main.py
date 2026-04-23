from fastapi import FastAPI
from fastapi.routing import APIRouter
from dotenv import load_dotenv

# Lade .env Datei beim Start
load_dotenv()

from execqueue.api.dead_letter import router as dead_letter_router
from execqueue.api.tasks import router as tasks_router
from execqueue.api.queue import router as queue_router
from execqueue.api.requirements import router as requirements_router
from execqueue.api.work_packages import router as work_packages_router
from execqueue.api.health import router as health_router
from execqueue.api.metrics import router as metrics_router
from execqueue.scheduler.runner import run_next_task
from execqueue.db.engine import engine
from sqlmodel import SQLModel


app = FastAPI(title="ExecQueue API")


@app.on_event("startup")
def on_startup():
    """Create all database tables on startup."""
    SQLModel.metadata.create_all(engine)


# Mount routers
app.include_router(tasks_router, prefix="/api/tasks", tags=["tasks"])
app.include_router(queue_router, prefix="/api/queue", tags=["queue"])
app.include_router(requirements_router, prefix="/api/requirements", tags=["requirements"])
app.include_router(work_packages_router, prefix="/api/work-packages", tags=["work-packages"])
app.include_router(dead_letter_router, prefix="/api", tags=["dead-letter"])
app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(metrics_router, prefix="/api", tags=["metrics"])


@app.get("/api/runner/run-next")
def run_next():
    """Run the next task in the queue."""
    from execqueue.db.session import get_session
    
    with get_session() as session:
        task = run_next_task(session)
        if task:
            return {
                "task_id": task.id,
                "status": task.status,
                "retry_count": task.retry_count,
            }
        return {"message": "No tasks in queue"}
