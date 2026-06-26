#!/usr/bin/env sh
set -eu

mkdir -p upstream

fetch_repo() {
  name="$1"
  url="$2"
  branch="$3"
  dir="upstream/$name"

  if [ -d "$dir/.git" ]; then
    git -C "$dir" fetch --depth 1 origin "$branch"
    git -C "$dir" checkout --detach FETCH_HEAD
  else
    git clone --depth 1 --branch "$branch" "$url" "$dir"
  fi

  printf '%s %s\n' "$name" "$(git -C "$dir" rev-parse HEAD)"
}

fetch_repo tor https://gitlab.torproject.org/tpo/core/tor.git main
fetch_repo arti https://gitlab.torproject.org/tpo/core/arti.git main
