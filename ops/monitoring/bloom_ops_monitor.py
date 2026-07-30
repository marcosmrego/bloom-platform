#!/usr/bin/env python3
import glob
import json
import os
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

STATE_PATH = Path("/var/lib/bloom-ops/state.json")
ENV_PATH = Path("/etc/bloom-ops/telegram.env")
AGENT = "hermes-agent-a11cqkott97egnix7puwjr1n"
WEBUI = "hermes-webui-a11cqkott97egnix7puwjr1n"


def command(args, timeout=20):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def load_env():
    values = {}
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if "=" in raw and not raw.lstrip().startswith("#"):
            key, value = raw.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


def send(text):
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_HOME_CHANNEL")
    if not token or not chat_id:
        raise RuntimeError("Telegram configuration is incomplete")
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError(f"Telegram returned HTTP {response.status}")


def memory_metrics():
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, raw = line.split(":", 1)
        values[key] = int(raw.strip().split()[0]) * 1024
    memory_pct = 100 * (1 - values["MemAvailable"] / values["MemTotal"])
    swap_pct = (
        100 * (1 - values["SwapFree"] / values["SwapTotal"])
        if values["SwapTotal"]
        else 0
    )
    return memory_pct, swap_pct


def container_info(name):
    result = command(["docker", "inspect", name])
    if result.returncode:
        return None
    payload = json.loads(result.stdout)[0]
    state = payload["State"]
    return {
        "running": state.get("Running", False),
        "health": state.get("Health", {}).get("Status", "none"),
        "restart_count": payload.get("RestartCount", 0),
        "started_at": state.get("StartedAt", ""),
    }


def collect(previous):
    problems = {}
    telemetry = {}

    disk = shutil.disk_usage("/")
    disk_pct = 100 * disk.used / disk.total
    telemetry["disk_pct"] = round(disk_pct, 1)
    if disk_pct >= 75:
        problems["disk"] = f"Disco raiz em {disk_pct:.1f}% (limite 75%)."

    memory_pct, swap_pct = memory_metrics()
    telemetry["memory_pct"] = round(memory_pct, 1)
    telemetry["swap_pct"] = round(swap_pct, 1)
    if memory_pct >= 85:
        problems["memory"] = f"Memória em {memory_pct:.1f}% (limite 85%)."
    if swap_pct >= 90:
        problems["swap"] = f"Swap em {swap_pct:.1f}% (limite 90%)."

    du = command(["du", "-sx", "--block-size=1", "/tmp"], timeout=30)
    tmp_bytes = int(du.stdout.split()[0]) if du.returncode == 0 else -1
    telemetry["tmp_bytes"] = tmp_bytes
    if tmp_bytes >= 1024**3:
        problems["tmp_size"] = f"/tmp ocupa {tmp_bytes / 1024**3:.2f} GiB."
    tirith_count = len(glob.glob("/tmp/tirith-install-*"))
    telemetry["tirith_tmp_count"] = tirith_count
    if tirith_count:
        problems["tirith_tmp"] = (
            f"Detectados {tirith_count} temporários tirith-install em /tmp."
        )

    prior_containers = previous.get("telemetry", {}).get("containers", {})
    containers = {}
    for name in (AGENT, WEBUI):
        info = container_info(name)
        containers[name] = info
        short = "agent" if name == AGENT else "webui"
        if not info:
            problems[f"container_{short}"] = f"Container {short} não encontrado."
            continue
        if not info["running"] or info["health"] not in ("healthy", "none"):
            problems[f"container_{short}"] = (
                f"Container {short}: running={info['running']}, "
                f"health={info['health']}."
            )
        prior = prior_containers.get(name)
        if prior and (
            info["restart_count"] > prior.get("restart_count", 0)
            or info["started_at"] != prior.get("started_at")
        ):
            problems[f"restart_{short}"] = f"Container {short} reiniciou ou foi recriado."
    telemetry["containers"] = containers

    s6 = command(
        ["docker", "exec", AGENT, "/command/s6-svstat", "/run/service/gateway-bloom"]
    )
    s6_text = (s6.stdout or s6.stderr).strip()
    telemetry["s6_gateway"] = s6_text
    if s6.returncode or not s6_text.startswith("up "):
        problems["s6_gateway"] = f"Gateway Bloom fora do ar: {s6_text or 'sem resposta'}."

    cron = command(["docker", "exec", AGENT, "hermes", "-p", "bloom", "cron", "list"])
    cron_text = (cron.stdout or cron.stderr).strip()
    telemetry["cron_state"] = (
        "not_configured" if "No scheduled jobs." in cron_text else "configured"
    )
    if cron.returncode:
        problems["cron_check"] = "Não foi possível consultar o cron do perfil Bloom."
    elif any(word in cron_text.lower() for word in (" failed", " error", " overdue")):
        problems["cron_failure"] = "O cron Bloom reporta falha ou atraso."

    return problems, telemetry


def main():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        previous = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    except (ValueError, OSError):
        previous = {}

    problems, telemetry = collect(previous)
    old = previous.get("problems", {})

    new_keys = sorted(set(problems) - set(old))
    recovered_keys = sorted(set(old) - set(problems))
    changed_keys = sorted(
        key for key in set(problems) & set(old) if problems[key] != old[key]
    )

    if new_keys or changed_keys:
        lines = ["🚨 Bloom Ops — alerta"]
        lines.extend(f"• {problems[key]}" for key in new_keys + changed_keys)
        send("\n".join(lines))
    if recovered_keys:
        lines = ["✅ Bloom Ops — recuperado"]
        lines.extend(f"• {old[key]}" for key in recovered_keys)
        send("\n".join(lines))

    STATE_PATH.write_text(
        json.dumps(
            {
                "checked_at": int(time.time()),
                "problems": problems,
                "telemetry": telemetry,
            },
            indent=2,
        )
    )
    os.chmod(STATE_PATH, 0o600)


if __name__ == "__main__":
    main()
