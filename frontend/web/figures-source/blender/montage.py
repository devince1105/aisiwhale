import bpy,sys
argv=sys.argv[sys.argv.index("--")+1:]
out=argv[0]; ins=argv[1:]
imgs=[bpy.data.images.load(p) for p in ins]
w,h=imgs[0].size
res=bpy.data.images.new("m",w*len(imgs),h)
import numpy as np
buf=np.zeros((h,w*len(imgs),4),dtype=np.float32)
for i,im in enumerate(imgs):
    a=np.array(im.pixels[:],dtype=np.float32).reshape(h,w,4); buf[:,i*w:(i+1)*w]=a
res.pixels[:]=buf.ravel(); res.filepath_raw=out; res.file_format='PNG'; res.save()
