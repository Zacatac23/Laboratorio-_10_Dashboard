#!/usr/bin/env bash
# Verificación Docker desde copia limpia (ejercicio 8). No toca el directorio de trabajo original.
# Uso: bash scripts/lab11/docker_verificacion.sh <dir_copia_limpia> [puerto_mlflow] [--snapshot]
#   Por defecto: git clone del commit HEAD (copia limpia de lo versionado).
#   --snapshot: además aplica los cambios aún no commiteados (archivos versionados o nuevos no ignorados),
#               para verificar la versión que se va a entregar antes de hacer el commit.
# Evidencia: evidencias/lab11/docker/docker_verificacion.log
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
COPIA="${1:?indicar directorio para la copia limpia}"
export MLFLOW_PORT="${2:-5000}"
export DASHBOARD_PORT="${DASHBOARD_PORT:-8501}"
EVID="$REPO/evidencias/lab11/docker"
LOG="$EVID/docker_verificacion.log"
mkdir -p "$EVID"
: > "$LOG"
paso() { echo; echo "### $(date '+%Y-%m-%dT%H:%M:%S%z') \$ $*"; "$@"; echo "[código de salida: $?]"; } >> "$LOG" 2>&1

{ echo "Verificación Docker — copia limpia: $COPIA — MLFLOW_PORT=$MLFLOW_PORT DASHBOARD_PORT=$DASHBOARD_PORT"; } >> "$LOG"
paso docker version --format 'Cliente {{.Client.Version}} / Engine {{.Server.Version}}'
paso docker compose version
rm -rf "$COPIA"
paso git clone --no-local --quiet "$REPO" "$COPIA"
cd "$COPIA" || exit 1
if [ "${3:-}" = "--snapshot" ]; then
  (cd "$REPO" && git ls-files -co --exclude-standard -z) | rsync -a --from0 --files-from=- "$REPO/" "$COPIA/"
  echo "MODO SNAPSHOT: commit base $(git rev-parse HEAD) + cambios sin commitear del directorio de trabajo" >> "$LOG"
fi
export GIT_COMMIT="$(git rev-parse HEAD)"
paso git -C "$COPIA" log --oneline -1
paso git -C "$COPIA" status --short
paso grep -n "allowed-hosts" docker-compose.yml
paso docker compose build
paso docker run --rm --entrypoint sh observatorio-turismo:lab11 -c 'echo "usuario: $(id)"; echo "--- /app"; ls -la /app; echo "--- /app/data (debe estar vacío)"; ls -la /app/data; echo "--- CSV/DB/secretos/.git en la imagen:"; find / -xdev \( -name "*.csv" -o -name "mlflow.db" -o -name "*.db" -o -name ".env" -o -name "*.pem" -o -name "*.key" -o -name ".git" -o -name "mlruns" \) -not -path "/proc/*" -not -path "/usr/*" -not -path "/etc/ssl/*" 2>/dev/null; echo "(fin de búsqueda)"; pip list 2>/dev/null | grep -iE "^(mlflow|statsmodels|streamlit|pandas|numpy) "'
paso docker compose up -d --wait
paso docker compose ps
paso curl -s -o /dev/null -w "dashboard /_stcore/health HTTP %{http_code}\n" "http://127.0.0.1:$DASHBOARD_PORT/_stcore/health"
paso curl -s -w "\nmlflow /health HTTP %{http_code}\n" "http://127.0.0.1:$MLFLOW_PORT/health"
paso shasum -a 256 data/estimaciones_aprobadas.csv data/estimaciones_aprobadas.manifest.json
# Dos ejecuciones dry-run idénticas (mismo commit, config y datos) para reproducibilidad
paso docker compose run --rm pipeline python pipeline.py --config config/pipeline_config.yaml --no-publish
paso docker compose run --rm pipeline python pipeline.py --config config/pipeline_config.yaml --no-publish
paso shasum -a 256 data/estimaciones_aprobadas.csv data/estimaciones_aprobadas.manifest.json
# Publicación controlada en la copia (genera una segunda versión aprobada y respalda la anterior)
paso docker compose run --rm pipeline
paso shasum -a 256 data/estimaciones_aprobadas.csv data/estimaciones_aprobadas.manifest.json
paso ls -la data/backup_aprobadas
paso docker compose run --rm --no-deps pipeline python -m src.restore_version --list
# Persistencia: down (sin -v) y up
paso curl -s -X POST -H "Content-Type: application/json" -d '{"experiment_ids":["1"],"max_results":100}' "http://127.0.0.1:$MLFLOW_PORT/api/2.0/mlflow/runs/search" -o "$EVID/runs_antes_down.json"
paso docker compose down
paso docker volume ls --filter name=observatorio_turismo
paso docker compose up -d --wait
paso curl -s -X POST -H "Content-Type: application/json" -d '{"experiment_ids":["1"],"max_results":100}' "http://127.0.0.1:$MLFLOW_PORT/api/2.0/mlflow/runs/search" -o "$EVID/runs_despues_up.json"
paso python3 -c "import json,sys; a=json.load(open('$EVID/runs_antes_down.json')).get('runs',[]); b=json.load(open('$EVID/runs_despues_up.json')).get('runs',[]); ia={r['info']['run_id'] for r in a}; ib={r['info']['run_id'] for r in b}; print('runs antes:',len(ia),'después:',len(ib),'iguales:',ia==ib)"
paso ls -la data/backup_aprobadas logs reports
paso docker compose ps
echo "FIN $(date '+%Y-%m-%dT%H:%M:%S%z')" >> "$LOG"
