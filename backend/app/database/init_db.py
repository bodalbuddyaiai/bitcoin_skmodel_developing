from sqlalchemy import create_engine
from app.models.trading_history import Base
from app.config.settings import DATABASE_URL
# 테이블 생성을 위해 모든 모델 import
from app.models.trading_settings import DiagonalSettings, EmailSettings, TradingSettings

def init_db():
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
    print("Database tables created successfully!") 