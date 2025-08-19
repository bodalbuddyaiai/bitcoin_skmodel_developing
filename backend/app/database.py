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

# DB 초기화 함수 수정
def init_db():
    # 여기서 모델 import
    from app.models.trading_history import TradingHistory
    
    # 기존 테이블 삭제 (옵션)
    Base.metadata.drop_all(bind=engine)
    
    # 테이블 새로 생성
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully")

# 이 파일이 직접 실행될 때만 init_db() 실행
if __name__ == "__main__":
    init_db() 