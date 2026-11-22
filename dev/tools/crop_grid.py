import sys
from PIL import Image, ImageDraw
B=Image.open(sys.argv[1]).convert('RGB')
x0,y0,x1,y1,S=map(int,sys.argv[2:7]); out=sys.argv[7]
im=B.crop((x0,y0,x1,y1)).resize(((x1-x0)*S,(y1-y0)*S),Image.BICUBIC)
dr=ImageDraw.Draw(im)
step=20 if S>=3 else 50
for x in range((x0//step+1)*step,x1,step):
    X=(x-x0)*S; big=x%100==0
    dr.line([X,0,X,12 if big else 6],fill=(255,255,0));
    if big: dr.text((X+2,12),str(x),fill=(255,255,0))
for y in range((y0//step+1)*step,y1,step):
    Y=(y-y0)*S; big=y%100==0
    dr.line([0,Y,12 if big else 6,Y],fill=(255,255,0))
    if big: dr.text((14,Y-5),str(y),fill=(255,255,0))
im.save(out)
