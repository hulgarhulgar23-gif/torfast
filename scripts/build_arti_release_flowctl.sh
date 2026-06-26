#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/../upstream/arti"
cargo build -p arti --locked --release --features flowctl-cc --target-dir target/flowctl
./target/flowctl/release/arti --version
