import numpy as np, sys
def load(path, groups=None):
    V=[];VN=[];g=None;G={}
    for l in open(path,errors='ignore'):
        if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
        elif l.startswith('vn '): VN.append([float(x) for x in l.split()[1:4]])
        elif l[:2] in('o ','g '): g=l.split()[1]
        elif l.startswith('f ') and g and (groups is None or g in groups):
            c=[t.split('/') for t in l.split()[1:4]]
            G.setdefault(g,[]).append([[int(t[0])-1 for t in c],[int(t[2])-1 if len(t)>2 and t[2] else -1 for t in c]])
    return np.array(V),np.array(VN),{k:np.array(v) for k,v in G.items()}
