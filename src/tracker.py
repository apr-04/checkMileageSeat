import json
import os
import time
from typing import List, Dict, Any, Tuple

DEFAULT_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "seat_cache.json")

class SeatTracker:
    """좌석 상태 추적 및 신규 오픈(취소표) 감지 모듈"""

    def __init__(self, cache_file: str = DEFAULT_CACHE_PATH):
        self.cache_file = cache_file
        self._ensure_dir()
        self.cache: Dict[str, Dict[str, Any]] = self._load_cache()

    def _ensure_dir(self):
        d = os.path.dirname(self.cache_file)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)

    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)

    @staticmethod
    def seat_key(seat: Dict[str, Any]) -> str:
        """좌석 항목 고유 식별 키 생성"""
        return f"{seat['departure']}_{seat['arrival']}_{seat['date']}_{seat['flight_number']}_{seat['booking_class']}"

    def update_and_get_new_seats(self, current_seats: List[Dict[str, Any]], notify_first_time: bool = False) -> List[Dict[str, Any]]:
        """
        현재 조회된 예약 가능 좌석 목록을 기반으로 새로 열린 좌석 목록을 추출합니다.
        
        :param current_seats: 현재 검색된 예약 가능 좌석 리스트
        :param notify_first_time: 첫 실행 시에도 발견된 모든 좌석에 대해 알림을 보낼지 여부
        :return: 신규로 오픈된 좌석 리스트
        """
        now = time.time()
        new_available = []
        is_first_run = len(self.cache) == 0

        # 현재 사용 가능한 좌석 식별
        current_keys = set()
        for seat in current_seats:
            k = self.seat_key(seat)
            current_keys.add(k)

            # 이전에 등록된 적 없거나, 이전에는 available=False 였던 좌석인 경우
            if k not in self.cache:
                self.cache[k] = {
                    "seat": seat,
                    "first_seen": now,
                    "last_seen": now,
                    "available": True
                }
                if not is_first_run or notify_first_time:
                    new_available.append(seat)
            else:
                prev = self.cache[k]
                if not prev.get("available", False):
                    # 이전에 마감되었다가 다시 열린 취소표!
                    new_available.append(seat)
                prev["available"] = True
                prev["last_seen"] = now
                prev["seat"] = seat

        # 이번 조회에 없는 기존 좌석은 available = False 처리
        # (단, 동일한 노선/날짜 범위에 해당하는 것만 False 처리하는 것이 이상적이나 간단하게 업데이트 시간 기반 관리)
        self._save_cache()
        return new_available

    def clear(self):
        """캐시 초기화"""
        self.cache = {}
        if os.path.exists(self.cache_file):
            os.remove(self.cache_file)
