#!/usr/bin/env python3
"""Deterministic NumPy CNN primitives for the offline architecture editor."""
from __future__ import annotations
import hashlib, importlib.util
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("galaxy_prepare",ROOT/"prepare-data.py"); assert spec and spec.loader
prepare=importlib.util.module_from_spec(spec); spec.loader.exec_module(prepare)
SEED=20261008; IMAGE_SIZE=32; EPOCHS=420; LEARNING_RATE=.025; DROPOUT_RATE=.20; BN_MOMENTUM=.10; BN_EPSILON=1e-5
TAILS=(("r",),("bn","r"),("r","bn"),("d","r"),("r","d"),("bn","d","r"),("bn","r","d"),("d","bn","r"),("d","r","bn"),("r","bn","d"),("r","d","bn"))
@dataclass(frozen=True)
class Architecture: id:str; depth:int; tail:tuple[str,...]
def architectures(): return tuple(Architecture(f"d{d}-{'-'.join(t)}",d,t) for d in (1,2) for t in TAILS)
def architecture_by_id(id):
 for a in architectures():
  if a.id==id:return a
 raise ValueError(f"unsupported architecture: {id}")
def stable_rng(*parts): return np.random.default_rng(int.from_bytes(hashlib.sha256("\0".join(map(str,(SEED,*parts))).encode()).digest()[:8],"little"))
def load_image(filename):
 path=prepare.ASSETS/filename
 if hashlib.sha256(path.read_bytes()).hexdigest()!=prepare.EXPECTED_SOURCE_SHA256[filename]:raise RuntimeError(f"admission hash mismatch: {filename}")
 with Image.open(path) as source:
  image=source.convert("L"); w,h=image.size; side=int(min(w,h)*.75); image=image.crop(((w-side)//2,(h-side)//2,(w+side)//2,(h+side)//2)).resize((IMAGE_SIZE,IMAGE_SIZE),Image.Resampling.LANCZOS)
 values=np.asarray(image,dtype=np.float64)/255.; return (values-values.mean())/(values.std()+1e-8)
def conv_forward(x,w,b):
 padded=np.pad(x,((0,0),(0,0),(1,1),(1,1))); windows=np.lib.stride_tricks.sliding_window_view(padded,(3,3),axis=(2,3)); return np.einsum("nchwkl,fckl->nfhw",windows,w,optimize=True)+b[None,:,None,None],(windows,w,x.shape)
def conv_backward(g,cache):
 windows,w,shape=cache; dw=np.einsum("nfhw,nchwkl->fckl",g,windows,optimize=True); db=g.sum((0,2,3)); n,c,h,ww=shape; padded=np.zeros((n,c,h+2,ww+2))
 for r in range(3):
  for col in range(3): padded[:,:,r:r+h,col:col+ww]+=np.einsum("nfhw,fc->nchw",g,w[:,:,r,col],optimize=True)
 return padded[:,:,1:-1,1:-1],dw,db
def bn_forward(x,gamma,beta,rmean,rvar,training,update):
 if training:
  mean=x.mean((0,2,3)); var=x.var((0,2,3))
  if update:rmean[:]=(1-BN_MOMENTUM)*rmean+BN_MOMENTUM*mean; rvar[:]=(1-BN_MOMENTUM)*rvar+BN_MOMENTUM*var
 else: mean,var=rmean,rvar
 inv=1/np.sqrt(var+BN_EPSILON); norm=(x-mean[None,:,None,None])*inv[None,:,None,None]; out=gamma[None,:,None,None]*norm+beta[None,:,None,None]
 return out,(norm,inv,gamma,x.shape) if training else None
def bn_backward(grad,cache):
 norm,inv,gamma,shape=cache; count=shape[0]*shape[2]*shape[3]; db=grad.sum((0,2,3)); dg=(grad*norm).sum((0,2,3)); scaled=grad*gamma[None,:,None,None]; dx=(scaled*count-scaled.sum((0,2,3),keepdims=True)-norm*(scaled*norm).sum((0,2,3),keepdims=True))*(inv[None,:,None,None]/count); return dx,dg,db
class TinyCNN:
 def __init__(self,architecture):
  self.architecture=architecture; self.params={}; self.buffers={}; inc=1
  for i in range(architecture.depth): self.params[f"w{i}"]=stable_rng("initial",f"w{i}").normal(0,np.sqrt(2/(inc*9)),(4,inc,3,3)); self.params[f"b{i}"]=np.zeros(4); inc=4
  self.params["head_w"]=stable_rng("initial","head_w").normal(0,np.sqrt(2/inc),(inc,3)); self.params["head_b"]=np.zeros(3)
  if "bn" in architecture.tail:self.params.update(bn_gamma=np.ones(4),bn_beta=np.zeros(4)); self.buffers.update(bn_mean=np.zeros(4),bn_var=np.ones(4))
 @property
 def parameter_count(self):return sum(v.size for v in self.params.values())
 def forward(self,x,training=False,dropout_rng=None,update_bn=True):
  a=x; caches=[]
  for i in range(self.architecture.depth):
   a,cc=conv_forward(a,self.params[f"w{i}"],self.params[f"b{i}"]); caches.append((f"conv{i}",cc)); tokens=("r",) if i<self.architecture.depth-1 else self.architecture.tail
   for token in tokens:
    if token=="r":caches.append(("relu",a)); a=np.maximum(a,0)
    elif token=="bn":a,c=bn_forward(a,self.params["bn_gamma"],self.params["bn_beta"],self.buffers["bn_mean"],self.buffers["bn_var"],training,update_bn); caches.append(("bn",c))
    elif token=="d":
     mask=None
     if training:
      if dropout_rng is None:raise ValueError("training Dropout needs RNG")
      mask=(dropout_rng.random(a.shape)>=DROPOUT_RATE)/(1-DROPOUT_RATE); a*=mask
     caches.append(("dropout",mask))
    else: raise AssertionError(token)
  pool=a.mean((2,3)); logits=pool@self.params["head_w"]+self.params["head_b"]; return logits,(caches,a.shape,pool) if training else None
 def gradients(self,x,y,rng,update_bn=True):
  logits,cache=self.forward(x,True,rng,update_bn); layers,ashape,pool=cache; p=np.exp(logits-logits.max(1,keepdims=True));p/=p.sum(1,keepdims=True); loss=float(-np.log(p[np.arange(len(y)),y]+1e-12).mean()); p[np.arange(len(y)),y]-=1;p/=len(y); grads={"head_w":pool.T@p,"head_b":p.sum(0)}; g=np.broadcast_to((p@self.params["head_w"].T)[:,:,None,None]/(ashape[2]*ashape[3]),ashape).copy()
  for name,c in reversed(layers):
   if name=="relu":g*=c>0
   elif name=="dropout":
    if c is not None:g*=c
   elif name=="bn":g,dg,db=bn_backward(g,c);grads["bn_gamma"]=dg;grads["bn_beta"]=db
   else:
    i=int(name[4:]);g,dw,db=conv_backward(g,c);grads[f"w{i}"]=dw;grads[f"b{i}"]=db
  return loss,grads
 def predict(self,x):return self.forward(x,False)[0].argmax(1)
def train(model,images,targets,label_key):
 first={k:np.zeros_like(v) for k,v in model.params.items()}; second={k:np.zeros_like(v) for k,v in model.params.items()}; rng=stable_rng("dropout");losses=[]
 for step in range(1,EPOCHS+1):
  loss,grads=model.gradients(images,targets,rng)
  if step in (1,EPOCHS):losses.append(loss)
  for k,v in model.params.items(): first[k]=.9*first[k]+.1*grads[k];second[k]=.999*second[k]+.001*grads[k]**2; v-=LEARNING_RATE*(first[k]/(1-.9**step))/(np.sqrt(second[k]/(1-.999**step))+1e-8)
 return losses
