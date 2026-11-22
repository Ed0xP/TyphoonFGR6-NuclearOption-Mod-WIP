import sys, re, collections
box=[float(x) for x in sys.argv[2].split(',')]; rx=re.compile(sys.argv[3] if len(sys.argv)>3 else '^(cockpit|canopy_i)')
V=[];g=None;F=collections.defaultdict(list)
for l in open(sys.argv[1], errors='ignore'):
    if l.startswith('v '): V.append(tuple(float(x) for x in l.split()[1:4]))
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f ') and g and rx.search(g):
        F[g].append([int(t.split('/')[0])-1 for t in l.split()[1:]])
def inside(p): return box[0]<=p[0]<=box[1] and box[2]<=p[1]<=box[3] and box[4]<=p[2]<=box[5]
for g,fs in F.items():
    key={}; par={}
    def find(a):
        while par[a]!=a: par[a]=par[par[a]]; a=par[a]
        return a
    for f in fs:
        ks=[]
        for i in f:
            k=tuple(round(c,4) for c in V[i]);
            if k not in par: par[k]=k
            ks.append(k)
        for k in ks[1:]:
            a,b=find(ks[0]),find(k)
            if a!=b: par[a]=b
    comp=collections.defaultdict(list)
    for f in fs:
        comp[find(tuple(round(c,4) for c in V[f[0]]))].append(f)
    for c,cf in comp.items():
        pts=[V[i] for f in cf for i in f]
        ctr=[sum(p[k] for p in pts)/len(pts) for k in range(3)]
        if not inside(ctr): continue
        mn=[min(p[k] for p in pts) for k in range(3)]; mx=[max(p[k] for p in pts) for k in range(3)]
        print(g, len(cf), 'faces  min', [round(x,3) for x in mn], 'max', [round(x,3) for x in mx])
