from cmath import cos
from turtle import color
import autograd.numpy as np
from autograd import grad
from time import time
from matplotlib import pyplot as plt


class Vehicle:

    def __init__(self, start, goal, inital_control_input, max_v, max_phi, start_time):
    
        '''
        Start, goal and state contains:
            pos_x : Position in X-coordinate (m)
            pos_y : Position in Y-coordinate (m)
            theta : Orientation Angle (radians)
            delta : Steering Angle (radians)
        These are the states of the Vehicle
        '''
        x_start=start[0]
        y_start=start[1]
        theta_start=start[2]*np.pi/180
        delta_start=start[3]*np.pi/180
        
        self.start = [x_start, y_start, theta_start, delta_start]

        x_goal=goal[0]
        y_goal=goal[1]
        theta_goal=goal[2]*np.pi/180
        delta_goal=goal[3]*np.pi/180
        self.goal = [x_goal, y_goal, theta_goal, delta_goal]

        self.state = [x_start, y_start, theta_start, delta_start]
        self.virtual_state = [x_start, y_start, theta_start, delta_start]
        '''
        # Control Input = [v, phi]
        # v : Velocity (m/s)
        # phi : Steering Rate (rad/s) 
        '''
        initial_v = inital_control_input[0]
        inital_phi = inital_control_input[1]*np.pi/180
        self.control_input = [initial_v, inital_phi]

        # Length of the Vehicle
        self.length = 0.1
        self.size = 1

        # Obstacles
        self.offset = 7
        self.dynamic_offset = 10
        self.obstacles = [[0,10,0.5],[10,0,0.5],[10,20,0.5],[20,10,0.5],[10,10,0.5]]
        self.dynamic_obstacles=[[5,0,0.25,90*np.pi/180,0.5],[0,5,0.25,0*np.pi/180,0.5],[0,15,0.25,0*np.pi/180,0.5],[15,20,0.4,-90*np.pi/180,0.5]]

        # self.dynamic_obstacles=[[18.5,21.5,0.5,230*np.pi/180,0.5],[21.5,18.5,0.5,220*np.pi/180,0.5]]
        # Start Time of the Vehicle
        # self.start_time = start_time
        self.time = start_time
        self.prediction_horizon = 10
        self.control_horizon = 1.0
        self.sampling_time = 0.2
        self.max_v = max_v
        self.max_phi = max_phi

        # History of the Vehicle
        self.state_history = []
        self.state_history.append([x_start, y_start, theta_start, delta_start])
        self.time_history = []
        self.time_history.append(start_time)
        self.control_input_history = []
        self.control_input_history.append([initial_v, inital_phi])

    
    def bicycle_model(self,v,phi, update = False):
        '''
        STATE MODEL
        This funciton gives the next state based on control inputs
        '''
        if update:
            state = self.state
        else:
            state = self.virtual_state
        
        # v and phi are given by the MPC
        pos_x = state[0]
        pos_y = state[1]
        theta = state[2] 
        delta = state[3]

        # print("V=",v)
        # print("theta=",theta)
        x_dot = v*np.cos(theta)
        y_dot = v*np.sin(theta)
        theta_dot = (v*np.tan(delta))/self.length
        delta_dot = phi

        state[0] = state[0] + x_dot*self.sampling_time
        state[1] = state[1] + y_dot*self.sampling_time
        state[2] = state[2] + theta_dot*self.sampling_time
        state[3] = state[3] + delta_dot*self.sampling_time 

        # Updating the States based on Kinematic Bicycle Model
        if update:
            self.state = state
            x=self.state[0]
            y=self.state[1]
            theta=self.state[2]
            delta=self.state[3]
            self.state_history.append([x, y, theta, delta])
            self.control_input_history.append([v,phi])
            self.time += self.sampling_time
            self.time_history.append(self.time)
            
        else:
            self.virtual_state = state   
        

    def goal_reach_cost(self):
        # State cost to Goal
        cost_xy = (self.virtual_state[0]-self.goal[0])**2 + (self.virtual_state[1]-self.goal[1])**2
        cost_theta = (self.virtual_state[2]-self.goal[2])**2
        cost_delta = (self.virtual_state[3]-self.goal[3])**2

        # Weights
        W1 = 1
        W2 = 1
        W3 = 0

        goal_reach_cost = W1*cost_xy + W2*cost_theta + W3*cost_delta

        return goal_reach_cost

    
    def smoothness_cost(self, virtual_input):
        cost_v = ((self.control_input[0] - virtual_input[0])/self.sampling_time)
        cost_phi = ((self.control_input[1] - virtual_input[1])/self.sampling_time)

        # Weights
        W1 = 1
        W2 = 1

        smoothness_cost = W1*cost_v + W2*cost_phi 

        return smoothness_cost

    def constraint_cost(self, virtual_input):
        lamda_v = max(0,virtual_input[0] - self.max_v) + max(0,-virtual_input[0] - self.max_v)
        lamda_phi = max(0,virtual_input[1] - self.max_phi) + max(0,-virtual_input[1] - self.max_phi)
        lamda_ws = 0 #Both x and y workspace constraints
        
        lambda_safety = 0
        for i in range(len(self.obstacles)):
            obs_x = self.obstacles[i][0]
            obs_y = self.obstacles[i][1]
            # dist = (((self.virtual_state[0]-obs_x)**2 + (self.virtual_state[1]-obs_y)**2)**0.5)
            dist = (((self.state[0]-obs_x)**2 + (self.state[1]-obs_y)**2)**0.5)
            if dist < self.offset:
                dist_virtual = (((self.virtual_state[0]-obs_x)**2 + (self.virtual_state[1]-obs_y)**2)**0.5)
                lambda_safety += max(0,-dist_virtual + self.obstacles[i][2] + self.size/2)

        for i in range(len(self.dynamic_obstacles)):
            obs_x = self.dynamic_obstacles[i][0]
            obs_y = self.dynamic_obstacles[i][1]
            dist = (((self.state[0]-obs_x)**2 + (self.state[1]-obs_y)**2)**0.5)
            if dist < self.dynamic_offset:
                dist_virtual = (((self.virtual_state[0]-obs_x)**2 + (self.virtual_state[1]-obs_y)**2)**0.5)
                lambda_safety += max(0,-dist_virtual + self.dynamic_obstacles[i][4] + self.size/2)
                   
        # Weights
        W1 = 1
        W2 = 1
        W3 = 1
        W4 = 5

        constraint_cost = W1*lamda_v + W2*lamda_phi + W3*lamda_ws + W4*lambda_safety
        
        return constraint_cost

    def dynamic_obstacle_cost(self):
        dynamic_obstacle_cost = 0
        for i in range(len(self.dynamic_obstacles)):
            obs_x = self.dynamic_obstacles[i][0]
            obs_y = self.dynamic_obstacles[i][1]

            dist = (((self.state[0]-obs_x)**2 + (self.state[1]-obs_y)**2)**0.5)
            if dist < self.dynamic_offset:
                dist_virtual = (((self.virtual_state[0]-obs_x)**2 + (self.virtual_state[1]-obs_y)**2)**0.5)
                dynamic_obstacle_cost += 1/dist_virtual

        return dynamic_obstacle_cost

    def static_obstacle_cost(self):
        static_obstacle_cost = 0
        for i in range(len(self.obstacles)):
            obs_x = self.obstacles[i][0]
            obs_y = self.obstacles[i][1]

            dist = (((self.state[0]-obs_x)**2 + (self.state[1]-obs_y)**2)**0.5)
            if dist < self.offset:
                dist_virtual = (((self.virtual_state[0]-obs_x)**2 + (self.virtual_state[1]-obs_y)**2)**0.5)
                static_obstacle_cost += 1/dist_virtual               
    
        return static_obstacle_cost       

    def total_cost(self, virtual_input):
        total_cost = 0
        x=self.state[0]
        y=self.state[1]
        theta=self.state[2]
        delta=self.state[3]
    
        self.virtual_state = [x,y,theta,delta]
        
        # Calculating cost across the prediction horizon
        for i in range(self.prediction_horizon):
            W1=1
            W2=1
            W3=10
            W4=1000
            W5=1000
            if i == self.prediction_horizon-1:
                terminal_cost = self.goal_reach_cost()*W1*5
            else:
                terminal_cost = 0
            total_cost += self.goal_reach_cost()*W1 + self.smoothness_cost(virtual_input)*W2 + self.constraint_cost(virtual_input)*W3 + self.static_obstacle_cost()*W4 + self.dynamic_obstacle_cost()*W5 +terminal_cost
            self.bicycle_model(virtual_input[0],virtual_input[1])
            # print("Me here")
        
        return total_cost

    def optimizer(self, iteration = 25, learning_rate = 0.005, decay = 0.9, eps = 1e-8):
        
        gradient = grad(self.total_cost)
        mean_square_gradient = np.asarray([0.0, 0.0])
        virtual_input = self.control_input

        for _ in range(iteration):
            cost_gradient = np.asarray(gradient(virtual_input))
            mean_square_gradient = (0.9*mean_square_gradient) + 0.1 * (cost_gradient**2)
            virtual_input = virtual_input - (learning_rate/((mean_square_gradient)**0.5+eps))*cost_gradient
        self.control_input = virtual_input
    

    def vehicle_plot(self, board):
        # if(self.time!=self.time_history[1]):
        #     vehicle.remove()
        #     arrow.remove()

        vehicle = plt.Circle((self.state[0], self.state[1]),0.5, facecolor='#3498db', edgecolor='black')
        board.add_patch(vehicle)
        arrow = plt.arrow(self.state[0], self.state[1], np.cos(self.state[2]), np.sin(self.state[2]), width = 0.1, facecolor='#3498db', edgecolor='black')
        plt.plot(np.array(self.state_history)[:,0], np.array(self.state_history)[:,1], color='#3498db')

        plt.plot(self.start[0],self.start[1], marker='*',  markersize=20, color='#1e8449', markeredgecolor='black')
        plt.plot(self.goal[0],self.goal[1], marker='*',  markersize=20, color='#1e8449', markeredgecolor='black')

        return vehicle, arrow
    
    def obstacle_plot(self, board):
        # if(self.time!=self.time_history[1]):
        #     dynamic_obstacle.remove()
        dynamic_obstacles_plot=[]
        for i in range(len(self.obstacles)):
            obstacle = plt.Circle((self.obstacles[i][0], self.obstacles[i][1]),self.obstacles[i][2], facecolor='#c0392b', edgecolor='black')
            board.add_patch(obstacle)
        
        for i in range(len(self.dynamic_obstacles)):
            dynamic_obstacle = plt.Circle((self.dynamic_obstacles[i][0], self.dynamic_obstacles[i][1]),self.dynamic_obstacles[i][4], facecolor='#8e44ad', edgecolor='black')
            board.add_patch(dynamic_obstacle)
            dynamic_obstacles_plot.append(dynamic_obstacle)

        return dynamic_obstacles_plot


if __name__== '__main__':

    Start_A = [0.0, 0.0, 45.0, 0.0]
    Goal_A = [20.0, 20.0, 45.0, 0.0]

    Start_B = [20.0, 20.0, 225.0, 0.0]
    Goal_B = [5.0, 5.0, 225.0, 0.0]


    inital_control_input_A=[2.0,0.0]
    inital_control_input_B=[2.0,0.0]
    start_time = 0 #time()

    VehicleA = Vehicle(Start_A,Goal_A, inital_control_input_A, 10.0, 10,start_time)

    VehicleB = Vehicle(Start_B,Goal_B, inital_control_input_B, 10.0, 10,start_time)
    
    fig = plt.figure(1)
    board = plt.axes(xlim=(-5,50),ylim=(-5,25))

    while(((VehicleA.state[0] - VehicleA.goal[0])**2 > 2) or ((VehicleA.state[1] - VehicleA.goal[1])**2 > 2) or ((VehicleB.state[0] - VehicleB.goal[0])**2 > 2) or ((VehicleB.state[1] - VehicleB.goal[1])**2 > 2)):        

        VehicleA.optimizer()
        VehicleA.bicycle_model(VehicleA.control_input[0], VehicleA.control_input[1], True)

        for i in range(len(VehicleA.dynamic_obstacles)):
            VehicleA.dynamic_obstacles[i][0] += VehicleA.dynamic_obstacles[i][2]*np.cos(VehicleA.dynamic_obstacles[i][3])
            VehicleA.dynamic_obstacles[i][1] += VehicleA.dynamic_obstacles[i][2]*np.sin(VehicleA.dynamic_obstacles[i][3])
       
        vehicle_a, arrow_a = VehicleA.vehicle_plot(board)
        dynamic_obstacle =VehicleA.obstacle_plot(board)
        # vehicle_a = plt.Circle((VehicleA.state[0], VehicleA.state[1]),0.5, facecolor='#3498db', edgecolor='black')
        # board.add_patch(vehicle_a)
        # arrowa = plt.arrow(VehicleA.state[0], VehicleA.state[1], np.cos(VehicleA.state[2]), np.sin(VehicleA.state[2]), width = 0.1, facecolor='#3498db', edgecolor='black')
        # plt.plot(np.array(VehicleA.state_history)[:,0], np.array(VehicleA.state_history)[:,1], color='#3498db')

        # plt.plot(VehicleA.start[0],VehicleA.start[1], marker='*',  markersize=20, color='#1e8449', markeredgecolor='black')
        # plt.plot(VehicleA.goal[0],VehicleA.goal[1], marker='*',  markersize=20, color='#1e8449', markeredgecolor='black')

        VehicleB.optimizer()
        VehicleB.bicycle_model(VehicleB.control_input[0], VehicleB.control_input[1], True)
        vehicle_b, arrow_b = VehicleB.vehicle_plot(board)

        # vehicle_b = plt.Circle((VehicleB.state[0], VehicleB.state[1]),0.5, facecolor='#3498db', edgecolor='black')
        # board.add_patch(vehicle_b)
        # arrowb = plt.arrow(VehicleB.state[0], VehicleB.state[1], np.cos(VehicleB.state[2]), np.sin(VehicleB.state[2]), width = 0.1, facecolor='#3498db', edgecolor='black')
        # plt.plot(np.array(VehicleB.state_history)[:,0], np.array(VehicleB.state_history)[:,1], color='#3498db')

        # for i in range(len(VehicleA.obstacles)):
        #     obstacle = plt.Circle((VehicleA.obstacles[i][0], VehicleA.obstacles[i][1]),VehicleA.obstacles[i][2], facecolor='#c0392b', edgecolor='black')
        #     board.add_patch(obstacle)
        
        # for i in range(len(VehicleA.dynamic_obstacles)):
        #     dynamic_obstacle = plt.Circle((VehicleA.dynamic_obstacles[i][0], VehicleA.dynamic_obstacles[i][1]),VehicleA.dynamic_obstacles[i][4], facecolor='#8e44ad', edgecolor='black')
        #     board.add_patch(dynamic_obstacle)
              
        plt.draw()
        plt.pause(VehicleA.sampling_time*0.1)
        
        for i in dynamic_obstacle:
            i.remove()

        vehicle_a.remove()
        arrow_a.remove()
        
        vehicle_b.remove()
        arrow_b.remove()
        # vehicle_b.remove()
        # arrowb.remove()
        # print("Time=",VehicleA.time)
       

    control_input_history = np.array(VehicleA.control_input_history)
    state_history = np.array(VehicleA.state_history)
    time_history = np.array(VehicleA.time_history)
    residual_state_history = np.array(VehicleA.state_history)-np.array(VehicleA.goal)
           
    plt.figure(2)
    plt.title('Velocity')
    plt.plot(time_history,control_input_history[:,0])
    
    plt.figure(3)
    plt.title('Steering Rate (Degree/s)')
    plt.plot(time_history,control_input_history[:,1]*180/np.pi)

    plt.figure(4)
    plt.title('X Position')
    plt.plot(time_history,state_history[:,0])

    plt.figure(5)
    plt.title('Y Position')
    plt.plot(time_history,state_history[:,1])

    plt.figure(6)
    plt.title('Theta (Degree)')
    plt.plot(time_history,state_history[:,2]*180/np.pi)

    plt.figure(7)
    plt.title('Delta (Degree)')
    plt.plot(time_history,state_history[:,3]*180/np.pi)

    plt.figure(8)
    plt.title('XY Position Residual')
    plt.plot(time_history,(residual_state_history[:,0]**2+residual_state_history[:,1]**2)**0.5)

    plt.figure(9)
    plt.title('Theta Residual(Degree)')
    plt.plot(time_history,residual_state_history[:,2]*180/np.pi)

    plt.figure(10)
    plt.title('Delta Residual (Degree)')
    plt.plot(time_history,residual_state_history[:,3]*180/np.pi)

    plt.show()











