import os
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()

# 환경 설정
ENV = os.getenv("ENV", "development")

# SQLite 데이터베이스 설정
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./bitcoin_trading.db') 

# Bitget API 설정
BITGET_API_KEY = os.getenv("BITGET_API_KEY")          # API 키
BITGET_SECRET_KEY = os.getenv("BITGET_SECRET_KEY")    # API 시크릿 키
BITGET_API_URL = "https://api.bitget.com"             # API 기본 URL
BITGET_API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE")  # API 패스프레이즈

# OpenAI API 설정
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

# Claude API 설정
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

# 서버 설정
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000)) 