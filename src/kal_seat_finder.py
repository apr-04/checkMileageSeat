import asyncio
import json
import logging
import os
import sys
import time
from typing import List, Dict, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger("kal_finder")

class KALAwardFinder:
    """대한항공 보너스 항공권 좌석 조회 엔진"""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._initialized = False

    def _get_chrome_path(self) -> Optional[str]:
        """로컬 및 클라우드(리눅스/윈도우/도커) 환경에 설치된 Chrome 경로를 탐색합니다."""
        env_path = os.environ.get("CHROME_PATH")
        if env_path and os.path.exists(env_path):
            return env_path

        candidates = [
            # Windows
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            # Linux (GitHub Actions / Docker / Ubuntu)
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            # macOS
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    async def init_session(self):
        """대한항공 웹사이트에 접속하여 유효한 브라우저 세션을 초기화합니다."""
        if self._initialized and self._page and not self._page.is_closed():
            return

        chrome_path = self._get_chrome_path()
        logger.info(f"브라우저 실행 중 (실행 경로: {chrome_path or 'Playwright 내장 Chromium'})...")
        
        self._pw = await async_playwright().start()
        launch_kwargs = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage"
            ]
        }
        if chrome_path:
            launch_kwargs["executable_path"] = chrome_path

        self._browser = await self._pw.chromium.launch(**launch_kwargs)
        self._context = await self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1400, "height": 900},
            locale="ko-KR"
        )
        self._page = await self._context.new_page()
        await self._page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        logger.info("대한항공 보너스 좌석 페이지 접속 및 세션 획득 중...")
        try:
            await self._page.goto(
                "https://www.koreanair.com/booking/book-and-manage/award-seat-availability",
                wait_until="domcontentloaded",
                timeout=30000
            )
            # 쿠키 팝업 허용 버튼 처리
            await self._page.wait_for_timeout(1500)
            cookie_btn = await self._page.query_selector('button:has-text("모든 쿠키 허용")')
            if cookie_btn:
                await cookie_btn.click()
            self._initialized = True
            logger.info("대한항공 세션 초기화 완료!")
        except Exception as e:
            logger.error(f"세션 초기화 실패: {e}")
            await self.close()
            raise

    async def fetch_month_seats(self, dep: str, arr: str, year_month: str) -> List[Dict[str, Any]]:
        """
        특정 노선 및 월에 대한 모든 항공편의 보너스 좌석 현황을 조회합니다.
        
        :param dep: 출발 공항 코드 (예: ICN)
        :param arr: 도착 공항 코드 (예: NRT, CDG)
        :param year_month: 년월 문자열 (예: 202610 또는 2026-10)
        :return: 좌석 가능 여부가 포함된 항공편 목록
        """
        if not self._initialized:
            await self.init_session()

        clean_ym = year_month.replace("-", "").strip()
        dep_date = f"{clean_ym}01"  # API 형식: YYYYMM01

        logger.info(f"좌석 조회 요청: {dep} -> {arr} ({clean_ym[:4]}년 {clean_ym[4:]}월)")

        js_script = f"""async () => {{
            try {{
                const res = await fetch("/api/hmp/bonusSeatView/bonusSeatView", {{
                    method: "POST",
                    headers: {{
                        "Content-Type": "application/json",
                        "channel": "pc",
                        "timestamp": Date.now().toString()
                    }},
                    body: JSON.stringify({{
                        departureAirport: "{dep}",
                        arrivalAirport: "{arr}",
                        departureDate: "{dep_date}"
                    }})
                }});
                if (!res.ok) {{
                    return {{ error: "HTTP " + res.status }};
                }}
                return await res.json();
            }} catch (e) {{
                return {{ error: e.toString() }};
            }}
        }}"""

        try:
            raw_data = await self._page.evaluate(js_script)
        except Exception as e:
            logger.warning(f"API 호출 중 세션 오류 발생({e}), 세션 재연결 시도...")
            self._initialized = False
            await self.init_session()
            raw_data = await self._page.evaluate(js_script)

        if not raw_data or "error" in raw_data:
            err = raw_data.get("error", "알 수 없는 오류") if raw_data else "빈 응답"
            logger.error(f"대한항공 API 응답 오류: {err}")
            return []

        flight_list = raw_data.get("flightList", [])
        dep_name = raw_data.get("departureAirportName", dep)
        arr_name = raw_data.get("arrivalAirportName", arr)

        parsed_results = []
        for day_item in flight_list:
            date_str = day_item.get("departureDate") # YYYYMMDD
            if not date_str:
                continue

            for f in day_item.get("flightDetailList", []):
                is_available = f.get("availableSeat") is True
                booking_class = f.get("bookingClass", "")
                front_class = f.get("frontBookingClass", "")
                flight_no = f.get("flightNumber", "")
                dep_time = f.get("departureTime", "")

                parsed_results.append({
                    "date": date_str,
                    "departure": dep,
                    "departure_name": dep_name,
                    "arrival": arr,
                    "arrival_name": arr_name,
                    "flight_number": flight_no,
                    "departure_time": dep_time,
                    "booking_class": booking_class,
                    "front_class": front_class,
                    "available": is_available
                })

        return parsed_results

    async def search_route_award_seats(
        self,
        dep: str,
        arr: str,
        months: List[str],
        target_classes: Optional[List[str]] = None,
        only_available: bool = True
    ) -> List[Dict[str, Any]]:
        """
        여러 월에 걸쳐 특정 노선의 보너스 좌석을 검색하고 필터링합니다.
        """
        all_results = []
        for ym in months:
            month_seats = await self.fetch_month_seats(dep, arr, ym)
            all_results.extend(month_seats)
            # 서버 부하 방지를 위한 짧은 딜레이
            await asyncio.sleep(0.5)

        filtered = []
        for item in all_results:
            if only_available and not item["available"]:
                continue
            if target_classes and item["booking_class"] not in target_classes:
                continue
            filtered.append(item)

        return filtered

    async def explore_available_destinations(
        self,
        dep: str,
        destinations: List[str],
        year_month: str,
        target_classes: Optional[List[str]] = None,
        airport_names: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        여러 목적지를 순차 조회하여 보너스 좌석이 남아있는 목적지 목록을 추출합니다.
        
        :return: 좌석이 존재하는 목적지별 집계 데이터 목록
        """
        if airport_names is None:
            airport_names = {}

        discovered_destinations = []

        for arr in destinations:
            if arr == dep:
                continue

            try:
                raw_seats = await self.fetch_month_seats(dep, arr, year_month)
                # 필터링
                avail_flights = []
                avail_classes = set()
                avail_dates = set()

                for s in raw_seats:
                    if not s.get("available"):
                        continue
                    b_cls = s.get("booking_class", "")
                    if target_classes and b_cls not in target_classes:
                        continue

                    avail_flights.append(s)
                    avail_classes.add(b_cls)
                    avail_dates.add(s.get("date", ""))

                if avail_flights:
                    arr_name = airport_names.get(arr, raw_seats[0].get("arrival_name", arr))
                    discovered_destinations.append({
                        "destination": arr,
                        "destination_name": arr_name,
                        "total_available_seats": len(avail_flights),
                        "available_classes": sorted(list(avail_classes)),
                        "available_dates": sorted(list(avail_dates)),
                        "sample_flights": avail_flights[:15],
                        "all_flights": avail_flights
                    })

                # 부하 방지용 짧은 딜레이
                await asyncio.sleep(0.3)

            except Exception as e:
                logger.error(f"{dep} -> {arr} 목적지 조회 실패: {e}")

        # 잔여 좌석 많은 순 정렬
        discovered_destinations.sort(key=lambda x: x["total_available_seats"], reverse=True)
        return discovered_destinations

    async def close(self):
        """브라우저 리소스를 해제합니다."""
        try:
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        finally:
            self._initialized = False
            self._page = None
            self._context = None
            self._browser = None
            self._pw = None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    async def demo():
        finder = KALAwardFinder(headless=True)
        try:
            results = await finder.search_route_award_seats(
                dep="ICN",
                arr="NRT",
                months=["202610"],
                target_classes=["X", "O", "A"],
                only_available=True
            )
            print(f"\n검색 완료: 총 {len(results)}건의 예약 가능 좌석 발견!")
            for r in results[:15]:
                print(f"[{r['date']}] {r['flight_number']} ({r['departure_time']}) - 클래스 {r['booking_class']} ({r['front_class']})")
        finally:
            await finder.close()

    asyncio.run(demo())
