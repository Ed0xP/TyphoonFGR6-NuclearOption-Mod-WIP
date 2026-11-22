import sys, numpy as np, math
obj, ck = sys.argv[1], sys.argv[2]
V=[];G={};cur=None
for l in open(obj):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): cur=l.split()[1]
    elif l.startswith('f ') and cur in ('cockpit_keys','cockpit_panel'):
        G.setdefault(cur,[]).append([int(c.split('/')[0]) for c in l.split()[1:]])
V=np.array(V)
def unit(v): return v/np.linalg.norm(v)
eye=np.array([0,1.16,6.5])
SCR={}
for l in open(ck):
    t=l.split()
    if len(t)==14 and t[0]=='screen': SCR[t[1]]=np.array([float(x) for x in t[2:]]).reshape(4,3)
key={};par={}
def kid(i): return key.setdefault(tuple(np.round(V[i-1],4)),len(key))
def find(a):
    while par.setdefault(a,a)!=a:
        par[a]=par[par[a]]; a=par[a]
    return a
for f in G['cockpit_keys']:
    ks=[kid(c) for c in f]
    for a in ks[1:]: par[find(a)]=find(ks[0])
comp={}
for f in G['cockpit_keys']:
    comp.setdefault(find(kid(f[0])),set()).update(c-1 for c in f)
comps=[V[sorted(v)] for v in comp.values()]
print(len(comps),'key components')
PT=[V[[c-1 for c in f]] for f in G['cockpit_panel']]
for nm in ('mfd_L','mfd_C','mfd_R'):
    q=SCR[nm]; o=q.mean(0)
    u,v=unit(q[1]-q[0]),unit(q[0]-q[3]); n=unit(np.cross(u,v))
    if n@(eye-o)<0: n=-n
    hw,hh=np.linalg.norm(q[1]-q[0])/2,np.linalg.norm(q[0]-q[3])/2
    print(nm,'half size mm %.1f x %.1f'%(hw*1000,hh*1000),'n',np.round(n,3),'u',np.round(u,3),'v',np.round(v,3), 'planarity', np.round([(p-o)@n*1000 for p in q],2))
    rows=[]
    for kc in comps:
        c=kc.mean(0)
        cu,cv,cw=(c-o)@u,(c-o)@v,(c-o)@n
        if abs(cw)<0.03 and abs(cu)<hw+0.05 and abs(cv)<hh+0.06:
            pu,pv,pw=(kc-o)@u,(kc-o)@v,(kc-o)@n
            rows.append((cu*1000,cv*1000,pu.min()*1000,pu.max()*1000,pv.min()*1000,pv.max()*1000,pw.min()*1000,pw.max()*1000,len(kc)))
    rows.sort(key=lambda r:(round(r[1]/12),r[0]))
    for r in rows: print('   key c(%.1f,%.1f) u[%.1f,%.1f] v[%.1f,%.1f] w[%.1f,%.1f] nv %d'%r)
    ws=[]
    for tri in PT:
        c=tri.mean(0); cu,cv,cw=(c-o)@u,(c-o)@v,(c-o)@n
        if abs(cu)<hw+0.03 and abs(cv)<hh+0.03 and abs(cw)<0.02:
            tn=unit(np.cross(tri[1]-tri[0],tri[2]-tri[0]))
            if abs(tn@n)>0.98: ws.append(((tri-o)@n).mean()*1000)
    ws=np.array(ws); print('   panel faces parallel within unit: n=%d, w values (mm) uniq:'%len(ws), np.unique(np.round(ws,1))[:20])
