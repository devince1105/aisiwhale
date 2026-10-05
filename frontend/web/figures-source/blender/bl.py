#!/usr/bin/env python3
"""Send to the running Blender (MCP addon, localhost:9876).
  bl.py run file.py [file2.py ...]   -> execute concatenated code
  bl.py shot out.png [view]          -> set view (front/side/back/q/keep) and screenshot"""
import socket,json,sys
def call(t,p):
    s=socket.create_connection(("localhost",9876),timeout=300)
    s.sendall(json.dumps({"type":t,"params":p}).encode())
    buf=b""
    while True:
        c=s.recv(1<<20)
        if not c: break
        buf+=c
        try: return json.loads(buf)
        except json.JSONDecodeError: pass
    return json.loads(buf)
cmd=sys.argv[1]
if cmd=="run":
    code="\n".join(open(f).read() for f in sys.argv[2:])
    r=call("execute_code",{"code":code})
    if r.get("status")!="success":
        m=r.get("message","")
        try: m=json.loads(m)["traceback"]
        except Exception: pass
        print("ERROR",m); sys.exit(1)
    print(r["result"].get("result",""))
elif cmd=="shot":
    out=sys.argv[2]; view=sys.argv[3] if len(sys.argv)>3 else "front"
    views={"front":(0,0),"side":(90,0),"back":(180,0),"q":(30,12),"q2":(-35,12)}
    if view in views:
        yaw,pitch=views[view]
        code=f'''
import bpy,math
from mathutils import Euler
for a in bpy.context.screen.areas:
    if a.type=='VIEW_3D':
        sp=a.spaces.active; r=sp.region_3d
        sp.shading.type='MATERIAL'; sp.overlay.show_overlays=False
        r.view_perspective='PERSP'
        r.view_rotation=Euler((math.radians(90-{pitch}),0,math.radians({yaw})),'XYZ').to_quaternion()
        r.view_location=(0,0,0.34); r.view_distance=1.0
'''
        call("execute_code",{"code":code})
    r=call("get_viewport_screenshot",{"filepath":out,"max_size":800})
    print(r.get("status"), r.get("message",""))
