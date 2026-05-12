#!/bin/bash
#
# Golf Model — One-Command VPS Deployment
#
# Usage:
#   ./deploy.sh                        # Show usage
#   ./deploy.sh --setup                # First-time server setup (from your laptop)
#   ./deploy.sh --update               # SSH to VPS, pull, build, restart
#   ./deploy.sh --update-local        # Run on the VPS itself (no SSH); same steps as --update
#
# Public site URL (HTTPS) is independent — e.g. golf.ancc.blog can point here while
# DEPLOY_HOST stays user@server-ip for SSH. Do not run ``--update`` from the VPS
# unless you want SSH-to-self; use ``--update-local`` instead.
#
# Prerequisites:
#   - SSH access to your VPS (e.g., Hetzner)
#   - .env file with configuration
#   - git repo pushed to origin
#
# Configuration (set these or they'll be prompted):
#   DEPLOY_HOST  - SSH host (e.g., user@1.2.3.4)
#   DEPLOY_PATH  - Remote path (default: /opt/golf-model)
#   DEPLOY_BRANCH - Git branch (default: main)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPDATE_STEPS="$SCRIPT_DIR/scripts/deploy-update-steps.sh"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Resolve the authoritative DB path by asking ``src.backup`` on the remote host.
# Falls back to ``<DEPLOY_PATH>/data/golf.db`` if Python/venv isn't available
# yet (first-time setup, broken venv, etc.). This keeps ops checks correct even
# if ``src.db._resolve_db_path()`` redirects the DB to a different location.
remote_db_path() {
    local resolved
    resolved=$(ssh "$DEPLOY_HOST" "cd '$DEPLOY_PATH' 2>/dev/null && ./venv/bin/python -m src.backup --print-path 2>/dev/null" || true)
    if [ -z "$resolved" ]; then
        resolved="$DEPLOY_PATH/data/golf.db"
    fi
    echo "$resolved"
}

# Configuration
DEPLOY_HOST="${DEPLOY_HOST:-}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/golf-model}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
REPO_URL=$(git remote get-url origin 2>/dev/null || echo "")

cmd="${1:-}"

require_ssh_host() {
    if [ -z "$DEPLOY_HOST" ]; then
        echo -n "Enter SSH host (e.g., root@1.2.3.4): "
        read -r DEPLOY_HOST
    fi
    if [ -z "$DEPLOY_HOST" ]; then
        error "No deploy host specified"
    fi
}

case "$cmd" in
    --update-local)
        ;;
    --setup|--update|--status)
        require_ssh_host
        ;;
esac

# ═══════════════════════════════════════════════════════════════
#  First-time Setup
# ═══════════════════════════════════════════════════════════════
setup_server() {
    log "Setting up server at $DEPLOY_HOST..."

    ssh "$DEPLOY_HOST" bash << 'SETUP_EOF'
        set -euo pipefail

        # Install system dependencies
        apt-get update -qq
        apt-get install -y -qq python3 python3-pip python3-venv git sqlite3 nodejs npm

        # Create app directory
        mkdir -p /opt/golf-model
        cd /opt/golf-model

        # Create virtual environment
        python3 -m venv venv
        source venv/bin/activate

        echo "Server setup complete."
SETUP_EOF

    # Clone or pull repo
    log "Deploying code..."
    ssh "$DEPLOY_HOST" bash << CLONE_EOF
        set -euo pipefail
        cd /opt/golf-model

        # Trust the Git host key on first use so non-interactive deploys do not fail.
        # Auth is still required separately (deploy key / agent / token).
        if echo "$REPO_URL" | grep -q "github.com"; then
            mkdir -p ~/.ssh
            chmod 700 ~/.ssh
            touch ~/.ssh/known_hosts
            ssh-keyscan -H github.com >> ~/.ssh/known_hosts 2>/dev/null || true
        fi

        if [ -d ".git" ]; then
            git fetch origin
            git checkout $DEPLOY_BRANCH
            git pull origin $DEPLOY_BRANCH
        else
            # Directory may already contain bootstrap files (like venv) from setup.
            # Initialize git in-place so first-time deploy works without requiring
            # an empty directory.
            git init
            if ! git remote get-url origin >/dev/null 2>&1; then
                git remote add origin $REPO_URL
            fi
            git fetch origin $DEPLOY_BRANCH
            git checkout -B $DEPLOY_BRANCH FETCH_HEAD
        fi

        source venv/bin/activate
        pip install -q -r requirements.txt

        # Build frontend bundle when present so / serves the latest React UI
        if [ -f "frontend/package.json" ]; then
            cd frontend
            export NODE_OPTIONS=--max-old-space-size=2048
            npm ci
            npm run build
            cd /opt/golf-model
        fi
CLONE_EOF

    # Upload .env file
    if [ -f ".env" ]; then
        log "Uploading .env configuration..."
        scp .env "$DEPLOY_HOST:$DEPLOY_PATH/.env"
    else
        warn "No .env file found locally. Create one on the server manually."
    fi

    # Install systemd services
    log "Installing systemd services..."
    ssh "$DEPLOY_HOST" bash << 'SYSTEMD_EOF'
        set -euo pipefail

        # Dashboard service
        cat > /etc/systemd/system/golf-dashboard.service << 'SVC'
[Unit]
Description=Golf Model Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/golf-model
Environment=PATH=/opt/golf-model/venv/bin:/usr/bin:/bin
Environment=LIVE_REFRESH_EMBEDDED_AUTOSTART=0
EnvironmentFile=-/opt/golf-model/.env
ExecStart=/opt/golf-model/venv/bin/python start.py dashboard --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVC

        # Research agent service
        cat > /etc/systemd/system/golf-agent.service << 'SVC'
[Unit]
Description=Golf Model Research Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/golf-model
Environment=PATH=/opt/golf-model/venv/bin:/usr/bin:/bin
EnvironmentFile=-/opt/golf-model/.env
ExecStart=/opt/golf-model/venv/bin/python start.py agent
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
SVC

        # Always-on live refresh worker
        cat > /etc/systemd/system/golf-live-refresh.service << 'SVC'
[Unit]
Description=Golf Model Live Refresh Worker
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/golf-model
Environment=PATH=/opt/golf-model/venv/bin:/usr/bin:/bin
EnvironmentFile=-/opt/golf-model/.env
ExecStart=/opt/golf-model/venv/bin/python -m workers.live_refresh_worker
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVC

        # Nightly backup timer (keep count from DEPLOY_BACKUP_KEEP in .env, default 4)
        cat > /etc/systemd/system/golf-backup.service << 'SVC'
[Unit]
Description=Golf Model Database Backup

[Service]
Type=oneshot
WorkingDirectory=/opt/golf-model
Environment=PATH=/opt/golf-model/venv/bin:/usr/bin:/bin
ExecStart=/bin/bash -lc 'set -a; [ -f /opt/golf-model/.env ] && . /opt/golf-model/.env; set +a; exec /opt/golf-model/venv/bin/python -m src.backup --keep "${DEPLOY_BACKUP_KEEP:-4}"'
SVC

        cat > /etc/systemd/system/golf-backup.timer << 'SVC'
[Unit]
Description=Golf Model Daily Backup

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
SVC

        systemctl daemon-reload
        systemctl enable golf-dashboard golf-agent golf-live-refresh golf-backup.timer
        systemctl start golf-dashboard golf-agent golf-live-refresh golf-backup.timer

        echo "Services installed and started."
SYSTEMD_EOF

    log "Setup complete!"
    log "Dashboard: http://$DEPLOY_HOST:8000"
    log "SSH: ssh $DEPLOY_HOST"
    log ""
    log "Commands:"
    log "  systemctl status golf-dashboard"
    log "  systemctl status golf-agent"
    log "  systemctl status golf-live-refresh"
    log "  journalctl -u golf-dashboard -f"
}


# ═══════════════════════════════════════════════════════════════
#  Update Deployment
# ═══════════════════════════════════════════════════════════════
update_server() {
    log "Updating $DEPLOY_HOST..."
    if [ ! -f "$UPDATE_STEPS" ]; then
        error "Missing $UPDATE_STEPS (repo incomplete?)"
    fi
    q_path=$(printf '%q' "$DEPLOY_PATH")
    q_branch=$(printf '%q' "$DEPLOY_BRANCH")
    ssh "$DEPLOY_HOST" "env DEPLOY_PATH=$q_path DEPLOY_BRANCH=$q_branch bash -s" < "$UPDATE_STEPS"

    log "Update deployed successfully."
}

# Run the same steps as ``update_server`` but on the current machine (no SSH).
# Use this when you are already logged into the VPS under ``$DEPLOY_PATH``.
update_server_local() {
    log "Updating in place at $DEPLOY_PATH (no SSH)..."
    if [ ! -d "$DEPLOY_PATH" ]; then
        error "Directory $DEPLOY_PATH does not exist on this machine. --update-local is only for the VPS shell. From your laptop run: DEPLOY_HOST=user@server ./deploy.sh --update"
    fi
    if [ ! -f "$UPDATE_STEPS" ]; then
        error "Missing $UPDATE_STEPS (run from repo root?)"
    fi
    env DEPLOY_PATH="$DEPLOY_PATH" DEPLOY_BRANCH="$DEPLOY_BRANCH" bash "$UPDATE_STEPS"
    log "Update deployed successfully."
}


# ═══════════════════════════════════════════════════════════════
#  Status Check
# ═══════════════════════════════════════════════════════════════
check_status() {
    log "Checking status on $DEPLOY_HOST..."
    # Note: double-quoted heredoc so $DEPLOY_PATH expands locally before the
    # remote shell sees it. Keep ``\$`` for any variable that should be
    # evaluated on the remote.
    ssh "$DEPLOY_HOST" bash << STATUS_EOF
        echo "=== Services ==="
        systemctl is-active golf-dashboard || true
        systemctl is-active golf-agent || true
        systemctl is-active golf-live-refresh || true

        echo ""
        echo "=== Database ==="
        cd "$DEPLOY_PATH" 2>/dev/null || { echo "Deploy path $DEPLOY_PATH not found"; exit 0; }
        if [ -x venv/bin/python ]; then
            DB_PATH=\$(./venv/bin/python -m src.backup --print-path 2>/dev/null || echo "$DEPLOY_PATH/data/golf.db")
        else
            DB_PATH="$DEPLOY_PATH/data/golf.db"
        fi
        echo "Resolved DB path: \$DB_PATH"
        if [ -f "\$DB_PATH" ]; then
            ls -lh "\$DB_PATH"
        else
            echo "No database found at \$DB_PATH"
        fi

        echo ""
        echo "=== Disk ==="
        df -h "$DEPLOY_PATH"

        echo ""
        echo "=== Recent Logs ==="
        journalctl -u golf-dashboard --no-pager -n 5 2>/dev/null || true
STATUS_EOF
}


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════
case "$cmd" in
    --setup)
        setup_server
        ;;
    --update)
        update_server
        ;;
    --update-local)
        update_server_local
        ;;
    --status)
        check_status
        ;;
    *)
        echo ""
        echo "Golf Model Deployment"
        echo "====================="
        echo ""
        echo "Usage:"
        echo "  $0 --setup          First-time server setup (from laptop; uses SSH)"
        echo "  $0 --update         Pull, build, restart via SSH to DEPLOY_HOST"
        echo "  $0 --update-local   Same as --update but run ON the VPS (no SSH)"
        echo "  $0 --status         Check server status via SSH"
        echo ""
        echo "Configuration:"
        echo "  DEPLOY_HOST=${DEPLOY_HOST:-"(required for --setup / --update / --status)"}"
        echo "  DEPLOY_PATH=$DEPLOY_PATH"
        echo "  DEPLOY_BRANCH=$DEPLOY_BRANCH"
        echo ""
        ;;
esac
