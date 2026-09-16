import asyncio
import datetime
import json
import logging
import os
import sys

# Ensure utf-8 stdout on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import MAJOR_AIRPORTS, DESTINATIONS_BY_REGION
from kal_seat_finder import KALAwardFinder

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_static_data")

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "data", "latest_seats.json")

async def build_static_dataset(max_months: int = 12, target_departure: str = "ICN"):
    """
    주요 목적지들의 마일리지 좌석을 일괄 스캔하여 GitHub Pages용 정적 데이터셋(latest_seats.json)을 생성합니다.
    대한항공 마일리지 예약 가능한 최대 기간(향후 약 360일 / 12개월)을 지원합니다.
    """
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    # 한국 표준시(KST) 기준 설정
    KST = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(KST)
    year = now.year
    month = now.month
    months_to_scan = []
    for _ in range(max_months):
        months_to_scan.append(f"{year}{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1

    # 대표 목적지 목록 추출
    key_destinations = [
        # 일본
        "NRT", "HND", "KIX", "FUK", "CTS", "OKA",
        # 동남아 / 휴양지
        "BKK", "DAD", "SIN", "DPS", "GUM", "TPE", "HKG",
        # 미주 / 하와이
        "HNL", "LAX", "JFK", "SFO",
        # 유럽
        "CDG", "LHR", "FCO", "BCN",
        # 대양주
        "SYD", "AKL"
    ]

    finder = KALAwardFinder(headless=True)
    all_routes_data = {}
    destinations_summary = []

    try:
        logger.info(f"GitHub Pages 데이터 빌드 시작: 출발지={target_departure}, 월 목록={months_to_scan}, 목적지={len(key_destinations)}개")

        for arr in key_destinations:
            if arr == target_departure:
                continue

            arr_name = MAJOR_AIRPORTS.get(arr, arr)
            logger.info(f"스캔 중: {target_departure} ➔ {arr_name}({arr}) ...")

            route_key = f"{target_departure}_{arr}"
            all_routes_data[route_key] = {
                "departure": target_departure,
                "departure_name": MAJOR_AIRPORTS.get(target_departure, target_departure),
                "arrival": arr,
                "arrival_name": arr_name,
                "flights": []
            }

            today_str = now.strftime("%Y%m%d")
            now_time_str = now.strftime("%H:%M")

            for ym in months_to_scan:
                try:
                    month_seats = await finder.fetch_month_seats(target_departure, arr, ym)

                    # 과거 날짜 및 이미 출발한 당일 항공편 제외 처리
                    for s in month_seats:
                        f_date = s.get("date", "")
                        f_time = s.get("departure_time", "")
                        if f_date < today_str:
                            s["available"] = False
                        elif f_date == today_str and f_time and f_time <= now_time_str:
                            s["available"] = False

                    # 유효한 빈좌석만 필터링
                    avail = [s for s in month_seats if s.get("available")]
                    all_routes_data[route_key]["flights"].extend(month_seats)

                    if avail:
                        destinations_summary.append({
                            "departure": target_departure,
                            "destination": arr,
                            "destination_name": arr_name,
                            "month": ym,
                            "total_seats": len(avail),
                            "classes": sorted(list(set(s["booking_class"] for s in avail))),
                            "dates": sorted(list(set(s["date"] for s in avail))),
                            "sample_flights": [f for f in avail if f["booking_class"] in ["X", "O", "A"]][:10] or avail[:10]
                        })

                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.error(f"  {target_departure}->{arr} {ym} 실패: {e}")

        # 메타데이터 및 최종 저장 객체
        dataset = {
            "updated_at": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S (KST)"),
            "departure": target_departure,
            "departure_name": MAJOR_AIRPORTS.get(target_departure, target_departure),
            "months": months_to_scan,
            "airports": MAJOR_AIRPORTS,
            "regions": DESTINATIONS_BY_REGION,
            "destinations_summary": destinations_summary,
            "routes_data": all_routes_data
        }

        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(dataset, f, ensure_ascii=False, indent=2)

        logger.info(f"성공! 정적 데이터셋이 저장되었습니다: {OUTPUT_PATH}")

    finally:
        await finder.close()

if __name__ == "__main__":
    # 기본 12개월(최대 예약 가능 범위) 빌드
    months_count = 12
    if len(sys.argv) > 1:
        try:
            months_count = int(sys.argv[1])
        except ValueError:
            pass

    asyncio.run(build_static_dataset(max_months=months_count))
