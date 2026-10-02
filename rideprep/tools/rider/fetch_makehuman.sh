#!/usr/bin/env sh
# Fetch the MakeHuman assets the rider build uses (base mesh, default skeleton + weights, body targets) into a folder.
# MakeHuman's bundled assets are CC0 1.0 (https://github.com/makehumancommunity/makehuman/blob/master/LICENSE.md, part C);
# only assets are used — the loader in mh.py is our own code.
#   sh tools/rider/fetch_makehuman.sh [dir]   (default: .cache/makehuman)
set -eu
DIR=${1:-.cache/makehuman}
REV=${MAKEHUMAN_REV:-master}
BASE=https://raw.githubusercontent.com/makehumancommunity/makehuman/$REV
mkdir -p "$DIR"
for f in makehuman/data/3dobjs/base.obj makehuman/data/rigs/default.mhskel makehuman/data/rigs/default_weights.mhw \
  makehuman/data/targets/macrodetails/caucasian-male-young.target makehuman/data/targets/macrodetails/caucasian-female-young.target \
  makehuman/data/targets/macrodetails/universal-male-young-maxmuscle-minweight.target \
  makehuman/data/targets/macrodetails/universal-male-young-averagemuscle-minweight.target \
  makehuman/data/targets/macrodetails/universal-female-young-maxmuscle-minweight.target \
  makehuman/data/targets/macrodetails/height/male-young-averagemuscle-averageweight-maxheight.target \
  makehuman/data/targets/macrodetails/proportions/male-young-averagemuscle-averageweight-idealproportions.target \
  LICENSE.ASSETS.md; do
  out="$DIR/$(basename "$f")"
  [ -s "$out" ] && continue
  curl -fsSL --retry 3 -o "$out.tmp" "$BASE/$f" && mv "$out.tmp" "$out"
  echo "  $out"
done
echo "MakeHuman assets in $DIR"
