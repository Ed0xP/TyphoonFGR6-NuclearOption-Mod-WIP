import sys, math
grp=sys.argv[3]; H=[float(x) for x in sys.argv[4].split(',')]; a=math.radians(float(sys.argv[5])); c,s=math.cos(a),math.sin(a)
L=open(sys.argv[1], errors='ignore').read().split('\n')
g=None; vi=set(); ni=set()
for l in L:
    if l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f ') and g==grp:
        for t in l.split()[1:]:
            p=t.split('/'); vi.add(int(p[0]))
            if len(p)>2 and p[2]: ni.add(int(p[2]))
nv=nn=0
for k,l in enumerate(L):
    if l.startswith('v '):
        nv+=1
        if nv in vi:
            x,y,z=[float(q) for q in l.split()[1:4]]; y-=H[1]; z-=H[2]
            L[k]='v %.5f %.5f %.5f'%(x, H[1]+y*c-z*s, H[2]+y*s+z*c)
    elif l.startswith('vn '):
        nn+=1
        if nn in ni:
            x,y,z=[float(q) for q in l.split()[1:4]]
            L[k]='vn %.4f %.4f %.4f'%(x, y*c-z*s, y*s+z*c)
open(sys.argv[2],'w').write('\n'.join(L))
print('posed', grp, len(vi), 'vertices')
