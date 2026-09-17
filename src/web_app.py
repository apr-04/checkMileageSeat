import asyncio
import datetime
import json
import logging
import os
import sys
import threading
import time
from flask import Flask, render_template, request, jsonify

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# src 폴더를 파이썬 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import load_config, save_config, SEAT_CLASS_NAMES, MAJOR_AIRPORTS, DESTINATIONS_BY_REGION
from kal_seat_finder import KALAwardFinder
from notifier import TelegramNotifier
from tracker import SeatTracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("kal_webapp")

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"),
    static_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
)

# 백그라운드 모니터링 상태 전역 변수
monitor_state = {
    "is_running": False,
    "last_check_time": None,
    "last_results_count": 0,
    "last_new_seats_count": 0,
    "logs": []
}
monitor_thread: threading.Thread = None
monitor_stop_event = threading.Event()

def add_log(msg: str):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    monitor_state["logs"].append(entry)
    if len(monitor_state["logs"]) > 100:
        monitor_state["logs"].pop(0)

def background_monitor_worker():
    """백그라운드 스레드에서 주기적으로 모니터링을 수행하는 루커"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    add_log("백그라운드 모니터링 스레드가 시작되었습니다.")
    tracker = SeatTracker()

    async def check_cycle():
        finder = KALAwardFinder(headless=True)
        try:
            cfg = load_config()
            routes = cfg.get("routes", [])
            tg = cfg.get("telegram", {})
            notifier = TelegramNotifier(
                bot_token=tg.get("bot_token", ""),
                chat_id=tg.get("chat_id", ""),
                enabled=tg.get("enabled", False)
            )

            total_found = 0
            total_new = 0

            for r in routes:
                if monitor_stop_event.is_set():
                    break
                dep = r.get("departure", "ICN")
                dep_name = r.get("departure_name", dep)
                arr = r.get("arrival", "NRT")
                arr_name = r.get("arrival_name", arr)
                months = r.get("months", [])
                classes = r.get("seat_classes", ["X", "O", "A", "Z"])

                add_log(f"좌석 검사 중: {dep_name}({dep}) ➔ {arr_name}({arr}) {months}월")
                seats = await finder.search_route_award_seats(
                    dep=dep, arr=arr, months=months, target_classes=classes, only_available=True
                )
                for s in seats:
                    s["departure_name"] = dep_name
                    s["arrival_name"] = arr_name

                total_found += len(seats)
                new_seats = tracker.update_and_get_new_seats(seats)
                total_new += len(new_seats)

                if new_seats:
                    add_log(f"🔔 {dep_name}➔{arr_name}: 신규 좌석 {len(new_seats)}건 발견! 텔레그램 발송 중...")
                    if notifier.is_configured():
                        notifier.notify_seats(new_seats)
                    else:
                        add_log("⚠️ 텔레그램 설정이 완료되지 않아 알림이 생략되었습니다.")
                else:
                    add_log(f"↳ {dep_name}➔{arr_name}: 현재 {len(seats)}개 잔여 (신규 변동 없음)")

            monitor_state["last_check_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            monitor_state["last_results_count"] = total_found
            monitor_state["last_new_seats_count"] = total_new
            add_log(f"검사 주기 완료 (전체 잔여 {total_found}개 / 신규 오픈 {total_new}개)")

        finally:
            await finder.close()

    while not monitor_stop_event.is_set():
        try:
            loop.run_until_complete(check_cycle())
        except Exception as e:
            add_log(f"❌ 모니터링 오류 발생: {e}")

        # 주기 대기
        cfg = load_config()
        interval = max(1, cfg.get("monitoring", {}).get("check_interval_minutes", 15))
        add_log(f"다음 검사까지 {interval}분 대기합니다.")

        for _ in range(interval * 60):
            if monitor_stop_event.is_set():
                break
            time.sleep(1)

    add_log("백그라운드 모니터링 스레드가 종료되었습니다.")
    monitor_state["is_running"] = False

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/config", methods=["GET"])
def get_config_api():
    return jsonify(load_config())

@app.route("/api/config", methods=["POST"])
def update_config_api():
    try:
        data = request.json
        save_config(data)
        return jsonify({"success": True, "message": "설정이 성공적으로 저장되었습니다."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/airports", methods=["GET"])
def get_airports_api():
    return jsonify(MAJOR_AIRPORTS)

@app.route("/api/seat_classes", methods=["GET"])
def get_seat_classes_api():
    return jsonify(SEAT_CLASS_NAMES)

@app.route("/api/regions", methods=["GET"])
def get_regions_api():
    return jsonify(DESTINATIONS_BY_REGION)

@app.route("/api/explore", methods=["POST"])
def explore_destinations_api():
    """특정 월에 마일리지 빈 좌석이 남아있는 목적지들을 일괄 탐색"""
    data = request.json or {}
    dep = data.get("departure", "ICN")
    region_key = data.get("region", "ALL")
    custom_airports = data.get("airports", [])
    month = data.get("month")
    classes = data.get("seat_classes", ["X", "O", "A", "Z"])

    if not month:
        now = datetime.datetime.now()
        month = now.strftime("%Y%m")

    # 대상 공항 목록 결정
    target_dests = []
    if custom_airports:
        target_dests = custom_airports
    elif region_key == "ALL":
        for r_info in DESTINATIONS_BY_REGION.values():
            target_dests.extend(r_info["airports"])
        target_dests = list(dict.fromkeys(target_dests))
    elif region_key in DESTINATIONS_BY_REGION:
        target_dests = DESTINATIONS_BY_REGION[region_key]["airports"]
    else:
        target_dests = ["NRT", "KIX", "FUK", "BKK", "DAD", "SIN", "CDG", "HNL"]

    direction = data.get("direction", "OUTBOUND")

    async def do_explore():
        finder = KALAwardFinder(headless=True)
        try:
            return await finder.explore_available_destinations(
                dep=dep,
                destinations=target_dests,
                year_month=month,
                target_classes=classes,
                airport_names=MAJOR_AIRPORTS,
                direction=direction
            )
        finally:
            await finder.close()

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(do_explore())
        return jsonify({
            "success": True,
            "data": results,
            "scanned_count": len(target_dests),
            "found_count": len(results)
        })
    except Exception as e:
        logger.error(f"Explore API error: {e}", exc_info=True)
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/test_telegram", methods=["POST"])
def test_telegram_api():
    data = request.json or {}
    token = data.get("bot_token", "")
    chat_id = data.get("chat_id", "")
    notifier = TelegramNotifier(bot_token=token, chat_id=chat_id, enabled=True)
    res = notifier.test_connection()
    return jsonify(res)

@app.route("/api/search", methods=["POST"])
def direct_search_api():
    """웹 화면에서 즉시 특정 노선/월을 검색하여 반환"""
    data = request.json or {}
    dep = data.get("departure", "ICN")
    arr = data.get("arrival", "NRT")
    months = data.get("months", [])
    classes = data.get("seat_classes", ["X", "O", "A", "Z"])

    if not months:
        # 기본 이번 달 및 다음 달
        now = datetime.datetime.now()
        months = [now.strftime("%Y%m")]

    async def do_search():
        finder = KALAwardFinder(headless=True)
        try:
            return await finder.search_route_award_seats(
                dep=dep,
                arr=arr,
                months=months,
                target_classes=classes,
                only_available=False  # 전체 캘린더 구성을 위해 빈좌석 여부 모두 가져옴
            )
        finally:
            await finder.close()

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(do_search())
        return jsonify({"success": True, "data": results})
    except Exception as e:
        logger.error(f"Search API error: {e}", exc_info=True)
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/monitor/status", methods=["GET"])
def get_monitor_status():
    return jsonify(monitor_state)

@app.route("/api/monitor/start", methods=["POST"])
def start_monitor():
    global monitor_thread, monitor_stop_event
    if monitor_state["is_running"]:
        return jsonify({"success": True, "message": "모니터링이 이미 실행 중입니다."})

    monitor_stop_event.clear()
    monitor_state["is_running"] = True
    monitor_thread = threading.Thread(target=background_monitor_worker, daemon=True)
    monitor_thread.start()
    return jsonify({"success": True, "message": "모니터링이 시작되었습니다."})

@app.route("/api/monitor/stop", methods=["POST"])
def stop_monitor():
    global monitor_stop_event
    if not monitor_state["is_running"]:
        return jsonify({"success": True, "message": "모니터링이 이미 중지되어 있습니다."})

    monitor_stop_event.set()
    monitor_state["is_running"] = False
    add_log("모니터링 중지 요청됨...")
    return jsonify({"success": True, "message": "모니터링 중지 요청이 전송되었습니다."})

def run_server(port: int = 5000):
    print(f"\n========================================================")
    print(f"🚀 대한항공 마일리지 빈좌석 모니터링 웹 대시보드 실행")
    print(f"🌐 웹 브라우저 주소: http://127.0.0.1:{port}")
    print(f"========================================================\n")
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    run_server()
