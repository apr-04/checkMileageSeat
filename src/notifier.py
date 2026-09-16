import datetime
import logging
import requests
from typing import List, Dict, Any, Optional

logger = logging.getLogger("telegram_notifier")

CLASS_BADGES = {
    "X": "🟢 일반석 보너스 (Economy)",
    "O": "🟣 프레스티지석 보너스 (Prestige)",
    "A": "🟡 일등석 보너스 (First)",
    "Z": "🔵 프레스티지 좌석승급 (Upgrade)",
    "W": "⚪ 프리미엄석 보너스",
    "G": "⚪ 프리미엄석 승급"
}

class TelegramNotifier:
    """텔레그램 봇 알림 발송 모듈"""

    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True):
        self.bot_token = bot_token.strip()
        self.chat_id = str(chat_id).strip()
        self.enabled = enabled

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id and self.enabled)

    def send_message(self, text: str, parse_mode: str = "HTML", disable_preview: bool = True) -> bool:
        """텔레그램 메시지를 발송합니다."""
        if not self.is_configured():
            logger.warning("텔레그램 설정이 비활성화되어 있거나 토큰/Chat ID가 입력되지 않았습니다.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            if data.get("ok"):
                logger.info(f"텔레그램 알림 전송 성공! (Chat ID: {self.chat_id})")
                return True
            else:
                logger.error(f"텔레그램 API 오류: {data.get('description')}")
                return False
        except Exception as e:
            logger.error(f"텔레그램 발송 네트워크 에러: {e}")
            return False

    def test_connection(self) -> Dict[str, Any]:
        """텔레그램 연결 상태 및 토큰/챗ID 유효성을 테스트합니다."""
        if not self.bot_token:
            return {"success": False, "message": "봇 토큰(Bot Token)을 입력해주세요."}
        if not self.chat_id:
            return {"success": False, "message": "채팅 ID(Chat ID)를 입력해주세요."}

        # 봇 정보 확인
        try:
            me_res = requests.get(f"https://api.telegram.org/bot{self.bot_token}/getMe", timeout=10).json()
            if not me_res.get("ok"):
                return {"success": False, "message": f"유효하지 않은 봇 토큰입니다: {me_res.get('description')}"}
            bot_username = me_res["result"].get("username", "알 수 없음")
        except Exception as e:
            return {"success": False, "message": f"텔레그램 서버 연결 실패: {e}"}

        # 테스트 메시지 전송
        test_msg = (
            f"🔔 <b>[대한항공 마일리지 알리미]</b>\n"
            f"✅ 텔레그램 연동이 성공적으로 완료되었습니다!\n"
            f"• 봇 이름: @{bot_username}\n"
            f"• 테스트 시각: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"앞으로 설정하신 노선에 빈 좌석이 발견되면 즉시 알림이 전송됩니다."
        )
        ok = self.send_message(test_msg)
        if ok:
            return {"success": True, "message": f"연결 성공! @{bot_username}으로부터 테스트 메시지가 전송되었습니다."}
        else:
            return {"success": False, "message": "메시지 발송 실패. Chat ID를 확인하거나 봇과 먼저 /start 대화를 나누었는지 확인하세요."}

    def notify_seats(self, seats: List[Dict[str, Any]]) -> bool:
        """새로 발견된 빈 좌석 목록을 알림으로 전송합니다."""
        if not seats or not self.is_configured():
            return False

        # 노선별로 그룹화
        grouped = {}
        for s in seats:
            key = (s["departure"], s.get("departure_name", s["departure"]),
                   s["arrival"], s.get("arrival_name", s["arrival"]))
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(s)

        success = True
        for (dep, dep_name, arr, arr_name), seat_items in grouped.items():
            # 날짜순 정렬
            seat_items.sort(key=lambda x: (x["date"], x.get("departure_time", "")))

            msg_lines = [
                f"✈️ <b>[대한항공 마일리지 빈좌석 알림]</b>",
                f"<b>구간:</b> {dep_name}({dep}) ➔ {arr_name}({arr})",
                f"<b>신규 오픈/취소표:</b> 총 <b>{len(seat_items)}개</b> 좌석 발견!\n"
            ]

            for s in seat_items[:20]:  # 텔레그램 메시지 길이 한도 고려 상위 20개
                d_str = s["date"]
                # YYYYMMDD -> YYYY-MM-DD (요일)
                try:
                    dt = datetime.datetime.strptime(d_str, "%Y%m%d")
                    day_kor = ["월", "화", "수", "목", "금", "토", "일"][dt.weekday()]
                    date_display = f"{dt.strftime('%m/%d')}({day_kor})"
                except Exception:
                    date_display = d_str

                cls_badge = CLASS_BADGES.get(s["booking_class"], f"클래스 {s['booking_class']}")
                time_str = f"출발 {s['departure_time']}" if s.get("departure_time") else ""
                
                msg_lines.append(f"• <b>{date_display}</b> {s['flight_number']} {time_str}")
                msg_lines.append(f"  ↳ {cls_badge}")

            if len(seat_items) > 20:
                msg_lines.append(f"\n<i>...외 {len(seat_items) - 20}개의 좌석이 더 있습니다.</i>")

            msg_lines.append(f"\n👉 <a href='https://www.koreanair.com/booking/search?bookingType=A&gnb=true'>대한항공 마일리지 예매 바로가기</a>")

            text = "\n".join(msg_lines)
            if not self.send_message(text):
                success = False

        return success
