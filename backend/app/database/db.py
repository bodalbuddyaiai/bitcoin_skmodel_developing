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
    from app.models.trading_settings import TradingSettings
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully")
    
    # 기본 설정 값 초기화
    db = SessionLocal()
    try:
        # 기본 설정 생성 (이미 존재하면 건너뛰기)
        default_settings = [
            {"setting_name": "stop_loss_reanalysis_minutes", "setting_value": 5, "description": "손절 후 재분석 시간 (분)"},
            {"setting_name": "normal_reanalysis_minutes", "setting_value": 60, "description": "일반 청산 후 재분석 시간 (분)"},
            {"setting_name": "monitoring_interval_minutes", "setting_value": 90, "description": "포지션 모니터링 주기 (분)"},
        ]
        
        for setting in default_settings:
            existing = db.query(TradingSettings).filter_by(setting_name=setting["setting_name"]).first()
            if not existing:
                new_setting = TradingSettings(**setting)
                db.add(new_setting)
        
        db.commit()
        print("Default settings initialized successfully")
    except Exception as e:
        print(f"Error initializing default settings: {e}")
        db.rollback()
    finally:
        db.close() 