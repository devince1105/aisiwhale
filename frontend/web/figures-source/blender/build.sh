#!/bin/zsh
# Builds a figure headless and writes its GLB and .blend (D-198):  ./build.sh tifa
# Needs Blender 5.2 at the usual place, or BLENDER=/path/to/Blender.
setopt pipefail
D=${0:A:h}
NAME=${1:?usage: build.sh <name>}
OUT=${D:h:h}/public/models/characters/$NAME.glb
B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
TMP=$(mktemp -t figure).py
{ cat $D/lib.py $D/figure.py $D/$NAME.py
  echo "OUT='$OUT'; BUDGET=9990"
  cat $D/export.py
  echo "bpy.ops.wm.save_as_mainfile(filepath='$D/$NAME.blend', compress=True)"
} > $TMP
$B -b --factory-startup --python-exit-code 1 --python $TMP 2>&1 | grep -E "^(parts|atlas|triangles|Traceback|  File|[A-Za-z]*Error)"
rm -f $TMP $D/$NAME.blend1
