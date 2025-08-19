from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from datetime import datetime
from app.database.db import Base  # 여기서 Base import

class TradingHistory(Base):
    __tablename__ = "trading_history"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.now)
    action = Column(String)  # ENTER_LONG, ENTER_SHORT, CLOSE_POSITION, HOLD
    leverage = Column(Float)
    position_size = Column(Float)
    expected_minutes = Column(Integer)
    reason = Column(String)
    market_data = Column(JSON)  # 분석 시점의 시장 데이터
    execution_result = Column(JSON, nullable=True)  # 실제 거래 실행 결과 