import sys, numpy as np
from PIL import Image
obj, out, pre = sys.argv[1], sys.argv[2], sys.argv[3]
V=[];VN=[];g=None;T=[]
for l in open(obj):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith('vn '): VN.append([float(x) for x in l.split()[1:4]])
    elif l.startswith('o '): g=l[2:].strip()
    elif l.startswith('f ') and g and any(g.startswith(p_) for p_ in pre.split(",")):
        c=[t.split('/') for t in l.split()[1:]]
        for j in range(1,len(c)-1): T.append([c[0],c[j],c[j+1]])
V=np.array(V);VN=np.array(VN)
res=300; x0,x1,z0,z1=-5.0,-0.6,-3.8,2.6
Wp=int((x1-x0)*res); Hp=int((z1-z0)*res)
img=np.zeros((Hp,Wp,3),np.float32); cov=np.zeros((Hp,Wp),bool); edges=np.zeros((Hp,Wp),bool)
for t in T:
    P=V[[int(c[0])-1 for c in t]]; N=VN[[int(c[2])-1 for c in t]]
    n=np.cross(P[1]-P[0],P[2]-P[0])
    if np.linalg.norm(n)<1e-12: continue
    n/=np.linalg.norm(n)
    if n[1]<0.5: continue
    pts=np.array([[(p[0]-x0)*res,(z1-p[2])*res] for p in P])
    xmin,ymin=np.floor(pts.min(0)).astype(int); xmax,ymax=np.ceil(pts.max(0)).astype(int)
    xmin=max(xmin,0);ymin=max(ymin,0);xmax=min(xmax,Wp-1);ymax=min(ymax,Hp-1)
    if xmax<xmin or ymax<ymin: continue
    xs,ys=np.meshgrid(np.arange(xmin,xmax+1)+0.5,np.arange(ymin,ymax+1)+0.5)
    a,b,c=pts; d=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
    if abs(d)<1e-12: continue
    w1=((b[1]-c[1])*(xs-c[0])+(c[0]-b[0])*(ys-c[1]))/d; w2=((c[1]-a[1])*(xs-c[0])+(a[0]-c[0])*(ys-c[1]))/d; w3=1-w1-w2
    m=(w1>=-1e-6)&(w2>=-1e-6)&(w3>=-1e-6)
    nn=w1[...,None]*N[0]+w2[...,None]*N[1]+w3[...,None]*N[2]
    nn/=np.linalg.norm(nn,axis=-1,keepdims=True)
    yy=(ys[m]-0.5).astype(int); xx=(xs[m]-0.5).astype(int)
    img[yy,xx]=nn[m]; cov[yy,xx]=True
o=np.zeros((Hp,Wp,3),np.uint8)
o[...,0]=np.clip(128+img[...,0]*1500,0,255); o[...,1]=np.clip(128+img[...,2]*1500,0,255); o[...,2]=128
o[~cov]=0
Image.fromarray(o).save(out)
