from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session
from ..services.trading_assistant import TradingAssistant
from ..models.trading_settings import TradingSettings, EmailSettings, DiagonalSettings
from ..database.db import get_db
from pydantic import BaseModel, EmailStr
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

class EmailSettingUpdate(BaseModel):
    email_address: Optional[str] = None
    send_main_analysis: Optional[bool] = None
    send_monitoring_analysis: Optional[bool] = None

class EmailSettingResponse(BaseModel):
    id: int
    email_address: Optional[str]
    send_main_analysis: bool
    send_monitoring_analysis: bool
    
    class Config:
        from_attributes = True

class DiagonalSettingUpdate(BaseModel):
    # 상승 빗각
    uptrend_point_a_time: Optional[str] = None
    uptrend_point_second_time: Optional[str] = None
    uptrend_point_b_time: Optional[str] = None
    # 하락 빗각
    downtrend_point_a_time: Optional[str] = None
    downtrend_point_second_time: Optional[str] = None
    downtrend_point_b_time: Optional[str] = None

class DiagonalSettingResponse(BaseModel):
    id: int
    # 상승 빗각
    uptrend_point_a_time: Optional[str]
    uptrend_point_second_time: Optional[str]
    uptrend_point_b_time: Optional[str]
    # 하락 빗각
    downtrend_point_a_time: Optional[str]
    downtrend_point_second_time: Optional[str]
    downtrend_point_b_time: Optional[str]
    
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

@router.get("/email-settings", response_model=EmailSettingResponse)
async def get_email_settings(db: Session = Depends(get_db)):
    """이메일 설정 조회"""
    try:
        email_setting = db.query(EmailSettings).first()
        
        # 설정이 없으면 기본값으로 생성
        if not email_setting:
            email_setting = EmailSettings(
                email_address=None,
                send_main_analysis=True,
                send_monitoring_analysis=True
            )
            db.add(email_setting)
            db.commit()
            db.refresh(email_setting)
        
        return email_setting
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.put("/email-settings")
async def update_email_settings(setting_update: EmailSettingUpdate, db: Session = Depends(get_db)):
    """이메일 설정 수정"""
    try:
        email_setting = db.query(EmailSettings).first()
        
        # 설정이 없으면 생성
        if not email_setting:
            email_setting = EmailSettings()
            db.add(email_setting)
        
        # 업데이트할 필드만 변경
        if setting_update.email_address is not None:
            email_setting.email_address = setting_update.email_address
        if setting_update.send_main_analysis is not None:
            email_setting.send_main_analysis = setting_update.send_main_analysis
        if setting_update.send_monitoring_analysis is not None:
            email_setting.send_monitoring_analysis = setting_update.send_monitoring_analysis
        
        db.commit()
        db.refresh(email_setting)
        
        return {
            "success": True,
            "message": "이메일 설정이 업데이트되었습니다",
            "setting": {
                "id": email_setting.id,
                "email_address": email_setting.email_address,
                "send_main_analysis": email_setting.send_main_analysis,
                "send_monitoring_analysis": email_setting.send_monitoring_analysis
            }
        }
    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}

@router.get("/diagonal-settings", response_model=DiagonalSettingResponse)
async def get_diagonal_settings(db: Session = Depends(get_db)):
    """빗각 분석 포인트 설정 조회"""
    try:
        diagonal_setting = db.query(DiagonalSettings).first()
        
        # 설정이 없으면 기본값으로 생성
        if not diagonal_setting:
            diagonal_setting = DiagonalSettings(
                diagonal_type=None
            )
            db.add(diagonal_setting)
            db.commit()
            db.refresh(diagonal_setting)
        
        return diagonal_setting
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.put("/diagonal-settings")
async def update_diagonal_settings(setting_update: DiagonalSettingUpdate, db: Session = Depends(get_db)):
    """빗각 분석 포인트 설정 수정 - 상승/하락 빗각 모두"""
    try:
        diagonal_setting = db.query(DiagonalSettings).first()
        
        # 설정이 없으면 생성
        if not diagonal_setting:
            diagonal_setting = DiagonalSettings()
            db.add(diagonal_setting)
        
        # 상승 빗각 필드 업데이트
        if setting_update.uptrend_point_a_time is not None:
            diagonal_setting.uptrend_point_a_time = setting_update.uptrend_point_a_time
        if setting_update.uptrend_point_second_time is not None:
            diagonal_setting.uptrend_point_second_time = setting_update.uptrend_point_second_time
        if setting_update.uptrend_point_b_time is not None:
            diagonal_setting.uptrend_point_b_time = setting_update.uptrend_point_b_time
        
        # 하락 빗각 필드 업데이트
        if setting_update.downtrend_point_a_time is not None:
            diagonal_setting.downtrend_point_a_time = setting_update.downtrend_point_a_time
        if setting_update.downtrend_point_second_time is not None:
            diagonal_setting.downtrend_point_second_time = setting_update.downtrend_point_second_time
        if setting_update.downtrend_point_b_time is not None:
            diagonal_setting.downtrend_point_b_time = setting_update.downtrend_point_b_time
        
        db.commit()
        db.refresh(diagonal_setting)
        
        return {
            "success": True,
            "message": "빗각 설정이 업데이트되었습니다",
            "setting": {
                "id": diagonal_setting.id,
                # 상승 빗각
                "uptrend_point_a_time": diagonal_setting.uptrend_point_a_time,
                "uptrend_point_second_time": diagonal_setting.uptrend_point_second_time,
                "uptrend_point_b_time": diagonal_setting.uptrend_point_b_time,
                # 하락 빗각
                "downtrend_point_a_time": diagonal_setting.downtrend_point_a_time,
                "downtrend_point_second_time": diagonal_setting.downtrend_point_second_time,
                "downtrend_point_b_time": diagonal_setting.downtrend_point_b_time
            }
        }
    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
