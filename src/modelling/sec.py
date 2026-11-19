import numpy as np
# NACA 65-010 thickness (x/c %, half thickness % chord) - rounded published ordinates
_X=np.array([0,.5,.75,1.25,2.5,5,7.5,10,15,20,25,30,35,40,45,50,55,60,65,70,75,80,85,90,95,100])/100.
_Y=np.array([0,.772,.932,1.169,1.574,2.177,2.647,3.040,3.666,4.143,4.503,4.760,4.924,5.0,4.963,4.812,4.530,4.146,3.682,3.156,2.584,2.006,1.445,.896,.430,0.0])/100.
def thick(x,chord,te=0.4):
    return np.interp(x,_X,_Y)*chord*(2*0.1/0.1/2)+x*te/2          # half thickness (mm) incl. 0.4 mm TE
def section(k1,k2,chord,kind,n=36):
    """closed perimeter (x axial, y tangential) mm, mid-chord centroid at 0. rotor: slope negative."""
    sgn=-1.0 if kind=='rotor' else 1.0
    ph0,ph1=sgn*np.radians(k1),sgn*np.radians(k2)
    N=400;s=np.linspace(0,chord,N);ph=ph0+(ph1-ph0)*s/chord;ds=s[1]-s[0]
    pm=(ph[:-1]+ph[1:])/2
    cx=np.concatenate([[0],np.cumsum(ds*np.cos(pm))]);cy=np.concatenate([[0],np.cumsum(ds*np.sin(pm))])
    x=0.5*(1-np.cos(np.linspace(0,np.pi,n+1)))
    si=x*chord;px=np.interp(si,s,cx);py=np.interp(si,s,cy);pph=np.interp(si,s,ph)
    yt=thick(x,chord);nx,ny=-np.sin(pph),np.cos(pph)
    up=np.stack([px+nx*yt,py+ny*yt],1);lo=np.stack([px-nx*yt,py-ny*yt],1)
    per=np.vstack([up,lo[-2:0:-1]])
    cen=np.array([np.interp(chord/2,s,cx),np.interp(chord/2,s,cy)])
    return per-cen,np.stack([px,py],1)-cen
