import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from tracker import SeatTracker
from notifier import TelegramNotifier
from config import load_config, save_config

class TestComponents(unittest.TestCase):

    def setUp(self):
        self.test_cache = os.path.join(os.path.dirname(__file__), "test_cache.json")
        if os.path.exists(self.test_cache):
            os.remove(self.test_cache)
        self.tracker = SeatTracker(cache_file=self.test_cache)

    def tearDown(self):
        if os.path.exists(self.test_cache):
            os.remove(self.test_cache)

    def test_tracker_first_run_and_new_seats(self):
        # 1. First run with notify_first_time=False -> should return 0 new seats
        sample_seats = [
            {"departure": "ICN", "arrival": "NRT", "date": "20261001", "flight_number": "KE713", "booking_class": "X", "available": True},
            {"departure": "ICN", "arrival": "NRT", "date": "20261001", "flight_number": "KE705", "booking_class": "O", "available": True}
        ]
        new_seats = self.tracker.update_and_get_new_seats(sample_seats, notify_first_time=False)
        self.assertEqual(len(new_seats), 0)

        # 2. Second run without change -> should still return 0 new seats
        new_seats2 = self.tracker.update_and_get_new_seats(sample_seats, notify_first_time=False)
        self.assertEqual(len(new_seats2), 0)

        # 3. New seat appears (e.g. newly opened or canceled ticket)
        sample_seats.append({
            "departure": "ICN", "arrival": "NRT", "date": "20261002", "flight_number": "KE703", "booking_class": "A", "available": True
        })
        new_seats3 = self.tracker.update_and_get_new_seats(sample_seats, notify_first_time=False)
        self.assertEqual(len(new_seats3), 1)
        self.assertEqual(new_seats3[0]["booking_class"], "A")

    def test_notifier_validation(self):
        # Unconfigured notifier
        n = TelegramNotifier(bot_token="", chat_id="")
        self.assertFalse(n.is_configured())
        self.assertFalse(n.send_message("test"))

        res = n.test_connection()
        self.assertFalse(res["success"])

if __name__ == "__main__":
    unittest.main()
