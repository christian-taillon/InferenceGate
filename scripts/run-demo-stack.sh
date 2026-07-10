#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
default_env_file="${DEMO_ENV_FILE:-${PROVIDER_ENV_FILE:-${GO_ENV_FILE:-}}}"
base_config="$repo_root/config.yaml"

select_env_file() {
    local env_files=()
    local file
    while IFS= read -r file; do
        env_files+=("$file")
    done < <(compgen -G "$repo_root/.*.env" || true)

    if [ -f "$repo_root/.env" ]; then
        env_files=("$repo_root/.env" "${env_files[@]}")
    fi

    if [ "${#env_files[@]}" -eq 0 ]; then
        printf 'No .env files found in %s\n' "$repo_root" >&2
        exit 1
    fi

    printf 'Select environment file for the demo stack:\n' >&2
    local index=1
    for file in "${env_files[@]}"; do
        printf '  [%s] %s\n' "$index" "$(basename "$file")" >&2
        index=$((index + 1))
    done

    local choice
    while true; do
        printf 'Enter choice [1-%s]: ' "${#env_files[@]}" >&2
        read -r choice
        if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#env_files[@]}" ]; then
            printf '%s\n' "${env_files[$((choice - 1))]}"
            return
        fi
        printf 'Invalid choice.\n' >&2
    done
}

env_file=""
if [ -n "$default_env_file" ]; then
    if [[ "$default_env_file" = /* ]]; then
        env_file="$default_env_file"
    else
        env_file="$repo_root/$default_env_file"
    fi
fi

args=()
while [ "$#" -gt 0 ]; do
    case "$1" in
        --env)
            if [ "$#" -lt 2 ]; then
                printf 'Missing value for --env\n' >&2
                exit 1
            fi
            if [[ "$2" = /* ]]; then
                env_file="$2"
            else
                env_file="$repo_root/$2"
            fi
            shift 2
            ;;
        --env=*)
            env_file="${1#--env=}"
            if [[ "$env_file" != /* ]]; then
                env_file="$repo_root/$env_file"
            fi
            shift
            ;;
        *)
            args+=("$1")
            shift
            ;;
    esac
done

if [ -z "$env_file" ]; then
    env_file="$(select_env_file)"
fi

if [ ! -f "$env_file" ]; then
    printf 'Missing env file: %s\n' "$env_file" >&2
    exit 1
fi

if [ ! -f "$base_config" ]; then
    printf 'Missing config file: %s\n' "$base_config" >&2
    exit 1
fi

set -a
. "$env_file"
set +a

export LITELLM_API_BASE="${LITELLM_API_BASE:-${baseURL:-}}"
export LITELLM_API_KEY="${LITELLM_API_KEY:-${OPENAI_API_KEY:-}}"

if [ -z "${LITELLM_API_BASE:-}" ] || [ -z "${LITELLM_API_KEY:-}" ]; then
    printf 'Expected API base URL and API key in %s\n' "$env_file" >&2
    exit 1
fi

if [ -n "${GUARD_MODEL:-}" ] && [ -z "${LLAMA_GUARD_MODEL:-}" ]; then
    export LLAMA_GUARD_MODEL="$GUARD_MODEL"
fi

main_api_base="$LITELLM_API_BASE"
main_api_key="$LITELLM_API_KEY"
main_model="${MODEL:-}"
main_demo_model_name="${DEMO_MODEL_NAME:-}"
default_guard_model="${LLAMA_GUARD_MODEL:-}"
default_guard_api_base="${LLAMA_GUARD_API_BASE:-}"
default_guard_api_key="${LLAMA_GUARD_API_KEY:-}"

if [ -f "$repo_root/.env" ]; then
    set -a
    . "$repo_root/.env"
    set +a

    default_guard_model="${default_guard_model:-${LLAMA_GUARD_MODEL:-}}"
    default_guard_api_base="${default_guard_api_base:-${LLAMA_GUARD_API_BASE:-${LITELLM_API_BASE:-}}}"
    default_guard_api_key="${default_guard_api_key:-${LLAMA_GUARD_API_KEY:-${LITELLM_API_KEY:-${OPENAI_API_KEY:-}}}}"

    export LITELLM_API_BASE="$main_api_base"
    export LITELLM_API_KEY="$main_api_key"
    export MODEL="$main_model"
    export DEMO_MODEL_NAME="$main_demo_model_name"
fi

if [ -n "$default_guard_model" ] && [ -z "${LLAMA_GUARD_MODEL:-}" ]; then
    export LLAMA_GUARD_MODEL="$default_guard_model"
fi

if [ -n "$default_guard_api_base" ] && [ -z "${LLAMA_GUARD_API_BASE:-}" ]; then
    export LLAMA_GUARD_API_BASE="$default_guard_api_base"
fi

if [ -n "$default_guard_api_key" ] && [ -z "${LLAMA_GUARD_API_KEY:-}" ]; then
    export LLAMA_GUARD_API_KEY="$default_guard_api_key"
fi

temp_config="$(mktemp "$repo_root/.litellm-demo-config.XXXXXX.yaml")"
cleanup() {
    rm -f "$temp_config"
}
trap cleanup EXIT

REPO_ROOT="$repo_root" BASE_CONFIG="$base_config" TEMP_CONFIG="$temp_config" MODEL_NAME="${MODEL:-}" \
    "$repo_root/.venv/bin/python" - <<'PY'
from pathlib import Path
import os

import yaml

base_config = Path(os.environ["BASE_CONFIG"])
temp_config = Path(os.environ["TEMP_CONFIG"])
model_name = os.environ.get("MODEL_NAME", "").strip()

with base_config.open(encoding="utf-8") as handle:
    config = yaml.safe_load(handle)

if model_name:
    litellm_params = config["model_list"][0]["litellm_params"]
    litellm_params["model"] = f"openai/{model_name}"

with temp_config.open("w", encoding="utf-8") as handle:
    yaml.safe_dump(config, handle, sort_keys=False)
PY

export LITELLM_CONFIG="$temp_config"

if [ -n "${MODEL:-}" ] && [ -z "${DEMO_MODEL_NAME:-}" ]; then
    export DEMO_MODEL_NAME="$MODEL"
fi

run_cmd() {
    "$@"
}

if [ "${#args[@]}" -eq 0 ]; then
    run_cmd "$repo_root/.venv/bin/python" "$repo_root/demo.py" --env "$env_file"
    exit $?
fi

case "${args[0]}" in
    demo)
        run_cmd "$repo_root/.venv/bin/python" "$repo_root/demo.py" --env "$env_file" "${args[@]:1}"
        ;;
    serve)
        run_cmd "$repo_root/.venv/bin/python" "$repo_root/serve.py" --env "$env_file" "${args[@]:1}"
        ;;
    smoke)
        run_cmd "$repo_root/.venv/bin/python" "$repo_root/tests/smoke_test.py" --env "$env_file" "${args[@]:1}"
        ;;
    --)
        run_cmd "${args[@]:1}"
        ;;
    *)
        run_cmd "${args[@]}"
        ;;
esac
