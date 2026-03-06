import os
import json
import time
from datetime import datetime
import pytest

# Store test results
_test_results = []
_suite_start_time = 0

def pytest_sessionstart(session):
    """Called before session starts."""
    global _suite_start_time
    _suite_start_time = time.time()

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Capture test execution status and outcome."""
    # execute all other hooks to obtain the report object
    outcome = yield
    rep = outcome.get_result()

    # We only care about the actual test execution phase
    if rep.when == "call":
        _test_results.append({
            "nodeid": item.nodeid,
            "name": item.name,
            "outcome": rep.outcome, # 'passed', 'failed', 'skipped'
            "duration_sec": rep.duration,
            "timestamp": datetime.now().isoformat()
        })

def pytest_sessionfinish(session, exitstatus):
    """Called after whole test run finishes, write results to JSON."""
    duration = time.time() - _suite_start_time
    
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    report_data = {
        "timestamp": datetime.now().isoformat(),
        "total_duration_sec": duration,
        "exit_status": exitstatus,
        "total_tests": len(_test_results),
        "results": _test_results
    }
    
    # Save as latest
    latest_file = os.path.join(log_dir, "test_run_latest.json")
    with open(latest_file, "w") as f:
        json.dump(report_data, f, indent=4)
        
    # Also save a timestamped version
    timestamped_file = os.path.join(log_dir, f"test_run_{int(time.time())}.json")
    with open(timestamped_file, "w") as f:
        json.dump(report_data, f, indent=4)
