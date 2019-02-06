#!/usr/bin/env python

"""
ROS node used to allow the user to control the baxter via mirroring.
"""

import argparse
import sys

import struct
import rospy

import baxter_interface
from BaxterGBI_pbr.msg import *
from baxter_interface import CHECK_VERSION, Limb
from BaxterGBI_pbr.srv import *
from BaxterGBI_pbr import ik_tracking, ReturnValue

import tf

from geometry_msgs.msg import (
    PoseStamped,
    Pose,
    Point,
    Quaternion,
)
from std_msgs.msg import Header

from baxter_core_msgs.srv import (
    SolvePositionIK,
    SolvePositionIKRequest,
)


"""
Global variables for initial posture.
"""
global start, init_pose_hand, init_orient_hand, calibrated, init_pose_baxter, init_orient_baxter
start = 0
calibrated = False
init_pose_hand = []
init_orient_hand = []
init_pose_baxter = []
init_orient_baxter = []


def calibrate(req):
    """
    Service used to initialize the initial posture of the baxter end effector.
    
    
    @type req.limb: string
    @param req.limb: "left" or "right" arm.
    @type data.position: float[]
    @param data.position: position we want to achieve.
    @type data.quaternion: float[]
    @param data.quaternion: orientation we want to achieve (Quaternion).
    """
    
    global arm, limb, calibrated, init_pose_hand, init_orient_hand, init_pose_baxter, init_orient_baxter
        
    if req.limb == "left" or req.limb == "right":
        limb = req.limb
        arm = Limb(limb)  
        
        
        #Acquire initial position/orientation of the human hand (The first value published)
        init_pose_hand.append(req.position[0])
        init_pose_hand.append(req.position[1])
        init_pose_hand.append(req.position[2])
        init_orient_hand.append(req.quaternion[0])
        init_orient_hand.append(req.quaternion[1])
        init_orient_hand.append(req.quaternion[2])
        init_orient_hand.append(req.quaternion[3])
        
        
        resp = arm.endpoint_pose()
        #Acquire initial position/orientation of the baxter
        init_pose_baxter = resp['position']
        init_orient_baxter = resp['orientation']
        #rospy.loginfo("Pose: "+ str(init_pose_baxter))
        #rospy.loginfo("Orient: "+str(init_orient_baxter))
        rospy.loginfo("Calibration completed!")
        calibrated = True
        return 0    
    else:
        rospy.logerr("Invalid limb value")
        return 1
        
   
def mirror_callback(data):
    """
    Callback function associated with the topic 'mirror_end_effector'.
    Whenever a data is written in the topic, this function is called and obtain from ik_tracking function the joints values to assign and
    move the end effector to the goal.
    
    @type data.position: float[]
    @param data.position: position we want to achieve.
    @type data.quaternion: float[]
    @param data.quaternion: orientation we want to achieve (Quaternion).
    """
    
    
    global arm, start, limb, init_pose_hand, init_orient_hand, init_pose_baxter, init_orient_baxter
    
    #If you start the mirroring you will read the messages in the topic
    if start == 1:            
        #Evaluate the relative movement of the hand
        pos = []
        pos.append(init_pose_baxter[0] + (data.position[0] - init_pose_hand[0]))
        pos.append(init_pose_baxter[1] + (data.position[1] - init_pose_hand[1]))
        pos.append(init_pose_baxter[2] + (data.position[2] - init_pose_hand[2]))
        
        
        orient = []
        
        #quaternion = tf.transformations.quaternion_from_euler(-3.127816, 0.000416, -1.900463)
        #type(pose) = geometry_msgs.msg.Pose
        #orient.append(quaternion[0])
        #orient.append(quaternion[1])
        #orient.append(quaternion[2])
        #orient.append(quaternion[3])
        
        orient.append(init_orient_baxter[0] + (data.quaternion[0] - init_orient_hand[0]))
        orient.append(init_orient_baxter[1] + (data.quaternion[1] - init_orient_hand[1]))
        orient.append(init_orient_baxter[2] + (data.quaternion[2] - init_orient_hand[2]))
        orient.append(init_orient_baxter[3] + (data.quaternion[3] - init_orient_hand[3]))
        
        rospy.loginfo("Start q: "+str(arm.joint_angles()))
        
        
        try:
            joint_solution = ik_tracking("left",pos,orient)   #joint_solution is an object type ReturnValue
            
            if joint_solution.isError == 1:
                rospy.logwarn("Cannot reach the goal")
            else:
                # set arm joint positions to solution
                arm.move_to_joint_positions(joint_solution.limb_joints)
        except rospy.ServiceException, e:
            rospy.logerr("Error during Inverse Kinematic problem")
       
  
def enableMirroring(req):
    """
    Service to start and stop the mirroring.
    
    @type req.mode: uint8
    @param req.mode: 1 to start and 0 to stop.
    """
    
    global start, calibrated
    if req.mode == 1: #Start Mirroring
        if start == 0:
            if calibrated == False:
                rospy.logwarn("You need to calibrate first!")
                return 1
            else:
                start = 1
                rospy.loginfo("Mirroring Started!")
                return 0
        elif start == 1:
            rospy.logwarn("Mirroring has already started!")
            return 1
    elif req.mode == 0: #Stop Mirroring
        if start == 1:
            start = 0
            calibrated = False
            rospy.loginfo("Mirroring Stopped!")
            return 0
        elif start == 0:
            rospy.logwarn("Mirroring has already stopped!")
            return 1
    else:
        rospy.logerr("Invalid mode!")
        return 1

def mirror_server():
    """
    Main of the node. Takes the information from the topic and move the baxter end effector based on those values.
    """
    
    rospy.loginfo("Initializing node... ")
    rospy.init_node('mirror_server')
    rospy.loginfo("Getting robot state... ")
    rs = baxter_interface.RobotEnable(CHECK_VERSION)
    init_state = rs.state().enabled
    rospy.loginfo("Enabling robot... ")
    rs.enable()

    service1 = rospy.Service('calibrate_mirroring',CalibrateMirror, calibrate)
    service2 = rospy.Service('enable_mirroring',EnableMirroring, enableMirroring)
    
    rospy.loginfo("Mirror Server executed -> mirror service available.")


    
    rospy.Subscriber("mirror_end_effector", mirror_end_effector, mirror_callback)
    
    def clean_shutdown():
        rospy.loginfo("\nExiting example...")
        if not init_state:
            rospy.loginfo("Disabling robot...")
            rs.disable()
    rospy.on_shutdown(clean_shutdown)

    rospy.spin()

if __name__ == "__main__":
    mirror_server()
