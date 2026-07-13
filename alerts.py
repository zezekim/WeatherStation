"""Threshold alert engine.

`evaluate_alerts` is a pure function over a reading dict — the Flask app calls
it to surface alerts on the dashboard, and the logger calls it to publish
alerts to MQTT. Thresholds live in config.ALERT_THRESHOLDS.
"""
from config import ALERT_THRESHOLDS

# Human-readable metric names and units for alert messages.
_LABELS = {
    "heat_index": ("Heat index", "°C"),
    "pm2_5": ("PM2.5", "µg/m³"),
    "pm10_0": ("PM10", "µg/m³"),
    "uv_index": ("UV index", ""),
    "wind_speed": ("Wind speed", "m/s"),
    "pressure": ("Pressure", "hPa"),
}

_LEVEL_RANK = {"warning": 1, "danger": 2}


def _breached(value, comparator, threshold):
    if comparator == ">":
        return value > threshold
    if comparator == "<":
        return value < threshold
    return False


def evaluate_alerts(data, thresholds=None):
    """Return a list of active alerts for a reading dict.

    Each alert: {metric, level, value, threshold, message}. For a metric that
    breaches multiple levels, only the most severe is reported. The list is
    sorted most-severe first.
    """
    if thresholds is None:
        thresholds = ALERT_THRESHOLDS

    alerts = []
    for metric, rules in thresholds.items():
        value = data.get(metric)
        if value is None:
            continue
        worst = None
        for level, comparator, threshold in rules:
            if _breached(value, comparator, threshold):
                if worst is None or _LEVEL_RANK[level] > _LEVEL_RANK[worst[0]]:
                    worst = (level, comparator, threshold)
        if worst:
            level, comparator, threshold = worst
            label, unit = _LABELS.get(metric, (metric, ""))
            direction = "above" if comparator == ">" else "below"
            alerts.append({
                "metric": metric,
                "level": level,
                "value": round(value, 1),
                "threshold": threshold,
                "message": f"{label} {value:g}{unit} is {direction} {threshold:g}{unit}",
            })

    alerts.sort(key=lambda a: _LEVEL_RANK[a["level"]], reverse=True)
    return alerts
