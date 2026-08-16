#!/usr/bin/env bash
# Install the Litestream binary if missing. Safe to re-run.
set -euo pipefail

VERSION="${LITESTREAM_VERSION:-0.3.13}"
DEST="${LITESTREAM_BIN:-/usr/local/bin/litestream}"

if [ -x "$DEST" ]; then
    echo "[litestream] already installed: $DEST ($("$DEST" version 2>/dev/null || true))"
    exit 0
fi

arch="$(uname -m)"
case "$arch" in
    x86_64|amd64) asset="litestream-v${VERSION}-linux-amd64.tar.gz" ;;
    aarch64|arm64) asset="litestream-v${VERSION}-linux-arm64.tar.gz" ;;
    *) echo "[litestream] unsupported arch: $arch" >&2; exit 1 ;;
esac

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
url="https://github.com/benbjohnson/litestream/releases/download/v${VERSION}/${asset}"
echo "[litestream] downloading $url"
curl -fsSL "$url" -o "$tmp/litestream.tgz"
tar -xzf "$tmp/litestream.tgz" -C "$tmp"
install -m 0755 "$tmp/litestream" "$DEST"
echo "[litestream] installed $DEST"
