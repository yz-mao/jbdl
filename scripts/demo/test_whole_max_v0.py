import os
import re
from jax.interpreters.xla import jaxpr_replicas
from numpy.core.shape_base import block
import numpy as np
import math
from jbdl.rbdl.kinematics import calc_pos_vel_point_to_base
from jbdl.rbdl.kinematics import calc_whole_body_com
from jbdl.rbdl.tools import plot_model, plot_contact_force, plot_com_inertia
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.axes3d import Axes3D
from jbdl.rbdl.dynamics.state_fun_ode import state_fun_ode, dynamics_fun, events_fun_core
import matplotlib
from jbdl.rbdl.utils import ModelWrapper
from jbdl.rbdl.contact import detect_contact, detect_contact_core
from jbdl.rbdl.contact import impulsive_dynamics, impulsive_dynamics_core
from jbdl.rbdl.dynamics import composite_rigid_body_algorithm_core, forward_dynamics_core, inverse_dynamics_core
from jbdl.rbdl.kinematics import *
from jbdl.rbdl.kinematics import calc_body_to_base_coordinates_core
import time
from jbdl.rbdl.utils import xyz2int
# matplotlib.use('TkAgg')

CURRENT_PATH = os.path.dirname(os.path.realpath(__file__))
SCRIPTS_PATH = os.path.dirname(CURRENT_PATH)
MODEL_DATA_PATH = os.path.join(SCRIPTS_PATH, "model_data") 


def jit_compiled(model):
    NC = int(model["NC"])
    NB = int(model["NB"])
    nf = int(model["nf"])
    x_tree = model["x_tree"]
    contactpoint = model["contactpoint"],
    idcontact = tuple(model["idcontact"])
    parent = tuple(model["parent"])
    jtype = tuple(model["jtype"])
    jaxis = xyz2int(model["jaxis"])
    contactpoint = model["contactpoint"]
    contact_cond = model["contact_cond"]
    contact_pos_lb = contact_cond["contact_pos_lb"]
    contact_vel_lb = contact_cond["contact_vel_lb"]
    contact_vel_ub = contact_cond["contact_vel_ub"]
    a_grav = model["a_grav"]
    flag_contact_list = [(0, 0, 0, 0), (1, 1, 1, 1), (2, 2, 2, 2)]
    I = model["I"]
    q = np.array([
        0, 0, 0.27, 0, 0, 0, # base
        0, 0.5, -0.8,  # fr
        0, 0.5, -0.8,  # fl
        0, 0.5, -0.8,  # br
        0, 0.5, -0.8]) # bl
    qdot = np.ones(NB)
    qddot = np.ones(NB)
    tau = np.concatenate([np.zeros(6), np.ones(NB-6)])
    start_time = time.time()
    for body_id, point_pos in zip(idcontact, contactpoint):
        print(body_id, point_pos)
        J = calc_point_jacobian_core(x_tree, parent, jtype, jaxis, NB, body_id, q, point_pos)
        J.block_until_ready()
        acc = calc_point_acceleration_core(x_tree, parent, jtype, jaxis, body_id, q, qdot, qddot, point_pos)
        acc.block_until_ready()
        end_pos = calc_body_to_base_coordinates_core(x_tree, parent, jtype, jaxis, body_id, q, point_pos)
        end_pos.block_until_ready()
    duarion = time.time() - start_time
    print("Jit compiled time for %s is %s." % ("Contact Point Functions", duarion))

    start_time = time.time()
    qddot = forward_dynamics_core(x_tree, I, parent, jtype, jaxis, NB, q, qdot, tau, a_grav)
    H =  composite_rigid_body_algorithm_core(x_tree, I, parent, jtype, jaxis, NB, q)
    C =  inverse_dynamics_core(x_tree, I, parent, jtype, jaxis, NB, q, qdot, np.zeros_like(q), a_grav)
    flag_contact_calc = detect_contact_core(x_tree, q, qdot, contactpoint, contact_pos_lb, contact_vel_lb, contact_vel_ub,  idcontact, parent, jtype, jaxis, NC)
    qddot.block_until_ready()
    H.block_until_ready()
    C.block_until_ready()
    flag_contact_calc.block_until_ready()
    duarion = time.time() - start_time
    print("Jit compiled time for %s is %s." % ("Basic Functions", duarion))

    # for flag_contact in flag_contact_list:
        # print("Jit compiled for %s ..." % str(flag_contact))
        # start_time = time.time()
        # rankJc = int(np.sum( [1 for item in flag_contact if item != 0]) * model["nf"])

        # xdot, fqp, H = DynamicsFunCore(x_tree, I, q, qdot, contactpoint, tau, a_grav, idcontact, flag_contact, parent, jtype, jaxis, NB, NC, nf, rankJc)
        # value = EventsFunCore(x_tree, q, contactpoint, idcontact, flag_contact, parent, jtype, jaxis, NC)
        # flag_contact_calc = detect_contact_core(x_tree, q, qdot, contactpoint, contact_pos_lb, contact_vel_lb, contact_vel_ub,  idcontact, parent, jtype, jaxis, NC)
        # qdot_impulse = impulsive_dynamics_core(x_tree, q, qdot, contactpoint, H, idcontact, flag_contact, parent, jtype, jaxis, NB, NC, nf, rankJc)

        # fqp.block_until_ready()
        # xdot.block_until_ready()
        # value.block_until_ready()
        # flag_contact_calc.block_until_ready()
        

        # flag_contact = detect_contact(model, q, qdot)
        # print(flag_contact)
        # qdot_impulse.block_until_ready()
        # duarion = time.time() - start_time
        # print("Jit compiled time for %s is %s." % (str(flag_contact), duarion))



    

         


if __name__ == "__main__":
    mdlw = ModelWrapper()
    mdlw.load(os.path.join(MODEL_DATA_PATH, 'whole_max_v1.json'))
    model = mdlw.model
    jit_compiled(model)

    idcontact = model["idcontact"]
    contactpoint = model["contactpoint"]
    q0 = np.array([0, 0, 0.5, 0.0, 0, 0,
        0, 0.5, -0.8,  # fr
        0, 0.5, -0.8,  # fl
        0, 0.5, -0.8,  # br
        0, 0.5, -0.8]) # bl

    q0 = q0.reshape(-1, 1)
    qd0 = np.zeros((18, 1))
    x0 = np.vstack([q0, qd0])
    u0 = np.zeros((12, 1))

    xk = x0
    u = u0
    kp = 200
    kd = 3
    kp = 50
    kd = 1
    xksv = []
    T = 2e-3
    xksv = []


    

    plt.ion()
    plt.figure()
    fig = plt.gcf()
    ax = Axes3D(fig)  
    ax = plt.gca()
    ax.clear()
    plot_model(model, q0, ax)
    ax.view_init(elev=0,azim=-90)
    ax.set_xlabel('X')
    ax.set_xlim(-0.3, -0.3+0.6)
    ax.set_ylabel('Y')
    ax.set_ylim(-0.15, -0.15+0.6)
    ax.set_zlabel('Z')
    ax.set_zlim(-0.1, -0.1+0.6)
    plt.pause(0.001)
    plt.show()

    for i in range(1000):
        print(i)
        u = kp * (q0[6:18] - xk[6:18]) + kd * (qd0[6:18] - xk[24:36])
        xk, contact_force = state_fun_ode(model, xk.flatten(), u.flatten(), T)
        xk = xk.reshape(-1, 1)
        xksv.append(xk)
        ax.clear()
        plot_model(model, xk[0:18], ax)
        plot_contact_force(model, xk[0:18], contact_force["fc"], contact_force["fcqp"], contact_force["fcpd"], 'fcqp', ax)
        ax.view_init(elev=0,azim=-90)
        ax.set_xlabel('X')
        ax.set_xlim(-0.3, -0.3+0.6)
        ax.set_ylabel('Y')
        ax.set_ylim(-0.15, -0.15+0.6)
        ax.set_zlabel('Z')
        ax.set_zlim(-0.1, -0.1+0.6)
        ax.set_title('Frame')
        plt.pause(0.001)
        plt.show()


    plt.ioff()