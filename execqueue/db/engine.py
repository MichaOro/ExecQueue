from sqlmodel import create_engine
from execqueue.runtime import get_opencode_base_url

DATABASE_URL = (
    "postgresql+psycopg://neondb_owner:npg_EoJ1iySBWNX6@ep-wispy-sea-alz3z46t-pooler.c-3.eu-central-1.aws.neon.tech/neondb?channel_binding=require&sslmode=require"
)

engine = create_engine(DATABASE_URL, echo=False)
