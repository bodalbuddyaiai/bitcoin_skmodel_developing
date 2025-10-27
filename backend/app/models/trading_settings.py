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
    """빗각 분석 포인트 설정 테이블 - 상승/하락 빗각 동시 활용"""
    __tablename__ = "diagonal_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 상승 빗각 (저점 연결) 설정
    uptrend_point_a_time = Column(String, nullable=True)  # Point A (역사적 저점) 시간
    uptrend_point_second_time = Column(String, nullable=True)  # 두 번째 저점 시간
    uptrend_point_b_time = Column(String, nullable=True)  # 변곡점 시간
    
    # 하락 빗각 (고점 연결) 설정
    downtrend_point_a_time = Column(String, nullable=True)  # Point A (역사적 고점) 시간
    downtrend_point_second_time = Column(String, nullable=True)  # 두 번째 고점 시간
    downtrend_point_b_time = Column(String, nullable=True)  # 변곡점 시간
    
    # 레거시 필드 (하위 호환성 유지 - 사용 안 함)
    diagonal_type = Column(String, nullable=True)  # deprecated
    point_a_time = Column(String, nullable=True)  # deprecated
    point_second_time = Column(String, nullable=True)  # deprecated
    point_b_time = Column(String, nullable=True)  # deprecated
    
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

