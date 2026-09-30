import asyncio
import datetime
import json
import logging
import os
import random
import sys
import tempfile
import time
from typing import List, Dict, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from playwright.async_api import async_playwright, BrowserContext, Page

logger = logging.getLogger("kal_finder")

class KALAwardFinder:
    """대한항공 보너스 항공권 좌석 조회 엔진 (Akamai WAF 우회 & 세션 지속성 적용)"""

    def __init__(
        self,
        headless: Optional[bool] = None,
        proxy: Optional[str] = None,
        user_data_dir: Optional[str] = None
    ):
        """
        :param headless: 헤드리스 모드 여부. None일 경우 환경에 따라 자동 결정 (Windows에서는 Akamai WAF 우회를 위해 기본 False/오프스크린 모드)
        :param proxy: 프록시 서버 URL (예: http://user:pass@host:port 또는 socks5://host:port)
        :param user_data_dir: 브라우저 영구 프로필 디렉터리 경로 (쿠키, 세션, Akamai 센서 데이터 보존)
        """
        if headless is None:
            # 윈도우 환경에서는 일반 헤드리스 시 Akamai WAF 차단(403/ERR_HTTP2_PROTOCOL_ERROR)이 발생하므로
            # 기본적으로 헤디드 모드(오프스크린)로 실행하여 정상 브라우저 지문 유지
            self.headless = False if sys.platform == "win32" else True
        else:
            if sys.platform == "win32" and headless is True:
                # 윈도우에서 명시적으로 FORCE_HEADLESS=1이 지정되지 않았다면 WAF 우회를 위해 off-screen headed 사용
                if os.environ.get("FORCE_HEADLESS", "").lower() in ("1", "true"):
                    self.headless = True
                else:
                    self.headless = False
            else:
                self.headless = headless

        self.proxy = proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        self.user_data_dir = user_data_dir or os.path.join(
            os.environ.get("LOCALAPPDATA", tempfile.gettempdir()), "kal_browser_profile"
        )
        os.makedirs(self.user_data_dir, exist_ok=True)

        self._pw = None
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
        """대한항공 웹사이트에 접속하여 유효한 Akamai 세션 및 브라우저 컨텍스트를 초기화합니다."""
        if self._initialized and self._page and not self._page.is_closed():
            return

        chrome_path = self._get_chrome_path()
        logger.info(f"브라우저 실행 중 (경로: {chrome_path or 'Playwright Chromium'}, Headless: {self.headless})...")

        self._pw = await async_playwright().start()

        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage"
        ]
        # 사용자의 화면을 가리거나 방해하지 않도록 화면 밖으로 배치
        if not self.headless:
            args.extend([
                "--window-position=-2000,-2000",
                "--window-size=1400,900"
            ])

        launch_kwargs = {
            "user_data_dir": self.user_data_dir,
            "headless": self.headless,
            "args": args,
            "viewport": {"width": 1400, "height": 900},
            "locale": "ko-KR"
        }
        if chrome_path:
            launch_kwargs["executable_path"] = chrome_path
        if self.proxy:
            logger.info(f"프록시 서버 설정 적용: {self.proxy}")
            launch_kwargs["proxy"] = {"server": self.proxy}

        try:
            self._context = await self._pw.chromium.launch_persistent_context(**launch_kwargs)
            self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()

            logger.info("대한항공 보너스 좌석 페이지 접속 및 Akamai 세션 획득 중...")
            await self._page.goto(
                "https://www.koreanair.com/booking/book-and-manage/award-seat-availability",
                wait_until="domcontentloaded",
                timeout=45000
            )
            await self._page.wait_for_timeout(2000)

            # Akamai 센서 스크립트 활성화를 위한 마우스 이동
            try:
                for i in range(8):
                    await self._page.mouse.move(150 + i * 35, 120 + i * 20)
                    await asyncio.sleep(0.05)
            except Exception:
                pass

            # 쿠키 및 모달 오버레이 제거
            try:
                await self._page.evaluate('''() => {
                    const b = document.querySelector('ke-biscuit-banner') || document.querySelector('kc-global-cookie-banner');
                    if (b) b.remove();
                    const overlay = document.querySelector('.modal-backdrop');
                    if (overlay) overlay.remove();
                }''')
            except Exception:
                pass

            self._initialized = True
            logger.info("대한항공 세션 초기화 완료!")
        except Exception as e:
            logger.error(f"세션 초기화 실패: {e}")
            await self.close()
            raise

    async def refresh_session(self):
        """차단 또는 세션 만료 시 페이지를 재방문하고 센서 토큰을 갱신합니다."""
        if not self._page or self._page.is_closed():
            self._initialized = False
            await self.init_session()
            return

        try:
            logger.info("Akamai 센서 토큰 및 세션 갱신 중...")
            await self._page.goto(
                "https://www.koreanair.com/booking/book-and-manage/award-seat-availability",
                wait_until="domcontentloaded",
                timeout=30000
            )
            await self._page.wait_for_timeout(2000)
            for i in range(5):
                await self._page.mouse.move(100 + i * 50, 120 + i * 30)
                await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"세션 갱신 실패, 세션 완전 재시작: {e}")
            await self.close()
            await self.init_session()

    async def fetch_month_seats(self, dep: str, arr: str, year_month: str, max_retries: int = 3) -> List[Dict[str, Any]]:
        """
        특정 노선 및 월에 대한 모든 항공편의 보너스 좌석 현황을 조회합니다.
        
        :param dep: 출발 공항 코드 (예: ICN)
        :param arr: 도착 공항 코드 (예: NRT, CDG)
        :param year_month: 년월 문자열 (예: 202610 또는 2026-10)
        :param max_retries: 403 차단 시 재시도 횟수
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
                        "accept": "application/json, text/plain, */*",
                        "channel": "pc",
                        "content-type": "application/json",
                        "timestamp": Date.now().toString(),
                        "Referer": "https://www.koreanair.com/booking/book-and-manage/award-seat-availability"
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

        raw_data = None
        for attempt in range(max_retries):
            try:
                raw_data = await self._page.evaluate(js_script)
            except Exception as e:
                logger.warning(f"API 호출 중 예외 발생({e}), 세션 재연결 시도...")
                await self.refresh_session()
                continue

            if raw_data and "error" in raw_data and "403" in str(raw_data.get("error")):
                backoff = (attempt + 1) * 8
                logger.warning(f"Akamai HTTP 403 감지됨 (시도 {attempt+1}/{max_retries}). {backoff}초 대기 후 세션 갱신 및 재시도...")
                await asyncio.sleep(backoff)
                await self.refresh_session()
                continue

            break

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
            # 서버 부하 및 차단 방지를 위한 자연스러운 랜덤 딜레이
            await asyncio.sleep(random.uniform(0.8, 1.6))

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
        airport_names: Optional[Dict[str, str]] = None,
        direction: str = "OUTBOUND"
    ) -> List[Dict[str, Any]]:
        """
        여러 목적지를 순차 조회하여 보너스 좌석이 남아있는 노선 목록을 추출합니다.
        (출국편: dep ➔ destinations / 귀국편: destinations ➔ dep)
        
        :return: 좌석이 존재하는 목적지별 집계 데이터 목록
        """
        if airport_names is None:
            airport_names = {}

        discovered_destinations = []
        KST = datetime.timezone(datetime.timedelta(hours=9))
        now = datetime.datetime.now(KST)
        today_str = now.strftime("%Y%m%d")
        now_time_str = now.strftime("%H:%M")

        for city in destinations:
            if city == dep:
                continue

            scan_dep = city if direction == "INBOUND" else dep
            scan_arr = dep if direction == "INBOUND" else city

            try:
                raw_seats = await self.fetch_month_seats(scan_dep, scan_arr, year_month)
                # 필터링
                avail_flights = []
                avail_classes = set()
                avail_dates = set()

                for s in raw_seats:
                    f_date = s.get("date", "")
                    f_time = s.get("departure_time", "")
                    # 과거 날짜 및 이미 출발한 당일 항공편 제외
                    if f_date < today_str:
                        s["available"] = False
                    elif f_date == today_str and f_time and f_time <= now_time_str:
                        s["available"] = False

                    if not s.get("available"):
                        continue
                    b_cls = s.get("booking_class", "")
                    if target_classes and b_cls not in target_classes:
                        continue

                    avail_flights.append(s)
                    avail_classes.add(b_cls)
                    avail_dates.add(f_date)

                if avail_flights:
                    dep_name = airport_names.get(scan_dep, raw_seats[0].get("departure_name", scan_dep))
                    arr_name = airport_names.get(scan_arr, raw_seats[0].get("arrival_name", scan_arr))
                    discovered_destinations.append({
                        "direction": direction,
                        "departure": scan_dep,
                        "departure_name": dep_name,
                        "destination": scan_arr,
                        "destination_name": arr_name,
                        "total_available_seats": len(avail_flights),
                        "available_classes": sorted(list(avail_classes)),
                        "available_dates": sorted(list(avail_dates)),
                        "sample_flights": avail_flights[:15],
                        "all_flights": avail_flights
                    })

                # 부하 방지용 랜덤 딜레이
                await asyncio.sleep(random.uniform(0.8, 1.5))

            except Exception as e:
                logger.error(f"[{direction}] {scan_dep} -> {scan_arr} 조회 실패: {e}")

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
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        finally:
            self._initialized = False
            self._page = None
            self._context = None
            self._pw = None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    async def demo():
        finder = KALAwardFinder()
        try:
            results = await finder.search_route_award_seats(
                dep="ICN",
                arr="NRT",
                months=["202611"],
                target_classes=["X", "O", "A"],
                only_available=True
            )
            print(f"\n검색 완료: 총 {len(results)}건의 예약 가능 좌석 발견!")
            for r in results[:15]:
                print(f"[{r['date']}] {r['flight_number']} ({r['departure_time']}) - 클래스 {r['booking_class']} ({r['front_class']})")
        finally:
            await finder.close()

    asyncio.run(demo())
