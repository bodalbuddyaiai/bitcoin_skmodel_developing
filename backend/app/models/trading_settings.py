from sqlalchemy import Column, Integer, String, DateTime, Boolean
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

class EmailSettings(Base):
    """이메일 설정 테이블"""
    __tablename__ = "email_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    email_address = Column(String, nullable=True)  # 수신자 이메일 주소
    send_main_analysis = Column(Boolean, default=True)  # 본분석 이메일 발송 여부
    send_monitoring_analysis = Column(Boolean, default=True)  # 모니터링분석 이메일 발송 여부
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

