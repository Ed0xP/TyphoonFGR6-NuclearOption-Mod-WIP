import sys
items=[]; plates=[]; scale=1.0
for ln,l in enumerate(open(sys.argv[1]),1):
    t=l.split('#')[0].split()
    if not t: continue
    k=t[0]
    xy=lambda s: tuple(float(v) for v in s.split(','))
    if k=='xform': scale=float(t[5])*1000
    elif k=='plate': plates.append([xy(s) for s in t[1:]])
    elif k=='toggle': x,y=xy(t[1]); r=7.5/scale; items.append((ln,'toggle',x-r,x+r,y-r,y+r))
    elif k=='knob': x,y=xy(t[1]); r=(float(t[2])/2+2.5)/scale; items.append((ln,'knob',x-r,x+r,y-r,y+r))
    elif k=='rocker': x,y=xy(t[1]); items.append((ln,'rocker',x-9/scale,x+9/scale,y-12/scale,y+12/scale))
    elif k=='key': x,y=xy(t[1]); w=float(t[2])/2/scale+1; h=float(t[3])/2/scale+1; items.append((ln,'key',x-w,x+w,y-h,y+h))
    elif k in('guard','hazard'): x0,y0=xy(t[1]); x1,y1=xy(t[2]); items.append((ln,k,min(x0,x1),max(x0,x1),min(y0,y1),max(y0,y1)))
    elif k=='label':
        x,y=xy(t[1]); txt=t[2].split('|'); cap=float(t[3]) if len(t)>3 else 2.0
        L=max(len(s) for s in txt)*cap*0.78/scale/2+0.5; T=len(txt)*cap*1.45/scale/2+0.3
        items.append((ln,'label '+t[2],x-T,x+T,y-L,y+L))
bad=0
for i,a in enumerate(items):
    for b in items[i+1:]:
        if a[1]=='hazard' and b[1] in('toggle',) or b[1]=='hazard' and a[1]=='toggle': continue
        if a[1]=='guard' or b[1]=='guard':
            if not (a[1].startswith('label') or b[1].startswith('label')): continue
        if a[2]<b[3] and b[2]<a[3] and a[4]<b[5] and b[4]<a[5]:
            print('overlap: line %d %s  x line %d %s'%(a[0],a[1],b[0],b[1])); bad+=1
print(len(items),'items,',bad,'overlaps')
