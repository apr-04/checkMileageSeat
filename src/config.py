import json
import os
from typing import Dict, Any, List

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")

# 좌석 클래스 매핑
SEAT_CLASS_NAMES = {
    "X": "일반석 보너스 (Economy)",
    "O": "프레스티지석 보너스 (Prestige)",
    "A": "일등석 보너스 (First)",
    "Z": "프레스티지석 좌석승급 (Upgrade)",
    "W": "프리미엄석 보너스",
    "G": "프리미엄석 좌석승급",
    "U": "프레스티지석 좌석승급"
}

# 기본 공항 코드 및 이름 사전
MAJOR_AIRPORTS = {
    "ICN": "서울/인천",
    "GMP": "서울/김포",
    "PUS": "부산/김해",
    "CJU": "제주",
    "NRT": "도쿄/나리타",
    "HND": "도쿄/하네다",
    "KIX": "오사카/간사이",
    "FUK": "후쿠오카",
    "CTS": "삿포로/치토세",
    "OKA": "오키나와",
    "TPE": "타이베이/타오위안",
    "HKG": "홍콩",
    "BKK": "방콕/수완나품",
    "DAD": "다낭",
    "SIN": "싱가포르",
    "DPS": "발리",
    "GUM": "괌",
    "HNL": "호놀룰루(하와이)",
    "LAX": "로스앤젤레스",
    "JFK": "뉴욕/JFK",
    "SFO": "샌프란시스코",
    "SEA": "시애틀",
    "ORD": "시카고",
    "LAS": "라스베이거스",
    "YVR": "밴쿠버",
    "YYZ": "토론토",
    "LHR": "런던/히드로",
    "CDG": "파리/샤를드골",
    "FCO": "로마",
    "FRA": "프랑크푸르트",
    "BCN": "바르셀로나",
    "ZRH": "취리히",
    "SYD": "시드니",
    "AKL": "오클랜드",
    "CEB": "세부",
    "HAN": "하노이",
    "SGN": "호치민",
    "BNE": "브리즈번"
}

# 지역별 주요 목적지 분류
DESTINATIONS_BY_REGION = {
    "JAPAN": {
        "name": "🇯🇵 일본",
        "airports": ["NRT", "HND", "KIX", "FUK", "CTS", "OKA"]
    },
    "SOUTHEAST_ASIA": {
        "name": "🌴 동남아/대만/홍콩",
        "airports": ["BKK", "DAD", "SIN", "DPS", "TPE", "HKG", "CEB", "HAN", "SGN"]
    },
    "AMERICA": {
        "name": "🇺🇸 미주/하와이/괌",
        "airports": ["HNL", "GUM", "LAX", "SFO", "JFK", "SEA", "LAS", "ORD", "YVR", "YYZ"]
    },
    "EUROPE": {
        "name": "🇪🇺 유럽",
        "airports": ["CDG", "LHR", "FCO", "FRA", "BCN", "ZRH"]
    },
    "OCEANIA": {
        "name": "🌊 대양주(호주/뉴질랜드)",
        "airports": ["SYD", "AKL", "BNE"]
    }
}

def load_config(config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """설정 파일을 로드하고 환경변수(ENV)가 있는 경우 우선 적용합니다."""
    example_path = os.path.join(os.path.dirname(config_path), "config.example.json")

    if not os.path.exists(config_path):
        if os.path.exists(example_path):
            try:
                with open(example_path, "r", encoding="utf-8") as ef:
                    save_config(json.load(ef), config_path)
            except Exception:
                save_config(get_default_config(), config_path)
        else:
            save_config(get_default_config(), config_path)

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # 환경변수(GitHub Secrets / Docker / Cloud 호스팅) 오버라이드 지원
    env_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    env_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    env_interval = os.environ.get("CHECK_INTERVAL_MINUTES")

    if "telegram" not in cfg:
        cfg["telegram"] = {}

    if env_token:
        cfg["telegram"]["bot_token"] = env_token.strip()
        cfg["telegram"]["enabled"] = True

    if env_chat_id:
        cfg["telegram"]["chat_id"] = str(env_chat_id).strip()
        cfg["telegram"]["enabled"] = True

    if env_interval:
        try:
            if "monitoring" not in cfg:
                cfg["monitoring"] = {}
            cfg["monitoring"]["check_interval_minutes"] = int(env_interval)
        except ValueError:
            pass

    return cfg

def save_config(config: Dict[str, Any], config_path: str = DEFAULT_CONFIG_PATH) -> None:
    """설정 파일에 저장합니다."""
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def get_default_config() -> Dict[str, Any]:
    """기본 설정값을 반환합니다."""
    return {
        "telegram": {
            "enabled": False,
            "bot_token": "",
            "chat_id": ""
        },
        "monitoring": {
            "check_interval_minutes": 15,
            "notify_on_all_available_on_start": False
        },
        "routes": [
            {
                "departure": "ICN",
                "departure_name": "서울/인천",
                "arrival": "NRT",
                "arrival_name": "도쿄/나리타",
                "months": ["202610"],
                "seat_classes": ["X", "O", "A", "Z"]
            }
        ]
    }
