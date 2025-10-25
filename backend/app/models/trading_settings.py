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

class DiagonalSettings(Base):
    """빗각 분석 포인트 설정 테이블"""
    __tablename__ = "diagonal_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 빗각 타입 선택 (uptrend 또는 downtrend 중 하나만)
    diagonal_type = Column(String, nullable=True)  # 'uptrend' 또는 'downtrend'
    
    # 포인트 시간 설정 (YYYY-MM-DD HH:MM 형식)
    point_a_time = Column(String, nullable=True)  # Point A (역사적 저점 또는 고점) 시간
    point_second_time = Column(String, nullable=True)  # 두 번째 저점 또는 고점 시간
    point_b_time = Column(String, nullable=True)  # 변곡점 시간
    
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

