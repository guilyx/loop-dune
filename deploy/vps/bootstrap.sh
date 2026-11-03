#!/usr/bin/env bash
# Provision a fresh Ubuntu 22.04/24.04 or Debian 12 server for the Loop stack.
# Run once as root; safe to re-run.
#
#   curl -fsSL https://raw.githubusercontent.com/guilyx/loopscan/master/deploy/vps/bootstrap.sh \
#     | sudo bash
#
# What it does:
#   * security updates, unattended-upgrades (automatic reboots off), fail2ban for SSH
#   * Docker Engine + Compose plugin from Docker's apt repository, log rotation
#   * firewall: only SSH, 80 and 443 open
#   * a swap file on small boxes (Postgres and Next.js builds like headroom)
#   * a `loop` user in the docker group with root's SSH keys, the repo in /opt/loop-dune
#   * SSH: key-only logins once a key is installed (never locks you out without one)
#
# Settings (environment): DEPLOY_USER=loop APP_DIR=/opt/loop-dune BRANCH=master
#   REPO_URL=https://github.com/guilyx/loopscan.git SWAP_SIZE=2G
set -Eeuo pipefail

DEPLOY_USER="${DEPLOY_USER:-loop}"
APP_DIR="${APP_DIR:-/opt/loop-dune}"
REPO_URL="${REPO_URL:-https://github.com/guilyx/loopscan.git}"
BRANCH="${BRANCH:-master}"
SWAP_SIZE="${SWAP_SIZE:-2G}"

log() { printf '\033[1m==> %s\033[0m\n' "$*"; }
[[ $EUID -eq 0 ]] || { echo "run as root (sudo bash bootstrap.sh)" >&2; exit 1; }
# shellcheck source=/dev/null
. /etc/os-release
case "$ID" in
  ubuntu|debian) ;;
  *) echo "unsupported distribution: $ID (Ubuntu or Debian expected)" >&2; exit 1 ;;
esac
export DEBIAN_FRONTEND=noninteractive

log "system packages and security updates"
apt-get update -q
apt-get upgrade -yq
apt-get install -yq ca-certificates curl git gnupg openssl ufw fail2ban unattended-upgrades age
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
systemctl enable --now fail2ban > /dev/null

log "Docker Engine"
if ! command -v docker > /dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/$ID ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
if [[ ! -f /etc/docker/daemon.json ]]; then
  cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" },
  "live-restore": true
}
EOF
  systemctl restart docker
fi
systemctl enable --now docker > /dev/null

log "firewall (SSH, HTTP, HTTPS)"
# Docker publishes ports through its own iptables chains, bypassing ufw; the stack only
# publishes 80/443 (Caddy), which are open anyway. Postgres is never published.
ufw default deny incoming > /dev/null
ufw default allow outgoing > /dev/null
ufw allow OpenSSH > /dev/null
ufw allow 80/tcp > /dev/null
ufw allow 443/tcp > /dev/null
ufw allow 443/udp > /dev/null   # HTTP/3
ufw --force enable > /dev/null

if ! swapon --show | grep -q . && [[ "$(free -m | awk '/^Mem:/ {print $2}')" -lt 4096 ]]; then
  log "swap file ($SWAP_SIZE)"
  fallocate -l "$SWAP_SIZE" /swapfile
  chmod 600 /swapfile
  mkswap /swapfile > /dev/null
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -q vm.swappiness=10
  echo 'vm.swappiness=10' > /etc/sysctl.d/99-loop-swap.conf
fi

log "deploy user '$DEPLOY_USER'"
id "$DEPLOY_USER" > /dev/null 2>&1 || useradd --create-home --shell /bin/bash "$DEPLOY_USER"
usermod -aG docker "$DEPLOY_USER"
home=$(getent passwd "$DEPLOY_USER" | cut -d: -f6)
if [[ -s /root/.ssh/authorized_keys && ! -s "$home/.ssh/authorized_keys" ]]; then
  install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$home/.ssh"
  install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /root/.ssh/authorized_keys "$home/.ssh/authorized_keys"
fi

if [[ -s /root/.ssh/authorized_keys || -s "$home/.ssh/authorized_keys" ]]; then
  log "SSH: keys only"
  cat > /etc/ssh/sshd_config.d/10-loop.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
  sshd -t   # never reload a broken config
  systemctl try-reload-or-restart ssh 2>/dev/null || systemctl try-reload-or-restart sshd || true
else
  log "SSH: no authorized key found, leaving password login on (add a key, then re-run)"
fi

log "repository in $APP_DIR"
if [[ ! -d "$APP_DIR/.git" ]]; then
  install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR"
  runuser -u "$DEPLOY_USER" -- git clone --quiet --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
env_file="$APP_DIR/deploy/vps/.env"
if [[ ! -f "$env_file" ]]; then
  install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR/deploy/vps/.env.example" "$env_file"
  # fresh random secrets; everything else is left for you to fill in
  for key in POSTGRES_PASSWORD DASHBOARD_DB_PASSWORD REVALIDATE_TOKEN; do
    sed -i "s|^$key=$|$key=$(openssl rand -hex 24)|" "$env_file"
  done
fi

cat <<EOF

Server ready. Next, as $DEPLOY_USER:

  1. Edit $env_file
       DOMAIN, ACME_EMAIL, ETH_RPC_URLS, BSC_RPC_URLS, BACKUP_AGE_RECIPIENTS, BACKUP_REMOTE...
     (database passwords and the refresh token were generated for you)
  2. Point DNS for your domain at this server.
  3. $APP_DIR/deploy/vps/stack.sh deploy

Full guide: docs/vps.md
EOF
