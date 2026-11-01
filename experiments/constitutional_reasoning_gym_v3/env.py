"""Optional Gymnasium adapter. Install gymnasium to use this module."""
import gymnasium as gym
from gymnasium import spaces
import string
from .core import TRACKS, World, make_twins, canon

class ConstitutionalReasoningEnv(gym.Env):
    metadata={'render_modes':['ansi']}
    def __init__(self,render_mode=None,gate=False):
        if render_mode not in (None,'ansi'):raise ValueError('render mode')
        self.render_mode=render_mode;self.gate=gate;self.world=None
        self.action_space=spaces.Discrete(3)
        self.observation_space=spaces.Text(min_length=1,max_length=16000,charset=string.printable)
    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed);options=options or {}
        family=int(options.get('family',self.np_random.integers(4)))
        if family not in range(4):raise ValueError('training families only in default Gym adapter')
        track=options.get('track',list(TRACKS)[int(self.np_random.integers(len(TRACKS)))])
        index=int(self.np_random.integers(10000));case_seed=int(self.np_random.integers(2**31))
        twin=make_twins(track,family,index,seed=case_seed)
        self.world=World(twin[int(self.np_random.integers(2))],self.gate)
        return canon(self.world.observation()),{}
    def step(self,action):
        if self.world is None:raise RuntimeError('reset first')
        raw=canon({'choice':int(action)}) if self.action_space.contains(action) else 'invalid'
        ob,reward,terminated,truncated,info=self.world.step(raw)
        return canon(ob),float(reward),bool(terminated and not truncated),bool(truncated),info
    def render(self):return None if self.world is None else canon(self.world.observation())

gym.register('ConstitutionalReasoning-v3',entry_point=__name__+':ConstitutionalReasoningEnv')
