import numpy as np
import matplotlib.pyplot as plt
from env2 import GameState
from ddpg import *
from collections import deque
import torch.nn as nn
import os, shutil
import argparse
from datetime import datetime
from utils2 import str2bool,evaluate_policy

'''Hyperparameter Setting'''
parser = argparse.ArgumentParser()
parser.add_argument('--dvc', type=str, default='cuda', help='running device: cuda or cpu')
parser.add_argument('--EnvIdex', type=int, default=0, help='PV1, Lch_Cv2, Humanv4, HCv4, BWv3, BWHv3')
parser.add_argument('--write', type=str2bool, default=False, help='Use SummaryWriter to record the training')
parser.add_argument('--render', type=str2bool, default=False, help='Render or Not')
parser.add_argument('--Loadmodel', type=str2bool, default=False, help='Load pretrained model or Not')
parser.add_argument('--ModelIdex', type=int, default=100, help='which model to load')

parser.add_argument('--seed', type=int, default=0, help='random seed')
parser.add_argument('--Max_train_steps', type=int, default = 30000, help='Max training steps') #aslinya 5e6
parser.add_argument('--save_interval', type=int, default=2500, help='Model saving interval, in steps.') #aslinya 1e5
parser.add_argument('--eval_interval', type=int, default=1000, help='Model evaluating interval, in steps.') #aslinya 2e3

parser.add_argument('--gamma', type=float, default=0.99, help='Discounted Factor')
parser.add_argument('--net_width', type=int, default=1024, help='Hidden net width, s_dim-400-300-a_dim')
parser.add_argument('--a_lr', type=float, default=2e-3, help='Learning rate of actor') # 2e-3
parser.add_argument('--c_lr', type=float, default=1e-3, help='Learning rate of critic') # 1e-3
parser.add_argument('--batch_size', type=int, default=128, help='batch_size of training')
parser.add_argument('--random_steps', type=int, default=5000, help='random steps before trianing')
parser.add_argument('--noise', type=float, default=0.1, help='exploring noise') #aslinya 0.1
opt = parser.parse_args()
opt.dvc = torch.device(opt.dvc) # from str to torch.device

def compute_cdf(data):
    x = np.sort(data)
    y = np.arange(1, len(x)+1) / len(x)
    return x, y

def main():
    EnvName = ['Power Allocation','LunarLanderContinuous-v2','Humanoid-v4','HalfCheetah-v4','BipedalWalker-v3','BipedalWalkerHardcore-v3']
    #BrifEnvName = ['PV1', 'LLdV2', 'Humanv4', 'HCv4','BWv3', 'BWHv3']
    BrifEnvName = ['6G', 'LLdV2', 'Humanv4', 'HCv4','BWv3', 'BWHv3']
    
    # Build Env
    env = GameState(20,5)
    eval_env = GameState(20,5)
    opt.state_dim = env.observation_space
    opt.action_dim = env.action_space
    opt.max_action = env.p_max   #remark: action space【-max,max】
    #print(f'Env:{EnvName[opt.EnvIdex]}  state_dim:{opt.state_dim}  action_dim:{opt.action_dim}  '
    #      f'max_a:{opt.max_action}  min_a:{env.action_space.low[0]}  max_e_steps:{env._max_episode_steps}')

    #variable tambahan 
    iterasi = 200
    total_episode = -(-opt.Max_train_steps//iterasi)
    sepertiga_eps=total_episode//3
    EE_DDPG=[] #buat cdf
    EE_RAND=[] #buat_cdf
    RATE_SUCCESS=[]
    RATE_SUCCESS_RAND=[]

    
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
    #dummy_s = torch.zeros((1, opt.state_dim), device=opt.dvc)
    #print("Initial actor a:", agent.actor(dummy_s).cpu().detach().numpy())
    print("state_dim, action_dim =", opt.state_dim, opt.action_dim)
    #dummy = torch.zeros(1, opt.state_dim).to(opt.dvc)
    #print("actor out shape:", agent.actor(dummy).shape)
    if opt.Loadmodel: agent.load(BrifEnvName[opt.EnvIdex], opt.ModelIdex)

    if opt.render:
        
        while True:
            loc = env.generate_positions()
            channel_gain=env.generate_channel_gain(loc)
            state_eval1,inf=env.reset(channel_gain)
            state_eval1 = np.array(state_eval1, dtype=np.float32)
            result = evaluate_policy(channel_gain,state_eval,eval_env, agent, turns=3)
            
            #print('EnvName:', BrifEnvName[opt.EnvIdex], 'score:', score, )
    else:
        total_steps = 0
        lr_steps = 0
        while total_steps < opt.Max_train_steps: # ini loop episode. Jadi total episode adalah Max_train_steps/200
            lr_steps+=1
            if lr_steps==sepertiga_eps :
                opt.a_lr=0.3 * opt.a_lr
                opt.c_lr=0.3 * opt.c_lr
                lr_steps=0
            loc= env.generate_positions() #lokasi untuk s_t
            channel_gain=env.generate_channel_gain(loc) #channel gain untuk s_t
            s,info= env.reset(channel_gain, seed=env_seed)  # Do not use opt.seed directly, or it can overfit to opt.seed
            env_seed += 1
            done = False
            langkah = 0
            '''Interact & trian'''
            while not done:  
                langkah +=1
                if total_steps <= opt.random_steps: #aslinya < aja, ide pengubahan ini tuh supaya selec action di train dulu.
                    a = env.sample_valid_power()
                    #a = env.p
                else: 
                    a = agent.select_action(s, deterministic=False)
                next_loc= env.generate_positions() #lokasi untuk s_t
                next_channel_gain=env.generate_channel_gain(next_loc) #channel gain untuk s_t
                s_next, r, dw, tr, info= env.step(a,channel_gain,next_channel_gain) # dw: dead&win; tr: truncated
                writer.add_scalar("Reward iterasi", r, total_steps)

                loc= env.generate_positions()
                channel_gain=env.generate_channel_gain(loc)
                if langkah == iterasi :
                    tr= True
                  
                    
                done = (dw or tr)

                agent.replay_buffer.add(np.array(s, dtype=np.float32), a, r, np.array(s_next, dtype=np.float32), dw)
                s = s_next
                channel_gain=next_channel_gain
                total_steps += 1

                '''train'''
                if total_steps >= opt.random_steps:
                    a_loss, c_loss = agent.train()
                    writer.add_scalar("Loss/Actor", a_loss, total_steps)
                    writer.add_scalar("Loss/Critic", c_loss, total_steps)
                    # print(f'EnvName:{BrifEnvName[opt.EnvIdex]}, Steps: {int(total_steps/1000)}k, actor_loss:{a_loss}')
                    # print(f'EnvName:{BrifEnvName[opt.EnvIdex]}, Steps: {int(total_steps/1000)}k, c_loss:{c_loss}')
        
                '''record & log'''
                if total_steps % opt.eval_interval == 0:
                    state_eval,inf=eval_env.reset(channel_gain)
                    state_eval = np.array(state_eval, dtype=np.float32)
                    result = evaluate_policy(channel_gain,state_eval,eval_env, agent, turns=1)
                    EE_DDPG.append(result['avg_EE'])
                    EE_RAND.append(result['avg_EE_rand'])
                    RATE_SUCCESS.append(result['pct_data_ok'])
                    RATE_SUCCESS_RAND.append(result['pct_data_ok_rand'])
                    
                    if opt.write: 
                        writer.add_scalar('ep_r', result['avg_score'], global_step=total_steps)
                        writer.add_scalar('energi efisiensi', result['avg_EE'], global_step=total_steps)
                        writer.add_scalar('energi efisiensi random', result['avg_EE_rand'], global_step=total_steps)
                        writer.add_scalar('total daya', result['avg_power'], global_step=total_steps)
                        writer.add_scalar('constraint daya', result['pct_power_ok'], global_step=total_steps)
                        writer.add_scalar('constraint data rate', result['pct_data_ok'], global_step=total_steps)
                        writer.add_scalar('constraint daya random', result['pct_power_ok_rand'], global_step=total_steps)
                        writer.add_scalar('constraint data rate random', result['pct_data_ok_rand'], global_step=total_steps)
                        writer.add_scalar('data_rate_1', result['data_rate_1'], global_step=total_steps)
                        writer.add_scalar('data_rate_7', result['data_rate_7'], global_step=total_steps)
                        writer.add_scalar('data_rate_8', result['data_rate_8'], global_step=total_steps)
                        writer.add_scalar('data_rate_11', result['data_rate_11'], global_step=total_steps)
                        writer.add_scalar('data_rate_15', result['data_rate_15'], global_step=total_steps)
                        writer.add_scalar('data_rate_20', result['data_rate_20'], global_step=total_steps)
                        writer.add_scalar('data_rate_2', result['data_rate_2'], global_step=total_steps)
                        writer.add_scalar('data_rate_3', result['data_rate_3'], global_step=total_steps)
                        writer.add_scalar('data_rate_4', result['data_rate_4'], global_step=total_steps)
                        writer.add_scalar('data_rate_5', result['data_rate_5'], global_step=total_steps)
                        writer.add_scalar('data_rate_6', result['data_rate_6'], global_step=total_steps)
                        writer.add_scalar('data_rate_9', result['data_rate_9'], global_step=total_steps)
                        writer.add_scalar('data_rate_10', result['data_rate_10'], global_step=total_steps)
                        writer.add_scalar('data_rate_12', result['data_rate_12'], global_step=total_steps)
                        writer.add_scalar('data_rate_13', result['data_rate_13'], global_step=total_steps)
                        writer.add_scalar('data_rate_14', result['data_rate_14'], global_step=total_steps)
                        writer.add_scalar('data_rate_16', result['data_rate_16'], global_step=total_steps)
                        writer.add_scalar('data_rate_17', result['data_rate_17'], global_step=total_steps)
                        writer.add_scalar('data_rate_18', result['data_rate_18'], global_step=total_steps)
                        writer.add_scalar('data_rate_19', result['data_rate_19'], global_step=total_steps)
                        writer.add_scalar('data_rate_pass', result['data_rate_pass'], global_step=total_steps)
                        writer.add_scalar('data_rate_random_pass', result['data_rate_rand_pass'], global_step=total_steps)
                        writer.add_scalar('jumlah data rate', result['data_rate_total'], global_step=total_steps)
                        writer.add_scalar('jumlah data rate random', result['data_rate_total_rand'], global_step=total_steps)
                        
                        

                    print(f'EnvName:{BrifEnvName[opt.EnvIdex]}, Steps: {int(total_steps/1000)}k')


                '''save model'''
                if total_steps % opt.save_interval == 0:
                    agent.save(BrifEnvName[opt.EnvIdex], int(total_steps/1000))
                s = s_next
                channel_gain=next_channel_gain

        x_ddpg, y_ddpg = compute_cdf(EE_DDPG)
        x_rand, y_rand = compute_cdf(EE_RAND)
        x_rate, y_rate = compute_cdf(RATE_SUCCESS)
        x_rate_rand, y_rate_rand = compute_cdf(RATE_SUCCESS_RAND)
        
        # PLOT CDF EE
        fig, ax = plt.subplots()
        ax.plot(x_ddpg, y_ddpg, label='DDPG')
        ax.plot(x_rand, y_rand, label='Random')
        ax.set_xlabel('Energi Efisiensi')
        ax.set_ylabel('CDF')
        ax.set_title('CDF Energi Efisiensi')
        ax.legend()
        ax.grid(True)

        #     log figure
        if opt.write :
            writer.add_figure('CDF Energi Efisiensi', fig, global_step=total_steps)
            plt.close(fig)

        # 2) Plot CDF Data Rate Success
        fig2, ax2 = plt.subplots()
        ax2.plot(x_rate, y_rate, label='DDPG')
        ax2.plot(x_rate_rand, y_rate_rand, label='Random')
        ax2.set_xlabel('Persentase UE ≥ R_th (%)')
        ax2.set_ylabel('CDF')
        ax2.set_title('CDF Success Rate Data Rate')
        ax2.legend()
        ax2.grid(True)

        if opt.write:
            writer.add_figure('CDF Data Rate Success', fig2, global_step=total_steps)
            plt.close(fig2)
        print("The end")

#%load_ext tensorboard
#%tensorboard --logdir runs
if __name__ == '__main__':
    main()

