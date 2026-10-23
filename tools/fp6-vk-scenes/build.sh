#!/bin/sh
# Compile every scene's shaders to SPIR-V into $1 (default ./spv), named SCENE.vert.spv / SCENE.frag.spv.
set -e
OUT=${1:-spv}
mkdir -p "$OUT"
for f in *.vert *.frag; do
	glslangValidator -V "$f" -o "$OUT/$f.spv" > /dev/null
done
