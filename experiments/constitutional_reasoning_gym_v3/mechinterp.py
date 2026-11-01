"""Residual capture, grouped probes and reversible interventions. No model loaded here."""
from __future__ import annotations
from contextlib import contextmanager
import numpy as np


def split_guard(train_groups,test_groups):
    if set(train_groups)&set(test_groups):raise ValueError('motif leakage between probe train and test')
    if not train_groups or not test_groups:raise ValueError('empty split')


def ridge_probe(train_x,train_y,test_x,test_y,train_groups,test_groups,alpha=1.,seed=41):
    split_guard(train_groups,test_groups)
    x=np.asarray(train_x,dtype=float);z=np.asarray(test_x,dtype=float)
    y=np.asarray(train_y,dtype=float);t=np.asarray(test_y,dtype=float)
    if x.ndim!=2 or z.ndim!=2 or x.shape[1]!=z.shape[1] or len(y)!=len(x) or len(t)!=len(z):raise ValueError('probe shape')
    if len(train_groups)!=len(x) or len(test_groups)!=len(z):raise ValueError('group shape')
    if not np.isfinite(x).all() or not np.isfinite(z).all():raise ValueError('nonfinite activation')
    if set(y)!= {0.,1.} or not set(t)<= {0.,1.}:raise ValueError('binary labels required')
    mu=x.mean(0);sd=x.std(0);sd[sd<1e-8]=1
    xx=(x-mu)/sd;zz=(z-mu)/sd
    xx=np.c_[xx,np.ones(len(xx))];zz=np.c_[zz,np.ones(len(zz))]
    def fit(labels):
        w=np.linalg.solve(xx.T@xx+alpha*np.eye(xx.shape[1]),xx.T@(2*labels-1))
        return float(((zz@w>=0)==t).mean()),w
    acc,w=fit(y);shuffled,_=fit(np.random.default_rng(seed).permutation(y))
    return {'accuracy':acc,'label_shuffle_accuracy':shuffled,'weights':w.tolist(),
            'train_mean':mu.tolist(),'train_sd':sd.tolist(),'causal_evidence':False,
            'train_groups':len(set(train_groups)),'test_groups':len(set(test_groups))}


def equal_norm_random(vector,seed=41):
    v=np.asarray(vector,dtype=float)
    if v.ndim!=1 or not np.isfinite(v).all():raise ValueError('invalid direction')
    r=np.random.default_rng(seed).normal(size=v.shape)
    return r/max(np.linalg.norm(r),1e-12)*np.linalg.norm(v)


@contextmanager
def capture_residuals(modules,positions):
    """modules maps stable layer names to torch modules; positions is one token index per row."""
    import torch
    saved={};handles=[]
    def make_hook(name):
        def hook(module,args,output):
            tensor=output[0] if isinstance(output,tuple) else output
            if tensor.ndim!=3 or len(positions)!=tensor.shape[0]:raise ValueError('capture shape')
            selected=[]
            for i,pos in enumerate(positions):
                if not -tensor.shape[1]<=pos<tensor.shape[1]:raise ValueError('anchor outside sequence')
                selected.append(tensor[i,pos].detach().float().cpu())
            saved[name]=torch.stack(selected)
        return hook
    try:
        for name,module in modules.items():handles.append(module.register_forward_hook(make_hook(name)))
        yield saved
    finally:
        for h in handles:h.remove()


@contextmanager
def intervene(module,direction,coefficient=1.,position=-1):
    """Inject at a preregistered token anchor. The caller supplies matched random controls."""
    import torch
    def hook(mod,args,output):
        x=output[0] if isinstance(output,tuple) else output
        if x.ndim!=3 or not -x.shape[1]<=position<x.shape[1]:raise ValueError('intervention shape')
        d=torch.as_tensor(direction,device=x.device,dtype=x.dtype)
        if d.shape != x.shape[-1:]:raise ValueError('direction dimension')
        patched=x.clone();patched[:,position,:]+=float(coefficient)*d
        return (patched,*output[1:]) if isinstance(output,tuple) else patched
    handle=module.register_forward_hook(hook)
    try:yield
    finally:handle.remove()
