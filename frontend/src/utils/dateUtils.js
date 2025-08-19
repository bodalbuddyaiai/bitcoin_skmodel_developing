/**
 * ISO 형식의 날짜 문자열을 사용자 친화적인 형식으로 변환합니다.
 * @param {string} isoString - ISO 형식의 날짜 문자열
 * @returns {string} 포맷팅된 날짜 문자열
 */
export const formatDateTime = (isoString) => {
  if (!isoString) return '없음';
  
  try {
    const date = new Date(isoString);
    
    // 유효한 날짜인지 확인
    if (isNaN(date.getTime())) {
      return '유효하지 않은 날짜';
    }
    
    // 날짜 및 시간 포맷팅
    return date.toLocaleString('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
  } catch (error) {
    console.error('날짜 포맷팅 오류:', error);
    return '날짜 포맷팅 오류';
  }
}; 