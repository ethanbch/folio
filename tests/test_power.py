"""Pause on low battery, resume quickly on power."""

import threading
import time

from folio import macos
from folio.config import Config
from folio.indexer import Indexer, Progress


def make_indexer() -> Indexer:
    idx = object.__new__(Indexer)  # the power loop needs no engine
    idx.cfg = Config(min_battery_percent=20)
    idx.progress = Progress(phase="content")
    idx.stop = threading.Event()
    idx.battery_override = threading.Event()
    idx.wake = threading.Event()
    return idx


def test_resumes_within_3_s_of_plugging_in(monkeypatch):
    power = {"on_battery": True}
    monkeypatch.setattr(macos, "battery", lambda: (power["on_battery"], 15))
    idx = make_indexer()
    done = threading.Event()
    threading.Thread(target=lambda: (idx._wait_for_power(), done.set()), daemon=True).start()
    time.sleep(0.2)
    assert idx.progress.phase == "paused" and idx.progress.battery == 15
    plugged = time.monotonic()
    power["on_battery"] = False
    assert done.wait(5)
    assert time.monotonic() - plugged < 3.5
    assert idx.progress.phase == "content" and idx.progress.battery is None


def test_continue_on_battery_resumes_at_once(monkeypatch):
    monkeypatch.setattr(macos, "battery", lambda: (True, 10))
    idx = make_indexer()
    done = threading.Event()
    threading.Thread(target=lambda: (idx._wait_for_power(), done.set()), daemon=True).start()
    time.sleep(0.2)
    idx.battery_override.set()
    idx.wake.set()
    assert done.wait(1)
    assert idx.progress.phase == "content"
