import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from datetime import datetime
import os
from typing import Optional

class EmailService:
    """이메일 전송 서비스"""
    
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        
        # 환경 변수에서 이메일과 비밀번호를 가져와서 특수 문자 제거
        sender_email_raw = os.getenv("SENDER_EMAIL", "")
        sender_password_raw = os.getenv("SENDER_PASSWORD", "")
        
        # 보이지 않는 공백 문자 및 특수 문자 제거
        if sender_email_raw:
            self.sender_email = sender_email_raw.strip().replace('\xa0', '').replace('\u2003', '').replace('\u2002', '')
            self.sender_email = self.sender_email.replace('\u2009', '').replace('\u200b', '').replace('\ufeff', '')
        else:
            self.sender_email = None
            
        if sender_password_raw:
            self.sender_password = sender_password_raw.strip().replace('\xa0', '').replace('\u2003', '').replace('\u2002', '')
            self.sender_password = self.sender_password.replace('\u2009', '').replace('\u200b', '').replace('\ufeff', '')
        else:
            self.sender_password = None
        
        self.enabled = bool(self.sender_email and self.sender_password)
        
        # 디버깅: 이메일/비밀번호 길이 확인
        if self.enabled:
            print(f"✅ 이메일 서비스 활성화됨 - 이메일 길이: {len(self.sender_email)}, 비밀번호 길이: {len(self.sender_password)}")
        else:
            print(f"❌ 이메일 서비스 비활성화됨 - SENDER_EMAIL과 SENDER_PASSWORD 환경 변수를 확인하세요.")
            print(f"   SENDER_EMAIL 설정 여부: {bool(sender_email_raw)}")
            print(f"   SENDER_PASSWORD 설정 여부: {bool(sender_password_raw)}")
        
    def _clean_text(self, text: str) -> str:
        """텍스트에서 문제가 될 수 있는 특수 문자 제거"""
        if not text:
            return text
        
        # 다양한 공백 문자를 일반 공백으로 변환
        text = text.replace('\xa0', ' ')  # NBSP
        text = text.replace('\u2003', ' ')  # EM SPACE
        text = text.replace('\u2002', ' ')  # EN SPACE
        text = text.replace('\u2009', ' ')  # THIN SPACE
        text = text.replace('\u200a', ' ')  # HAIR SPACE
        text = text.replace('\u200b', '')  # ZERO WIDTH SPACE
        text = text.replace('\ufeff', '')  # ZERO WIDTH NO-BREAK SPACE
        
        return text
    
    def send_analysis_email(
        self, 
        recipient_email: str, 
        analysis_type: str,
        analysis_data: dict
    ) -> dict:
        """
        분석 결과를 이메일로 전송
        
        Args:
            recipient_email: 수신자 이메일
            analysis_type: 분석 타입 ("본분석" 또는 "모니터링분석")
            analysis_data: 분석 결과 데이터
        """
        if not self.enabled:
            return {
                "success": False,
                "error": "이메일 설정이 구성되지 않았습니다. SENDER_EMAIL과 SENDER_PASSWORD를 환경변수에 설정해주세요."
            }
        
        if not recipient_email:
            return {"success": False, "error": "수신자 이메일이 설정되지 않았습니다."}
        
        # 분석 데이터의 텍스트 필드를 사전 정리
        if 'ai_analysis' in analysis_data:
            analysis_data['ai_analysis'] = self._clean_text(analysis_data['ai_analysis'])
        if 'additional_info' in analysis_data:
            analysis_data['additional_info'] = self._clean_text(analysis_data['additional_info'])
        
        try:
            # 이메일 내용 구성
            subject = f"[비트코인 자동매매] {analysis_type} 결과 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            html_content = self._create_html_content(analysis_type, analysis_data)
            
            print(f"이메일 전송 시도 - 수신자: {recipient_email}")
            
            # 이메일 메시지 생성
            message = MIMEMultipart("alternative")
            message.set_charset("utf-8")
            
            # From, To는 일반 문자열로 설정
            message["From"] = self.sender_email
            message["To"] = recipient_email
            
            # Subject는 명시적으로 인코딩
            message["Subject"] = str(Header(subject, "utf-8"))
            
            # HTML 본문 정리
            html_content_clean = self._clean_text(html_content)
            
            # HTML 파트 추가
            html_part = MIMEText(html_content_clean, "html", "utf-8")
            message.attach(html_part)
            
            # SMTP 서버 연결 및 전송
            print(f"SMTP 서버 연결 시도: {self.smtp_server}:{self.smtp_port}")
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                print("STARTTLS 완료")
                server.login(self.sender_email, self.sender_password)
                print("로그인 완료")
                
                # as_string()으로 변환하여 전송
                msg_string = message.as_string()
                server.sendmail(self.sender_email, recipient_email, msg_string)
                print("이메일 전송 완료")
            
            return {
                "success": True,
                "message": f"{analysis_type} 결과가 {recipient_email}로 전송되었습니다."
            }
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"이메일 전송 오류 상세:\n{error_detail}")
            return {
                "success": False,
                "error": f"이메일 전송 실패: {str(e)}"
            }
    
    def _create_html_content(self, analysis_type: str, analysis_data: dict) -> str:
        """HTML 형식의 이메일 내용 생성"""
        
        # 기본 정보
        timestamp = datetime.now().strftime('%Y년 %m월 %d일 %H시 %M분')
        
        # 공통 스타일
        style = """
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
            .container { max-width: 800px; margin: 0 auto; padding: 20px; }
            .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                     color: white; padding: 20px; border-radius: 10px 10px 0 0; }
            .content { background: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px; }
            .section { background: white; margin: 15px 0; padding: 15px; border-radius: 8px; 
                      box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .section-title { color: #667eea; font-size: 18px; font-weight: bold; 
                            margin-bottom: 10px; border-bottom: 2px solid #667eea; 
                            padding-bottom: 5px; }
            .info-row { display: flex; justify-content: space-between; padding: 8px 0; 
                       border-bottom: 1px solid #eee; }
            .info-label { font-weight: bold; color: #666; }
            .info-value { color: #333; }
            .decision { font-size: 24px; font-weight: bold; text-align: center; 
                       padding: 20px; margin: 20px 0; border-radius: 8px; }
            .decision.long { background: #d4edda; color: #155724; }
            .decision.short { background: #f8d7da; color: #721c24; }
            .decision.hold { background: #fff3cd; color: #856404; }
            .decision.close { background: #d1ecf1; color: #0c5460; }
            .footer { text-align: center; color: #666; font-size: 12px; margin-top: 20px; }
        </style>
        """
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            {style}
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0;">🤖 비트코인 자동매매 AI 분석</h1>
                    <p style="margin: 10px 0 0 0;">{analysis_type} 리포트</p>
                </div>
                <div class="content">
        """
        
        # AI 결정사항
        decision = analysis_data.get('decision', 'UNKNOWN')
        decision_class = decision.lower()
        decision_text = {
            'LONG': '🚀 롱(매수) 포지션 진입',
            'SHORT': '📉 숏(매도) 포지션 진입',
            'HOLD': '⏸️ 관망 (포지션 없음)',
            'CLOSE_POSITION': '💰 포지션 청산'
        }.get(decision, decision)
        
        html += f"""
                    <div class="decision {decision_class}">
                        {decision_text}
                    </div>
        """
        
        # 시장 정보
        html += """
                    <div class="section">
                        <div class="section-title">📊 시장 정보</div>
        """
        
        if 'current_price' in analysis_data:
            html += f"""
                        <div class="info-row">
                            <span class="info-label">현재가</span>
                            <span class="info-value">${analysis_data['current_price']:,.2f}</span>
                        </div>
            """
        
        if 'timestamp' in analysis_data:
            html += f"""
                        <div class="info-row">
                            <span class="info-label">분석 시각</span>
                            <span class="info-value">{analysis_data['timestamp']}</span>
                        </div>
            """
        
        html += """
                    </div>
        """
        
        # 포지션 정보 (있는 경우)
        if 'position_info' in analysis_data and analysis_data['position_info']:
            pos = analysis_data['position_info']
            html += """
                    <div class="section">
                        <div class="section-title">📈 포지션 정보</div>
            """
            
            if 'side' in pos:
                html += f"""
                        <div class="info-row">
                            <span class="info-label">포지션 방향</span>
                            <span class="info-value">{pos['side']}</span>
                        </div>
                """
            
            if 'leverage' in pos:
                html += f"""
                        <div class="info-row">
                            <span class="info-label">레버리지</span>
                            <span class="info-value">{pos['leverage']}x</span>
                        </div>
                """
            
            if 'entry_price' in pos:
                html += f"""
                        <div class="info-row">
                            <span class="info-label">진입가</span>
                            <span class="info-value">${pos['entry_price']:,.2f}</span>
                        </div>
                """
            
            if 'unrealized_pnl' in pos:
                pnl = pos['unrealized_pnl']
                pnl_color = '#28a745' if pnl >= 0 else '#dc3545'
                html += f"""
                        <div class="info-row">
                            <span class="info-label">미실현 손익</span>
                            <span class="info-value" style="color: {pnl_color}; font-weight: bold;">
                                ${pnl:,.2f}
                            </span>
                        </div>
                """
            
            if 'roe_percentage' in pos:
                roe = pos['roe_percentage']
                roe_color = '#28a745' if roe >= 0 else '#dc3545'
                html += f"""
                        <div class="info-row">
                            <span class="info-label">수익률 (ROE)</span>
                            <span class="info-value" style="color: {roe_color}; font-weight: bold;">
                                {roe:,.2f}%
                            </span>
                        </div>
                """
            
            html += """
                    </div>
            """
        
        # AI 분석 내용
        if 'ai_analysis' in analysis_data:
            html += f"""
                    <div class="section">
                        <div class="section-title">🧠 AI 분석</div>
                        <div style="white-space: pre-wrap; line-height: 1.8;">
                            {analysis_data['ai_analysis']}
                        </div>
                    </div>
            """
        
        # 추가 정보
        if 'additional_info' in analysis_data:
            html += f"""
                    <div class="section">
                        <div class="section-title">ℹ️ 추가 정보</div>
                        <div style="white-space: pre-wrap;">
                            {analysis_data['additional_info']}
                        </div>
                    </div>
            """
        
        # Footer
        html += f"""
                    <div class="footer">
                        <p>이 메일은 비트코인 자동매매 시스템에서 자동으로 전송되었습니다.</p>
                        <p>{timestamp}</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html

