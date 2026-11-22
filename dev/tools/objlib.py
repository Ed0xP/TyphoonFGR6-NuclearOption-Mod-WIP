import numpy as np
def read(path):
    V=[];VT=[];VN=[];groups=[];cur=None
    for line in open(path):
        if line.startswith('v '): V.append([float(x) for x in line.split()[1:4]])
        elif line.startswith('vt '): VT.append([float(x) for x in line.split()[1:3]])
        elif line.startswith('vn '): VN.append([float(x) for x in line.split()[1:4]])
        elif line.startswith('o '): cur={'name':line[2:].strip(),'mtl':None,'f':[]}; groups.append(cur)
        elif line.startswith('usemtl'): cur['mtl']=line.split()[1]
        elif line.startswith('f '):
            cur['f'].append([tuple(int(p) if p else 0 for p in (t.split('/')+['',''])[:3]) for t in line.split()[1:]])
    return np.array(V),np.array(VT),np.array(VN),groups
