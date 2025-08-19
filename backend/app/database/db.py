from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config.settings import DATABASE_URL

SQLALCHEMY_DATABASE_URL = DATABASE_URL

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    # 기존 테이블 삭제 (옵션)
    Base.metadata.drop_all(bind=engine)
    
    # 모델 import 및 테이블 생성
    from app.models.trading_history import TradingHistory
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully") 