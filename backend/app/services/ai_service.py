from .openai_service import OpenAIService
from .claude_service import ClaudeService

class AIService:
    def __init__(self):
        self.openai_service = OpenAIService()
        self.claude_service = ClaudeService()
        self.current_model = "gpt"  # 기본값은 GPT
    
    def set_model(self, model_type):
        """AI 모델 설정
        Args:
            model_type (str): 모델 타입 ('openai', 'claude', 'claude-opus')
        """
        if model_type in ['openai', 'gpt']:
            self.current_model = 'openai'
        elif model_type in ['claude', 'claude-sonnet']:
            self.current_model = 'claude'
            # Claude 서비스에 모델 타입 설정
            self.claude_service.set_model_type('claude')
        elif model_type in ['claude-opus', 'opus']:
            self.current_model = 'claude-opus'
            # Claude 서비스에 모델 타입 설정
            self.claude_service.set_model_type('claude-opus')
        else:
            print(f"알 수 없는 모델 타입: {model_type}")
            return False
        
        print(f"AI 모델이 {self.current_model}로 설정되었습니다.")
        return True
    
    def get_current_model(self):
        """현재 설정된 AI 모델 반환"""
        return self.current_model
    
    def reset_thread(self):
        """AI 스레드 초기화 (OpenAI만 해당)"""
        if self.current_model == "gpt":
            self.openai_service.reset_thread()
        # Claude는 스레드 개념이 없으므로 아무것도 하지 않음
    
    async def analyze_market_data(self, market_data):
        """선택된 AI 모델로 시장 데이터 분석"""
        print(f"\n=== AI 서비스: {self.current_model.upper()} 모델 사용 중 ===")
        
        if self.current_model == "gpt":
            return await self.openai_service.analyze_market_data(market_data)
        elif self.current_model in ["claude", "claude-opus"]:
            return await self.claude_service.analyze_market_data(market_data)
        else:
            raise ValueError(f"알 수 없는 모델 타입: {self.current_model}")
    
    async def monitor_position(self, market_data, position_info):
        """선택된 AI 모델로 포지션 모니터링"""
        if self.current_model == "gpt":
            return await self.openai_service.monitor_position(market_data, position_info)
        elif self.current_model in ["claude", "claude-opus"]:
            return await self.claude_service.monitor_position(market_data, position_info)
        else:
            raise ValueError(f"알 수 없는 모델 타입: {self.current_model}") 