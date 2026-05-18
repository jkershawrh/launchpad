"""Power mode definitions for workload scaling."""

POWER_MODES = {
    "standby": {"count": 5, "concurrency": 1},
    "drive": {"count": 25, "concurrency": 5},
    "boost": {"count": 250, "concurrency": 25},
    "overdrive": {"count": 1000, "concurrency": 50},
    "max_q": {"count": 1000, "concurrency": 100},
    "cooldown": {"count": 5, "concurrency": 1},
}


def get_mode_config(mode: str, count: int = None, concurrency: int = None) -> dict:
    if mode not in POWER_MODES:
        raise ValueError(f"Unknown power mode: {mode}")
    cfg = dict(POWER_MODES[mode])
    if mode == "max_q":
        if count is not None:
            cfg["count"] = count
        if concurrency is not None:
            cfg["concurrency"] = concurrency
    return cfg


def list_modes() -> list[dict]:
    return [{"name": name, **conf} for name, conf in POWER_MODES.items()]
