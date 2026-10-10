"""Video sintetico con verita' a terra: tastiera parziale (prima nota bianca = C3), mani finte, note premute."""
import cv2, numpy as np, json, sys
from keyboard_grid import e_nero, _OFFSET_NERI
def genera(path, prima=48, n_bianchi=22, fps=30, secondi=8, W=1600, H=600, sk=0.0, premute=None, seed=1, mano=True):
    rng = np.random.default_rng(seed)
    bianchi=[]; n=prima
    while len(bianchi)<n_bianchi:
        if not e_nero(n): bianchi.append(n)
        n+=1
    x0, y0, ww, hk, hb = 100, 200, 60, 220, 130
    premute = premute or [(60,1.0,2.0),(64,2.5,3.5),(67,2.5,3.5),(72,4.0,4.2),(49,1.0,3.0),(61,5.0,6.5),(48,6.0,7.5),(59,6.2,7.0)]
    n_fr=int(fps*secondi)
    base=np.full((H,W,3),70,np.uint8)
    cv2.rectangle(base,(x0-40,y0-40),(x0+ww*n_bianchi+40,y0),(25,25,25),-1)     # fallboard scuro
    pos={}
    for i,b in enumerate(bianchi):
        xl=x0+i*ww; cv2.rectangle(base,(xl,y0),(xl+ww-2,y0+hk),(225,225,225),-1); pos[b]=(xl,xl+ww-2,False)
    for i,b in enumerate(bianchi):
        nn=b+1
        if e_nero(nn) and i+1<len(bianchi):
            c=x0+(i+1)*ww+_OFFSET_NERI[nn%12]*ww; hw=0.3*ww
            cv2.rectangle(base,(int(c-hw),y0),(int(c+hw),y0+hb),(20,20,20),-1); pos[nn]=(int(c-hw),int(c+hw),True)
    M=np.float32([[1,sk,-sk*300],[0,1,0]])
    out=cv2.VideoWriter(path,cv2.VideoWriter_fourcc(*'mp4v'),fps,(W,H))
    for f in range(n_fr):
        t=f/fps; im=base.copy()
        for nota,a,b in premute:
            if a<=t<b:
                xl,xr,ne=pos[nota]
                if ne: im[y0+10:y0+hb-10,xl+2:xr-2]=np.clip(im[y0+10:y0+hb-10,xl+2:xr-2].astype(int)+70,0,255)
                else: im[y0+hb+15:y0+hk-10,xl+4:xr-4]=np.clip(im[y0+hb+15:y0+hk-10,xl+4:xr-4].astype(int)-60,0,255)
        cx=int(x0+ww*(4+ 10*(0.5+0.5*np.sin(t*0.9))))                   # mano finta che passa sopra senza premere
        ov=im.copy(); cv2.ellipse(ov,(cx,y0+40),(150,60),0,0,360,(110,120,140),-1); im=cv2.addWeighted(ov,0.8,im,0.2,0) if mano else im
        im=np.clip(im.astype(np.float32)+rng.normal(0,2,im.shape),0,255).astype(np.uint8)
        if sk: im=cv2.warpAffine(im,M,(W,H),borderValue=(70,70,70))
        out.write(im)
    out.release()
    quad=[(x0-40,y0-30),(x0+ww*n_bianchi+40,y0-30),(x0+ww*n_bianchi+40,y0+hk),(x0-40,y0+hk)]
    if sk: quad=[(x+sk*(300-y)* -1 if False else x - sk*(y-300),y) for x,y in quad]
    return dict(premute=premute,quad=quad,n_fr=n_fr,pos=pos,bianchi=bianchi)
if __name__=="__main__":
    r=genera(sys.argv[1], sk=float(sys.argv[2]) if len(sys.argv)>2 else 0.0)
    print(json.dumps({"quad":r["quad"],"n_fr":r["n_fr"]}))
