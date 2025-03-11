import numpy as np
import matplotlib.pyplot as plt
from env import GameState
from ddpg import *
from collections import deque
import torch.nn as nn
import os, shutil
import argparse
from datetime import datetime
from utils import str2bool,evaluate_policy

'''Hyperparameter Setting'''
parser = argparse.ArgumentParser()
parser.add_argument('--dvc', type=str, default='cpu', help='running device: cuda or cpu')
parser.add_argument('--EnvIdex', type=int, default=0, help='PV1, Lch_Cv2, Humanv4, HCv4, BWv3, BWHv3')
parser.add_argument('--write', type=str2bool, default=False, help='Use SummaryWriter to record the training')
parser.add_argument('--render', type=str2bool, default=False, help='Render or Not')
parser.add_argument('--Loadmodel', type=str2bool, default=False, help='Load pretrained model or Not')
parser.add_argument('--ModelIdex', type=int, default=100, help='which model to load')

parser.add_argument('--seed', type=int, default=0, help='random seed')
parser.add_argument('--Max_train_steps', type=int, default=200000, help='Max training steps') #aslinya 5e6
parser.add_argument('--save_interval', type=int, default=10000, help='Model saving interval, in steps.') #aslinya 1e5
parser.add_argument('--eval_interval', type=int, default=5000, help='Model evaluating interval, in steps.') #aslinya 2e3

parser.add_argument('--gamma', type=float, default=0.99, help='Discounted Factor')
parser.add_argument('--net_width', type=int, default=400, help='Hidden net width, s_dim-400-300-a_dim')
parser.add_argument('--a_lr', type=float, default=1e-3, help='Learning rate of actor')
parser.add_argument('--c_lr', type=float, default=1e-3, help='Learning rate of critic')
parser.add_argument('--batch_size', type=int, default=128, help='batch_size of training')
parser.add_argument('--random_steps', type=int, default=60000, help='random steps before trianing')
parser.add_argument('--noise', type=float, default=0.5, help='exploring noise')
opt = parser.parse_args()
opt.dvc = torch.device(opt.dvc) # from str to torch.device

def main():
    #EnvName = ['Pendulum-v1','LunarLanderContinuous-v2','Humanoid-v4','HalfCheetah-v4','BipedalWalker-v3','BipedalWalkerHardcore-v3']
    #BrifEnvName = ['PV1', 'LLdV2', 'Humanv4', 'HCv4','BWv3', 'BWHv3']
    BrifEnvName = ['6G', 'LLdV2', 'Humanv4', 'HCv4','BWv3', 'BWHv3']
    # Build Env
    env = GameState(5,3)
    eval_env = GameState(5,3)
    opt.state_dim = env.observation_space
    opt.action_dim = env.action_space
    opt.max_action = env.p_max   #remark: action space【-max,max】
    #print(f'Env:{EnvName[opt.EnvIdex]}  state_dim:{opt.state_dim}  action_dim:{opt.action_dim}  '
    #      f'max_a:{opt.max_action}  min_a:{env.action_space.low[0]}  max_e_steps:{env._max_episode_steps}')

    # Seed Everything
    env_seed = opt.seed
    torch.manual_seed(opt.seed)
    torch.cuda.manual_seed(opt.seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    print("Random Seed: {}".format(opt.seed))

    # Build SummaryWriter to record training curves
    if opt.write:
        from torch.utils.tensorboard import SummaryWriter
        timenow = str(datetime.now())[0:-10]
        timenow = ' ' + timenow[0:13] + '_' + timenow[-2::]
        writepath = 'runs/{}'.format(BrifEnvName[opt.EnvIdex]) + timenow
        if os.path.exists(writepath): shutil.rmtree(writepath)
        writer = SummaryWriter(log_dir=writepath)


    # Build DRL model
    if not os.path.exists('model'): os.mkdir('model')
    agent = DDPG_agent(**vars(opt)) # var: transfer argparse to dictionary
    if opt.Loadmodel: agent.load(BrifEnvName[opt.EnvIdex], opt.ModelIdex)

    if opt.render:
        
        while True:
            channel_gain=env.generate_channel_gain()
            state_eval1,inf=env.ini(channel_gain)
            state_eval1 = np.array(state_eval1, dtype=np.float32)
            score = evaluate_policy(channel_gain,state_eval1,env, agent, turns=1)
            
            print('EnvName:', BrifEnvName[opt.EnvIdex], 'score:', score, )
    else:
        total_steps = 0
        while total_steps < opt.Max_train_steps:
            channel_gain=env.generate_channel_gain()
            s,info= env.ini(channel_gain, seed=env_seed)  # Do not use opt.seed directly, or it can overfit to opt.seed
            env_seed += 1
            done = False
            #print("ini aku di loop utama")
            langkah = 0
            '''Interact & trian'''
            while not done:  
                #print(total_steps, opt.random_steps)
                langkah +=1
                if total_steps < opt.random_steps: a = env.p
                else: 
                    a = agent.select_action(s, deterministic=False)
                s_next, r, dw, tr, info = env.step(a,channel_gain) # dw: dead&win; tr: truncated
                if langkah == 150 :
                    tr= True
                done = (dw or tr)

                agent.replay_buffer.add(np.array(s, dtype=np.float32), a, r, np.array(s_next, dtype=np.float32), dw)
                s = s_next
                total_steps += 1

                '''train'''
                if total_steps >= opt.random_steps:
                    agent.train()

                '''record & log'''
                if total_steps % opt.eval_interval == 0:
                    state_eval,inf=eval_env.ini(channel_gain)
                    state_eval = np.array(state_eval, dtype=np.float32)
                    ep_r,avg_ee = evaluate_policy(channel_gain,state_eval,eval_env, agent, turns=3)
                    if opt.write: 
                        writer.add_scalar('ep_r', ep_r, global_step=total_steps)
                        writer.add_scalar('avg_ee', avg_ee, global_step=total_steps)
                    print(f'EnvName:{BrifEnvName[opt.EnvIdex]}, Steps: {int(total_steps/1000)}k, Episode Reward:{ep_r}')

                '''save model'''
                if total_steps % opt.save_interval == 0:
                    agent.save(BrifEnvName[opt.EnvIdex], int(total_steps/1000))
        print("The end")


if __name__ == '__main__':
    main()

