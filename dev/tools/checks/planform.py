import sys, numpy as np, cv2
from PIL import Image
Image.MAX_IMAGE_PIXELS=None
obj, tex, out, grp_prefix, ch = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
V=[];VT=[];g=None;T=[]
for l in open(obj):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith('vt '): VT.append([float(x) for x in l.split()[1:3]])
    elif l.startswith('o '): g=l[2:].strip()
    elif l.startswith('f ') and g and g.startswith(grp_prefix):
        c=[t.split('/') for t in l.split()[1:]]
        for j in range(1,len(c)-1): T.append([c[0],c[j],c[j+1]])
V=np.array(V);VT=np.array(VT)
img=np.asarray(Image.open(tex).convert('RGBA')).astype(np.float32)
if ch=='lum': src=img[...,:3].mean(2)
else: src=img[...,int(ch)]
H,Wd=src.shape
res=300
x0,x1,z0,z1=-5.0,-0.6,-3.8,2.6
Wp=int((x1-x0)*res); Hp=int((z1-z0)*res)
outimg=np.zeros((Hp,Wp),np.float32); cov=np.zeros((Hp,Wp),bool)
for t in T:
    vi=[int(c[0])-1 for c in t]; ti=[int(c[1])-1 for c in t]
    P=V[vi];
    n=np.cross(P[1]-P[0],P[2]-P[0]);
    if np.linalg.norm(n)<1e-12: continue
    n/=np.linalg.norm(n)
    if n[1]<0.5: continue
    UV=VT[ti]
    pts=np.array([[(p[0]-x0)*res,(z1-p[2])*res] for p in P])
    xmin,ymin=np.floor(pts.min(0)).astype(int); xmax,ymax=np.ceil(pts.max(0)).astype(int)
    xmin=max(xmin,0);ymin=max(ymin,0);xmax=min(xmax,Wp-1);ymax=min(ymax,Hp-1)
    if xmax<xmin or ymax<ymin: continue
    xs,ys=np.meshgrid(np.arange(xmin,xmax+1)+0.5,np.arange(ymin,ymax+1)+0.5)
    a,b,c=pts
    d=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
    if abs(d)<1e-12: continue
    w1=((b[1]-c[1])*(xs-c[0])+(c[0]-b[0])*(ys-c[1]))/d
    w2=((c[1]-a[1])*(xs-c[0])+(a[0]-c[0])*(ys-c[1]))/d
    w3=1-w1-w2
    m=(w1>=-1e-6)&(w2>=-1e-6)&(w3>=-1e-6)
    if not m.any(): continue
    u=w1*UV[0,0]+w2*UV[1,0]+w3*UV[2,0]; v=w1*UV[0,1]+w2*UV[1,1]+w3*UV[2,1]
    px=np.clip((u*Wd).astype(int),0,Wd-1); py=np.clip(((1-v)*H).astype(int),0,H-1)
    yy=(ys[m]-0.5).astype(int); xx=(xs[m]-0.5).astype(int)
    outimg[yy,xx]=src[py[m],px[m]]; cov[yy,xx]=True
vals=outimg[cov]; lo,hi=np.percentile(vals,[3,97])
o=np.clip((outimg-lo)/(hi-lo+1e-6)*255,0,255).astype(np.uint8); o[~cov]=0
Image.fromarray(o).save(out); print(lo,hi,Wp,Hp)
