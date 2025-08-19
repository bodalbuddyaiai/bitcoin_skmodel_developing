from fastapi import APIRouter, Body
from ..services.trading_assistant import TradingAssistant
from pydantic import BaseModel

# 라우터 생성 시 prefix와 tags 추가
router = APIRouter(
    prefix="/trading",  # 선택사항: 라우터 레벨에서 prefix 추가
    tags=["trading"]    # Swagger UI에서 그룹화
)

class TradeAction(BaseModel):
    action: str

@router.post("/analyze")
async def analyze_market():
    """시장 분석 및 거래 실행"""
    try:
        trading_assistant = TradingAssistant()
        result = await trading_assistant.analyze_and_execute()
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/test-trade")  # 실제 경로는 /api/trading/test-trade가 됨
async def test_trade(trade_action: TradeAction):
    """테스트용 거래 실행"""
    try:
        trading_assistant = TradingAssistant()
        result = await trading_assistant.test_trade(trade_action.action)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}
