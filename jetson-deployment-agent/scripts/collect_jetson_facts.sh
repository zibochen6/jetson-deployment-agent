#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  collect_jetson_facts.sh --local --output <path>
  collect_jetson_facts.sh --host <host> --user <user> [--port 22] [--identity <key>] --output <path>

Required output schema keys:
  device, os, jetpack, l4t, cuda, python, memory, storage, package_managers
EOF
}

die() {
  echo "[collect-jetson-facts][ERROR] $*" >&2
  exit 1
}

derive_jetpack_series() {
  local jetpack_version="${1:-}"
  local l4t_release="${2:-}"
  if [[ "$jetpack_version" =~ ^6(\.|$) ]]; then
    echo "6.x"
    return 0
  fi
  if [[ "$jetpack_version" =~ ^5(\.|$) ]]; then
    echo "5.x"
    return 0
  fi
  if [[ "$l4t_release" =~ ^R36 ]]; then
    echo "6.x"
    return 0
  fi
  if [[ "$l4t_release" =~ ^R35 ]]; then
    echo "5.x"
    return 0
  fi
  echo "unknown"
}

detect_package_managers() {
  local managers=()
  if command -v apt-get >/dev/null 2>&1; then
    managers+=("apt")
  fi
  if command -v pip3 >/dev/null 2>&1 || command -v pip >/dev/null 2>&1; then
    managers+=("pip")
  fi
  if command -v conda >/dev/null 2>&1; then
    managers+=("conda")
  fi
  local joined=""
  local item
  for item in "${managers[@]}"; do
    if [[ -z "$joined" ]]; then
      joined="$item"
    else
      joined="$joined,$item"
    fi
  done
  echo "$joined"
}

collect_local_kv() {
  local device_model arch os_pretty kernel l4t_raw l4t_release jetpack_version jetpack_series
  local cuda_version nvcc_path python_version mem_total_kb root_avail_kb package_managers

  if [[ -r /proc/device-tree/model ]]; then
    device_model="$(tr -d '\0' </proc/device-tree/model 2>/dev/null || true)"
  else
    device_model=""
  fi
  if [[ -z "$device_model" ]]; then
    device_model="$(uname -m 2>/dev/null || echo "unknown")"
  fi

  arch="$(uname -m 2>/dev/null || echo "unknown")"
  os_pretty="unknown"
  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    os_pretty="${PRETTY_NAME:-unknown}"
  fi
  kernel="$(uname -r 2>/dev/null || echo "unknown")"

  if [[ -r /etc/nv_tegra_release ]]; then
    l4t_raw="$(tr -d '\r' </etc/nv_tegra_release 2>/dev/null || true)"
  else
    l4t_raw=""
  fi
  l4t_release="$(echo "$l4t_raw" | sed -n 's/.*\(R[0-9][0-9]*\).*/\1/p' | head -n1)"

  jetpack_version="$(dpkg-query -W -f='${Version}' nvidia-jetpack 2>/dev/null | head -n1 || true)"
  jetpack_series="$(derive_jetpack_series "$jetpack_version" "$l4t_release")"

  nvcc_path="$(command -v nvcc 2>/dev/null || true)"
  cuda_version="$(nvcc --version 2>/dev/null | sed -n 's/.*release \([0-9][0-9.]*\).*/\1/p' | tail -n1)"
  if [[ -z "$cuda_version" ]]; then
    cuda_version="$(sed -n 's/.*CUDA Version \([0-9][0-9.]*\).*/\1/p' /usr/local/cuda/version.txt 2>/dev/null | head -n1)"
  fi

  python_version="$(python3 --version 2>/dev/null | awk '{print $2}' || true)"
  mem_total_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo "0")"
  root_avail_kb="$(df -Pk / 2>/dev/null | awk 'NR==2 {print $4}' || echo "0")"
  package_managers="$(detect_package_managers)"

  echo "DEVICE_MODEL=${device_model:-unknown}"
  echo "ARCH=${arch:-unknown}"
  echo "OS_PRETTY=${os_pretty:-unknown}"
  echo "KERNEL=${kernel:-unknown}"
  echo "L4T_RELEASE=${l4t_release:-unknown}"
  echo "L4T_RAW=${l4t_raw:-unknown}"
  echo "JETPACK_VERSION=${jetpack_version:-unknown}"
  echo "JETPACK_SERIES=${jetpack_series:-unknown}"
  echo "CUDA_VERSION=${cuda_version:-unknown}"
  echo "NVCC_PATH=${nvcc_path:-unknown}"
  echo "PYTHON_VERSION=${python_version:-unknown}"
  echo "MEM_TOTAL_KB=${mem_total_kb:-0}"
  echo "ROOT_AVAILABLE_KB=${root_avail_kb:-0}"
  echo "PACKAGE_MANAGERS=${package_managers}"
}

collect_remote_kv() {
  local host="$1"
  local user="$2"
  local port="$3"
  local identity="$4"
  local ssh_cmd=(ssh -p "$port" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
  if [[ -n "$identity" ]]; then
    ssh_cmd+=(-i "$identity")
  fi

  "${ssh_cmd[@]}" "${user}@${host}" 'bash -s' <<'EOF'
set -euo pipefail

derive_jetpack_series() {
  local jetpack_version="${1:-}"
  local l4t_release="${2:-}"
  if [[ "$jetpack_version" =~ ^6(\.|$) ]]; then
    echo "6.x"
    return 0
  fi
  if [[ "$jetpack_version" =~ ^5(\.|$) ]]; then
    echo "5.x"
    return 0
  fi
  if [[ "$l4t_release" =~ ^R36 ]]; then
    echo "6.x"
    return 0
  fi
  if [[ "$l4t_release" =~ ^R35 ]]; then
    echo "5.x"
    return 0
  fi
  echo "unknown"
}

detect_package_managers() {
  local managers=()
  if command -v apt-get >/dev/null 2>&1; then managers+=("apt"); fi
  if command -v pip3 >/dev/null 2>&1 || command -v pip >/dev/null 2>&1; then managers+=("pip"); fi
  if command -v conda >/dev/null 2>&1; then managers+=("conda"); fi
  local joined=""
  local item
  for item in "${managers[@]}"; do
    if [[ -z "$joined" ]]; then joined="$item"; else joined="$joined,$item"; fi
  done
  echo "$joined"
}

if [[ -r /proc/device-tree/model ]]; then
  device_model="$(tr -d '\0' </proc/device-tree/model 2>/dev/null || true)"
else
  device_model=""
fi
if [[ -z "$device_model" ]]; then
  device_model="$(uname -m 2>/dev/null || echo "unknown")"
fi
arch="$(uname -m 2>/dev/null || echo "unknown")"
os_pretty="unknown"
if [[ -f /etc/os-release ]]; then
  . /etc/os-release
  os_pretty="${PRETTY_NAME:-unknown}"
fi
kernel="$(uname -r 2>/dev/null || echo "unknown")"
if [[ -r /etc/nv_tegra_release ]]; then
  l4t_raw="$(tr -d '\r' </etc/nv_tegra_release 2>/dev/null || true)"
else
  l4t_raw=""
fi
l4t_release="$(echo "$l4t_raw" | sed -n 's/.*\(R[0-9][0-9]*\).*/\1/p' | head -n1)"
jetpack_version="$(dpkg-query -W -f='${Version}' nvidia-jetpack 2>/dev/null | head -n1 || true)"
jetpack_series="$(derive_jetpack_series "$jetpack_version" "$l4t_release")"
nvcc_path="$(command -v nvcc 2>/dev/null || true)"
cuda_version="$(nvcc --version 2>/dev/null | sed -n 's/.*release \([0-9][0-9.]*\).*/\1/p' | tail -n1)"
if [[ -z "$cuda_version" ]]; then
  cuda_version="$(sed -n 's/.*CUDA Version \([0-9][0-9.]*\).*/\1/p' /usr/local/cuda/version.txt 2>/dev/null | head -n1)"
fi
python_version="$(python3 --version 2>/dev/null | awk '{print $2}' || true)"
mem_total_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo "0")"
root_avail_kb="$(df -Pk / 2>/dev/null | awk 'NR==2 {print $4}' || echo "0")"
package_managers="$(detect_package_managers)"

echo "DEVICE_MODEL=${device_model:-unknown}"
echo "ARCH=${arch:-unknown}"
echo "OS_PRETTY=${os_pretty:-unknown}"
echo "KERNEL=${kernel:-unknown}"
echo "L4T_RELEASE=${l4t_release:-unknown}"
echo "L4T_RAW=${l4t_raw:-unknown}"
echo "JETPACK_VERSION=${jetpack_version:-unknown}"
echo "JETPACK_SERIES=${jetpack_series:-unknown}"
echo "CUDA_VERSION=${cuda_version:-unknown}"
echo "NVCC_PATH=${nvcc_path:-unknown}"
echo "PYTHON_VERSION=${python_version:-unknown}"
echo "MEM_TOTAL_KB=${mem_total_kb:-0}"
echo "ROOT_AVAILABLE_KB=${root_avail_kb:-0}"
echo "PACKAGE_MANAGERS=${package_managers}"
EOF
}

HOST=""
USER_NAME=""
PORT="22"
IDENTITY=""
LOCAL_MODE=0
OUTPUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --user)
      USER_NAME="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    --identity)
      IDENTITY="${2:-}"
      shift 2
      ;;
    --local)
      LOCAL_MODE=1
      shift
      ;;
    --output)
      OUTPUT="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

if [[ -z "$OUTPUT" ]]; then
  die "Missing --output"
fi

if [[ "$LOCAL_MODE" -eq 0 ]]; then
  if [[ -z "$HOST" || -z "$USER_NAME" ]]; then
    die "Remote mode requires --host and --user (or use --local)"
  fi
fi

RAW_KV=""
if [[ "$LOCAL_MODE" -eq 1 ]]; then
  RAW_KV="$(collect_local_kv)"
else
  RAW_KV="$(collect_remote_kv "$HOST" "$USER_NAME" "$PORT" "$IDENTITY")"
fi

declare -A FACTS=()
while IFS='=' read -r key value; do
  if [[ -n "${key:-}" ]]; then
    FACTS["$key"]="${value:-}"
  fi
done <<< "$RAW_KV"

export DEVICE_MODEL="${FACTS[DEVICE_MODEL]:-unknown}"
export ARCH="${FACTS[ARCH]:-unknown}"
export OS_PRETTY="${FACTS[OS_PRETTY]:-unknown}"
export KERNEL="${FACTS[KERNEL]:-unknown}"
export L4T_RELEASE="${FACTS[L4T_RELEASE]:-unknown}"
export L4T_RAW="${FACTS[L4T_RAW]:-unknown}"
export JETPACK_VERSION="${FACTS[JETPACK_VERSION]:-unknown}"
export JETPACK_SERIES="${FACTS[JETPACK_SERIES]:-unknown}"
export CUDA_VERSION="${FACTS[CUDA_VERSION]:-unknown}"
export NVCC_PATH="${FACTS[NVCC_PATH]:-unknown}"
export PYTHON_VERSION="${FACTS[PYTHON_VERSION]:-unknown}"
export MEM_TOTAL_KB="${FACTS[MEM_TOTAL_KB]:-0}"
export ROOT_AVAILABLE_KB="${FACTS[ROOT_AVAILABLE_KB]:-0}"
export PACKAGE_MANAGERS="${FACTS[PACKAGE_MANAGERS]:-}"

if [[ "$OUTPUT" != "-" ]]; then
  mkdir -p "$(dirname "$OUTPUT")"
fi

python3 - "$OUTPUT" <<'PY'
import json
import os
import sys
from pathlib import Path

def to_int(value: str, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default

def kb_to_gb(kb: int) -> float:
    return round(kb / (1024.0 * 1024.0), 2)

mem_kb = to_int(os.environ.get("MEM_TOTAL_KB", "0"), 0)
storage_kb = to_int(os.environ.get("ROOT_AVAILABLE_KB", "0"), 0)
package_managers = [x for x in os.environ.get("PACKAGE_MANAGERS", "").split(",") if x]

payload = {
    "device": {
        "model": os.environ.get("DEVICE_MODEL", "unknown"),
        "arch": os.environ.get("ARCH", "unknown"),
    },
    "os": {
        "pretty_name": os.environ.get("OS_PRETTY", "unknown"),
        "kernel": os.environ.get("KERNEL", "unknown"),
    },
    "jetpack": {
        "installed_version": os.environ.get("JETPACK_VERSION", "unknown"),
        "series": os.environ.get("JETPACK_SERIES", "unknown"),
    },
    "l4t": {
        "release": os.environ.get("L4T_RELEASE", "unknown"),
        "raw": os.environ.get("L4T_RAW", "unknown"),
    },
    "cuda": {
        "version": os.environ.get("CUDA_VERSION", "unknown"),
        "nvcc_path": os.environ.get("NVCC_PATH", "unknown"),
    },
    "python": {
        "version": os.environ.get("PYTHON_VERSION", "unknown"),
    },
    "memory": {
        "mem_total_kb": mem_kb,
        "mem_total_gb": kb_to_gb(mem_kb),
    },
    "storage": {
        "root_available_kb": storage_kb,
        "root_available_gb": kb_to_gb(storage_kb),
    },
    "package_managers": package_managers,
}

output = sys.argv[1]
serialized = json.dumps(payload, indent=2)
if output == "-":
    print(serialized)
else:
    path = Path(output)
    path.write_text(serialized + "\n", encoding="utf-8")
PY
