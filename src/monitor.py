import argparse
import asyncio
import datetime
import logging
import os
import sys
import time

# Windows 콘솔 한글 및 이모지 출력 지원
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import load_config
from kal_seat_finder import KALAwardFinder
from notifier import TelegramNotifier
from tracker import SeatTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("kal_monitor")

class AwardSeatMonitor:
    """보너스 항공권 자동 모니터링 서비스"""

    def __init__(self, config_path: str = None):
        self.config_path = config_path
        self.config = load_config(config_path) if config_path else load_config()
        self.tracker = SeatTracker()
        self.finder = KALAwardFinder(headless=True)
        self._init_notifier()
        self.running = False

    def _init_notifier(self):
        tg = self.config.get("telegram", {})
        self.notifier = TelegramNotifier(
            bot_token=tg.get("bot_token", ""),
            chat_id=tg.get("chat_id", ""),
            enabled=tg.get("enabled", False)
        )

    def reload_config(self):
        self.config = load_config(self.config_path) if self.config_path else load_config()
        self._init_notifier()

    async def run_once(self, notify_all: bool = False) -> int:
        """모든 설정된 노선에 대해 1회 조회를 수행합니다."""
        self.reload_config()
        routes = self.config.get("routes", [])
        if not routes:
            logger.warning("설정된 감시 노선(routes)이 없습니다. config.json 또는 웹 UI에서 노선을 추가하세요.")
            return 0

        logger.info(f"=== 대한항공 마일리지 빈좌석 검사 시작 (총 {len(routes)}개 노선) ===")
        total_new_found = 0

        try:
            for idx, route in enumerate(routes, 1):
                dep = route.get("departure", "ICN")
                dep_name = route.get("departure_name", dep)
                arr = route.get("arrival", "NRT")
                arr_name = route.get("arrival_name", arr)
                months = route.get("months", [])
                classes = route.get("seat_classes", ["X", "O", "A", "Z"])

                logger.info(f"[{idx}/{len(routes)}] {dep_name}({dep}) ➔ {arr_name}({arr}) {months}월 조회 중...")

                available_seats = await self.finder.search_route_award_seats(
                    dep=dep,
                    arr=arr,
                    months=months,
                    target_classes=classes,
                    only_available=True
                )

                # 공항 한글명 보정
                for s in available_seats:
                    s["departure_name"] = dep_name
                    s["arrival_name"] = arr_name

                logger.info(f"  ↳ 검색 결과: 현재 {len(available_seats)}개의 잔여 좌석 확인됨")

                # 신규 오픈 / 취소표 여부 판별
                new_seats = self.tracker.update_and_get_new_seats(
                    available_seats,
                    notify_first_time=notify_all or self.config.get("monitoring", {}).get("notify_on_all_available_on_start", False)
                )

                if new_seats:
                    logger.info(f"  🔔 [신규 좌석 발견!] {len(new_seats)}개의 새로운 좌석이 확인되어 알림을 전송합니다.")
                    total_new_found += len(new_seats)
                    if self.notifier.is_configured():
                        self.notifier.notify_seats(new_seats)
                    else:
                        logger.warning("  ⚠️ 텔레그램 설정이 완료되지 않아 알림이 발송되지 않았습니다.")
                else:
                    logger.info("  ↳ 이전 상태와 동일 (신규 변동 없음)")

            logger.info(f"=== 검사 완료 (새로 오픈된 좌석: {total_new_found}건) ===\n")
            return total_new_found

        except Exception as e:
            logger.error(f"모니터링 실행 중 오류 발생: {e}", exc_info=True)
            return 0

    async def start_loop(self):
        """설정된 주기마다 무한 반복 모니터링을 실행합니다."""
        self.running = True
        interval_min = self.config.get("monitoring", {}).get("check_interval_minutes", 15)
        logger.info(f"대한항공 마일리지 감시 서비스 시작 (점검 주기: {interval_min}분)")

        try:
            while self.running:
                start_t = time.time()
                await self.run_once()

                interval_min = self.config.get("monitoring", {}).get("check_interval_minutes", 15)
                wait_sec = max(60, interval_min * 60)
                logger.info(f"다음 검사까지 {interval_min}분 대기합니다... (Ctrl+C 로 중단 가능)")

                # 1초씩 sleep하여 중단 신호에 반응할 수 있게 함
                for _ in range(int(wait_sec)):
                    if not self.running:
                        break
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("모니터링 루프가 취소되었습니다.")
        finally:
            await self.finder.close()
            logger.info("브라우저 리소스 정리 및 모니터링 종료.")

    def stop(self):
        self.running = False

def main():
    parser = argparse.ArgumentParser(description="대한항공 마일리지 보너스 좌석 모니터링 서비스")
    parser.add_argument("--once", action="store_true", help="주기적 반복 없이 1회만 조회하고 종료")
    parser.add_argument("--notify-all", action="store_true", help="신규 여부와 상관없이 현재 발견된 모든 좌석 알림")
    parser.add_argument("--config", type=str, default=None, help="설정 파일 경로")
    args = parser.parse_args()

    monitor = AwardSeatMonitor(config_path=args.config)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    if args.once:
        try:
            loop.run_until_complete(monitor.run_once(notify_all=args.notify_all))
        finally:
            loop.run_until_complete(monitor.finder.close())
    else:
        try:
            loop.run_until_complete(monitor.start_loop())
        except KeyboardInterrupt:
            logger.info("사용자에 의해 모니터링이 중단되었습니다.")
            monitor.stop()

if __name__ == "__main__":
    main()
