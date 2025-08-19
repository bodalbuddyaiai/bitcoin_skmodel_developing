from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from ..database import Base
import datetime

class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    action = Column(String)  # 'buy', 'sell', 'hold'
    price = Column(Float)
    amount = Column(Float)
    leverage = Column(Integer)
    position_type = Column(String)  # 'long', 'short'
    ai_reasoning = Column(JSON)
    status = Column(String) 