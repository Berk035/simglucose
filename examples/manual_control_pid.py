#!/home/berk/VS_Project/simglucose/SIMBG/bin/python

import gym
from numpy import array
import pygame
from gym.envs.registration import register
import sys, keyboard
from pygame.locals import *
import pickle as pkl
import argparse
from simglucose.controller.base import Action
import pandas as pd
import glob


class PIDAction:
    def __init__(self, P=1, I=0, D=0, target=1):
        self.P = P
        self.I = I
        self.D = D
        self.target = target
        self.integrated_state = 0
        self.prev_state = 0

    def policy(self, current_act):
        sample_time = 3

        # BG is the only state for this PID controller
        control = current_act
        control_input = self.P * (control - self.target) + \
            self.I * self.integrated_state + \
            self.D * (control - self.prev_state) / sample_time

        # update the states
        self.prev_state = control
        self.integrated_state += (control - self.target) * sample_time

        # # return the actionq
        action = control_input
        if action <=0:
            #self.target=0
            action=0
        # #print(f"Target: \t {(self.target)} \n Action: \t {(action)}")
    
        #print("Target:%.3f"%self.target)
        return action
        
    def reset(self):
        self.prev_state = 0
        self.integrated_state = 0
        

    def key_callback(self,act):
        if keyboard.is_pressed('up'):
            act +=0.5
            #self.target+=0.5
        if keyboard.is_pressed('down'):
            act -=0.5
        return act


def main():
    n_trajectory = 0

    # Register gym environment. By specifying kwargs,
    # you are able to choose which patient to simulate.
    # patient_name must be 'adolescent#001' to 'adolescent#010',
    # or 'adult#001' to 'adult#010', or 'child#001' to 'child#010'
    register(
        id='simglucose-adult-v1',
        entry_point='simglucose.envs:T1DSimEnv',
        kwargs={'patient_name': 'adult#001'}
    )

    env = gym.make('simglucose-adult-v1')
    observation = env.reset()
    action_ref = 0
    act_obj = PIDAction(P=args.pid_tune[0], 
                        I=args.pid_tune[1], 
                        D=args.pid_tune[2], target=action_ref)

    # 0: read, 1: collect
    if args.collect:

        try:
            with open(args.save_path, 'rb') as handle:
                memory = pkl.load(handle)
        except:
            print('No saved trajectories found')
            pass
        
        memory = {'states': [], 'actions': [], 'rewards': [], 'dones': []}
        for e in range(args.episodes):
            obs_record = []
            rew_record = []
            action_record = []
            dones = []
            timestamps = []

            for t in range(args.timesteps):
                env.render(mode='human')

                if args.collect: action_ref = act_obj.key_callback(action_ref)
                # if keyboard.is_pressed('up'):
                #     action_ref +=0.5
                # if keyboard.is_pressed('down'):
                #     action_ref -=0.5
                action = act_obj.policy(action_ref)

                # Action in the gym environment is a scalar
                # representing the basal insulin, which differs from
                # the regular controller action outside the gym
                # environment (a tuple (basal, bolus)).qq
                # In the perfect situation, the agent should be able
                # to control the glucose only through basal instead
                # of asking patient to take bolus
                
                #print("Action: %.3f"%action)
                #print(f"Observation: {observation}")
                #print(f"Timestep: {t} \n Traj: {n_trajectory}")

                observation, reward, done, info = env.step(action)

                obs_record.append(observation)
                rew_record.append(reward)
                action_record.append(action)
                dones.append(done)
                timestamps.append(t)

                if done or t==(args.timesteps-1):
                    #GAIL uses fixed timestep for all records
                    if t==(args.timesteps-1):
                        memory['states'].append(obs_record)
                        memory['actions'].append(action_record)
                        memory['rewards'].append(rew_record)
                        memory['dones'].append(dones)

                        data_list = {'BG': env.env.BG_hist[:-1], 'CGM': env.env.CGM_hist[:-1],'Insulin': env.env.insulin_hist, 
                                     'Risk': env.env.risk_hist[:-1], 'Return': rew_record, 'Dones': dones}
                    
                        df = pd.DataFrame(data=data_list, index=env.env.time_hist[:-1])
                        df.index.name = 'Date'
                        df.to_csv(args.save_path + "%s.csv"%e)
                    
                    print("Episode finished after {} timesteps".format(t + 1))
                    observation = env.reset()
                    act_obj.reset()
                    env.close()
                    action_ref = 0
                    n_trajectory+=1

        print('trajectories:', n_trajectory)
        print('states collected:', len(memory['states']))

        #fusion_episodes()

    else:
        try:
            with open(args.save_path, 'rb') as handle:
                memory = pkl.load(handle)
        except:
            print('No saved trajectories found')
            pass

        print(f"Length Memory Trajectories: {len(memory['dones'])}")
        #print(f"Length Memory Timesteps: {len(memory['dones'][1])}")
        #print(f"Memory Dones: {memory['dones'][0][-10:]}")

        #bc_train()

def fusion_episodes():
    csv_files = glob.glob('/home/berk/VS_Project/simglucose/examples/trajectories'+'*.{}'.format('csv'))
    df_concat = pd.concat([pd.read_csv(f) for f in csv_files ], ignore_index=True)
    print(df_concat)



def bc_train():

    import torch
    from models.BC_model import NeuralNet
    from models.load_policy import get_batch,load_policy
    import torch.nn as nn
    import torch.optim as optim

    network = NeuralNet(1,128,64,1)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(network.parameters(),0.01,0.9)

    losses = []
    iter = []
    for i in range(20):
        state,action = get_batch()
        for j in range(state.size()[0]):
            network.zero_grad()
            output = network(state[j])
            loss = criterion(output,action[j])
            if i%10==0:
                losses.append(loss)
                iter.append(i)
            loss.backward()
            optimizer.step()
        print(loss)



if __name__ == '__main__':
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--collect', type=bool, default= 1)
    parser.add_argument('--save_path', type=str, default= '/home/berk/VS_Project/simglucose/examples/trajectories/DATA')
    parser.add_argument('--pid_tune', nargs="+", default= [0.3, 0, 1])
    parser.add_argument('--episodes', type=int, default= 2)
    parser.add_argument('--timesteps', type=int, default= 100)

    args = parser.parse_args()
    main()