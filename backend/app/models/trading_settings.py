from sqlalchemy import Column, Integer, String, DateTime
from app.database.db import Base
import datetime

class TradingSettings(Base):
    """트레이딩 설정 테이블"""
    __tablename__ = "trading_settings"

    id = Column(Integer, primary_key=True, index=True)
    setting_name = Column(String, unique=True, index=True, nullable=False)  # 설정 이름
    setting_value = Column(Integer, nullable=False)  # 설정 값 (분 단위)
    description = Column(String)  # 설정 설명
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

