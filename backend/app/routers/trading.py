from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session
from ..services.trading_assistant import TradingAssistant
from ..models.trading_settings import TradingSettings
from ..database.db import get_db
from pydantic import BaseModel
from typing import List, Optional

# 라우터 생성 시 prefix와 tags 추가
router = APIRouter(
    prefix="/trading",  # 선택사항: 라우터 레벨에서 prefix 추가
    tags=["trading"]    # Swagger UI에서 그룹화
)

class TradeAction(BaseModel):
    action: str

class SettingUpdate(BaseModel):
    setting_name: str
    setting_value: int
    
class SettingResponse(BaseModel):
    id: int
    setting_name: str
    setting_value: int
    description: Optional[str]
    
    class Config:
        from_attributes = True

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

@router.get("/settings", response_model=List[SettingResponse])
async def get_settings(db: Session = Depends(get_db)):
    """트레이딩 설정 조회"""
    try:
        settings = db.query(TradingSettings).all()
        return settings
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.put("/settings")
async def update_setting(setting_update: SettingUpdate, db: Session = Depends(get_db)):
    """트레이딩 설정 수정"""
    try:
        setting = db.query(TradingSettings).filter_by(setting_name=setting_update.setting_name).first()
        
        if not setting:
            return {"success": False, "error": "설정을 찾을 수 없습니다"}
        
        setting.setting_value = setting_update.setting_value
        db.commit()
        db.refresh(setting)
        
        # TradingAssistant에 설정 업데이트 반영
        trading_assistant = TradingAssistant()
        trading_assistant.update_settings(setting_update.setting_name, setting_update.setting_value)
        
        return {
            "success": True,
            "message": "설정이 업데이트되었습니다",
            "setting": {
                "id": setting.id,
                "setting_name": setting.setting_name,
                "setting_value": setting.setting_value,
                "description": setting.description
            }
        }
    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
