"""
server_monitor.py — Monitor server resources (CPU, RAM, Disk)
Send alerts when usage exceeds thresholds (80%, 90%, 95%)
"""
import os
import psutil
import json


def _disk_usage_percent() -> float:
    """Disk usage for OS root (Windows vs POSIX)."""
    try:
        if os.name == "nt":
            root = os.environ.get("SystemDrive", "C:") + "\\"
        else:
            root = "/"
        return round(psutil.disk_usage(root).percent, 1)
    except OSError:
        return round(psutil.disk_usage(".").percent, 1)

THRESHOLDS = {
    "warning": 80,   # Yellow alert
    "critical": 90,  # Orange alert
    "danger": 95,    # Red alert
}


def get_server_stats() -> dict:
    """Get current server resource usage."""
    return {
        "cpu": round(psutil.cpu_percent(interval=None), 1),
        "ram": round(psutil.virtual_memory().percent, 1),
        "disk": _disk_usage_percent(),
    }


def check_server_alerts() -> list[dict]:
    """
    Check server resources and return alerts if thresholds exceeded.
    """
    alerts = []
    stats = get_server_stats()
    
    for resource, value in stats.items():
        if value >= THRESHOLDS["danger"]:
            alerts.append({
                "type": "server_resource",
                "severity": "danger",
                "color": "#b71c1c",
                "resource": resource.upper(),
                "value": value,
                "threshold": THRESHOLDS["danger"],
                "message": f"🚨 Server {resource.upper()} at {value}% — CRITICAL (>{THRESHOLDS['danger']}%)",
            })
        elif value >= THRESHOLDS["critical"]:
            alerts.append({
                "type": "server_resource",
                "severity": "critical",
                "color": "#ef5350",
                "resource": resource.upper(),
                "value": value,
                "threshold": THRESHOLDS["critical"],
                "message": f"⚠️ Server {resource.upper()} at {value}% — HIGH (>{THRESHOLDS['critical']}%)",
            })
        elif value >= THRESHOLDS["warning"]:
            alerts.append({
                "type": "server_resource",
                "severity": "warning",
                "color": "#ffa726",
                "resource": resource.upper(),
                "value": value,
                "threshold": THRESHOLDS["warning"],
                "message": f"⚡ Server {resource.upper()} at {value}% — Elevated (>{THRESHOLDS['warning']}%)",
            })
    
    return alerts


def get_server_stats_json() -> str:
    """Get server stats as JSON string."""
    return json.dumps(get_server_stats())
