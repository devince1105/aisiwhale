#!/bin/zsh
# Builds a figure headless and writes its GLB and .blend (D-198):  ./build.sh tifa
# Needs Blender 5.2 at the usual place, or BLENDER=/path/to/Blender. A copy of the .blend also goes to
# the owner's local archive (data/, not in git) as data/blender/<name>-<triangles>.blend, where a figure
# that fills the 10,000-triangle budget (9,500 or more) is named -9999 and any other carries its count.
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
LOG=$($B -b --factory-startup --python-exit-code 1 --python $TMP 2>&1 | grep -E "^(parts|atlas|triangles|Traceback|  File|[A-Za-z]*Error)") || { print -r -- $LOG; exit 1; }
print -r -- $LOG
rm -f $TMP $D/$NAME.blend1
TRIS=$(print -r -- $LOG | sed -nE 's/^triangles [0-9]+ -> ([0-9]+)$/\1/p' | tail -1)
TAG=$(( TRIS >= 9500 ? 9999 : TRIS ))
ARCHIVE=${D:h:h:h:h}/data/blender
mkdir -p $ARCHIVE && cp $D/$NAME.blend $ARCHIVE/$NAME-$TAG.blend && print "archived data/blender/$NAME-$TAG.blend"
