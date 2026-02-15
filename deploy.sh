#!/bin/bash
#
# Golf Model — One-Command VPS Deployment
#
# Usage:
#   ./deploy.sh                    # Deploy to configured server
#   ./deploy.sh --setup            # First-time server setup
#   ./deploy.sh --update           # Pull latest code and restart
#
# Prerequisites:
#   - SSH access to your VPS (e.g., Hetzner)
#   - .env file with configuration
#   - git repo pushed to origin
#
# Configuration (set these or they'll be prompted):
#   DEPLOY_HOST  - SSH host (e.g., user@1.2.3.4)
#   DEPLOY_PATH  - Remote path (default: /opt/golf-model)
#   DEPLOY_BRANCH - Git branch (default: feature/model-overhaul)

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Configuration
DEPLOY_HOST="${DEPLOY_HOST:-}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/golf-model}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-feature/model-overhaul}"
REPO_URL=$(git remote get-url origin 2>/dev/null || echo "")

if [ -z "$DEPLOY_HOST" ]; then
    echo -n "Enter SSH host (e.g., root@1.2.3.4): "
    read DEPLOY_HOST
fi

if [ -z "$DEPLOY_HOST" ]; then
    error "No deploy host specified"
fi

# ═══════════════════════════════════════════════════════════════
#  First-time Setup
# ═══════════════════════════════════════════════════════════════
setup_server() {
    log "Setting up server at $DEPLOY_HOST..."

    ssh "$DEPLOY_HOST" bash << 'SETUP_EOF'
        set -e

        # Install system dependencies
        apt-get update -qq
        apt-get install -y -qq python3 python3-pip python3-venv git sqlite3

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
        set -e
        cd /opt/golf-model

        if [ -d ".git" ]; then
            git fetch origin
            git checkout $DEPLOY_BRANCH
            git pull origin $DEPLOY_BRANCH
        else
            git clone -b $DEPLOY_BRANCH $REPO_URL .
        fi

        source venv/bin/activate
        pip install -q -r requirements.txt
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
        set -e

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
ExecStart=/opt/golf-model/venv/bin/python start.py agent
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
SVC

        # Nightly backup timer
        cat > /etc/systemd/system/golf-backup.service << 'SVC'
[Unit]
Description=Golf Model Database Backup

[Service]
Type=oneshot
WorkingDirectory=/opt/golf-model
Environment=PATH=/opt/golf-model/venv/bin:/usr/bin:/bin
ExecStart=/opt/golf-model/venv/bin/python -m src.backup --keep 14
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
        systemctl enable golf-dashboard golf-agent golf-backup.timer
        systemctl start golf-dashboard golf-agent golf-backup.timer

        echo "Services installed and started."
SYSTEMD_EOF

    log "Setup complete!"
    log "Dashboard: http://$DEPLOY_HOST:8000"
    log "SSH: ssh $DEPLOY_HOST"
    log ""
    log "Commands:"
    log "  systemctl status golf-dashboard"
    log "  systemctl status golf-agent"
    log "  journalctl -u golf-dashboard -f"
}


# ═══════════════════════════════════════════════════════════════
#  Update Deployment
# ═══════════════════════════════════════════════════════════════
update_server() {
    log "Updating $DEPLOY_HOST..."

    ssh "$DEPLOY_HOST" bash << UPDATE_EOF
        set -e
        cd /opt/golf-model

        # Backup before update
        if [ -f "golf_model.db" ]; then
            source venv/bin/activate
            python -m src.backup --keep 14 || true
        fi

        # Pull latest
        git fetch origin
        git checkout $DEPLOY_BRANCH
        git pull origin $DEPLOY_BRANCH

        # Install deps
        source venv/bin/activate
        pip install -q -r requirements.txt

        # Initialize DB (runs migrations)
        python -c "from src.db import init_db; init_db()"

        # Restart services
        systemctl restart golf-dashboard golf-agent

        echo "Update complete."
UPDATE_EOF

    log "Update deployed successfully."
}


# ═══════════════════════════════════════════════════════════════
#  Status Check
# ═══════════════════════════════════════════════════════════════
check_status() {
    log "Checking status on $DEPLOY_HOST..."
    ssh "$DEPLOY_HOST" bash << 'STATUS_EOF'
        echo "=== Services ==="
        systemctl is-active golf-dashboard || true
        systemctl is-active golf-agent || true

        echo ""
        echo "=== Database ==="
        if [ -f "/opt/golf-model/golf_model.db" ]; then
            ls -lh /opt/golf-model/golf_model.db
        else
            echo "No database found"
        fi

        echo ""
        echo "=== Disk ==="
        df -h /opt/golf-model

        echo ""
        echo "=== Recent Logs ==="
        journalctl -u golf-dashboard --no-pager -n 5 2>/dev/null || true
STATUS_EOF
}


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════
case "${1:-}" in
    --setup)
        setup_server
        ;;
    --update)
        update_server
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
        echo "  $0 --setup     First-time server setup"
        echo "  $0 --update    Pull latest code and restart"
        echo "  $0 --status    Check server status"
        echo ""
        echo "Configuration:"
        echo "  DEPLOY_HOST=$DEPLOY_HOST"
        echo "  DEPLOY_PATH=$DEPLOY_PATH"
        echo "  DEPLOY_BRANCH=$DEPLOY_BRANCH"
        echo ""
        ;;
esac
