import sys
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
arm.animation_data_create()
act = bpy.data.actions[ACTION]
arm.animation_data.action = act
if act.slots: arm.animation_data.action_slot = act.slots[0]
r = act.frame_range
bpy.context.scene.frame_set(int(r[0] + (r[1] - r[0]) * FRAC))
print(ACTION, tuple(r))
