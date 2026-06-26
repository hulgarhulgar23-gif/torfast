#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/../upstream/arti"
cargo build -p arti --locked --release
./target/release/arti --version
