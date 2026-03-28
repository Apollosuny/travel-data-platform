from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from travel_data_platform.config import settings

engine = create_engine(
  settings.database_url,
  echo=False,
  pool_pre_ping=True,
)

SessionLocal = sessionmaker(
  bind=engine,
  autoflush=False,
  autocommit=False,
)