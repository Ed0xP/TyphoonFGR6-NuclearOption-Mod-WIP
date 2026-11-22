import sys, re, collections
box=[float(x) for x in sys.argv[2].split(',')]; rx=re.compile(sys.argv[3])
V=[];g=None;F=[]
for l in open(sys.argv[1], errors='ignore'):
    if l.startswith('v '): V.append(tuple(float(x) for x in l.split()[1:4]))
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f ') and g and rx.search(g):
        F.append((g,[int(t.split('/')[0])-1 for t in l.split()[1:]]))
par={}
def find(a):
    while par[a]!=a: par[a]=par[par[a]]; a=par[a]
    return a
K=lambda i: tuple(round(c,4) for c in V[i])
for g,f in F:
    ks=[K(i) for i in f]
    for k in ks: par.setdefault(k,k)
    for k in ks[1:]:
        a,b=find(ks[0]),find(k)
        if a!=b: par[a]=b
comp=collections.defaultdict(list)
for g,f in F: comp[find(K(f[0]))].append((g,f))
for c,cf in comp.items():
    pts=[V[i] for g,f in cf for i in f]
    mn=[min(p[k] for p in pts) for k in range(3)]; mx=[max(p[k] for p in pts) for k in range(3)]
    ctr=[(mn[k]+mx[k])/2 for k in range(3)]
    if not (box[0]<=ctr[0]<=box[1] and box[2]<=ctr[1]<=box[3] and box[4]<=ctr[2]<=box[5]): continue
    gs=collections.Counter(g for g,f in cf)
    print(len(cf),'faces min',[round(x,3) for x in mn],'max',[round(x,3) for x in mx],dict(gs))
