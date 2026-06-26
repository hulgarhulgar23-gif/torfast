#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/../upstream/tor"

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 2
  fi
}

need autoconf
need automake
need pkg-config
need make
need gcc

if command -v brew >/dev/null 2>&1; then
  OPENSSL_DIR="$(brew --prefix openssl@3)"
  LIBEVENT_DIR="$(brew --prefix libevent)"
  ZSTD_DIR="$(brew --prefix zstd)"
  XZ_DIR="$(brew --prefix xz)"
else
  OPENSSL_DIR="${OPENSSL_DIR:-/usr/local}"
  LIBEVENT_DIR="${LIBEVENT_DIR:-/usr/local}"
  ZSTD_DIR="${ZSTD_DIR:-/usr/local}"
  XZ_DIR="${XZ_DIR:-/usr/local}"
fi

./autogen.sh

CPPFLAGS="-I/opt/homebrew/include -I${OPENSSL_DIR}/include -I${LIBEVENT_DIR}/include -I${ZSTD_DIR}/include -I${XZ_DIR}/include" \
LDFLAGS="-L/opt/homebrew/lib -L${OPENSSL_DIR}/lib -L${LIBEVENT_DIR}/lib -L${ZSTD_DIR}/lib -L${XZ_DIR}/lib" \
PKG_CONFIG_PATH="${OPENSSL_DIR}/lib/pkgconfig:${LIBEVENT_DIR}/lib/pkgconfig:${ZSTD_DIR}/lib/pkgconfig:${XZ_DIR}/lib/pkgconfig" \
./configure \
  --disable-asciidoc \
  --disable-manpage \
  --disable-html-manual \
  --with-libevent-dir="${LIBEVENT_DIR}" \
  --with-openssl-dir="${OPENSSL_DIR}" \
  --enable-zstd \
  --enable-lzma

make -j"$(sysctl -n hw.ncpu 2>/dev/null || getconf _NPROCESSORS_ONLN || echo 2)"

./src/app/tor --version
