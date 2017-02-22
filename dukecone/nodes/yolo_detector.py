#!/usr/bin/env python2
import sys
import os
import argparse
import numpy as np
import cv2

import tensorflow as tf
import rospy

from copy import deepcopy
from sensor_msgs.msg import Image
from dukecone.msg import ObjectLocation
from cv_bridge import CvBridge, CvBridgeError

sys.path.insert(0, '../core/yolo')
from yolo_cnn_net import Yolo_tf


# Model parameters as external flags.
flags = tf.app.flags
FLAGS = flags.FLAGS
flags.DEFINE_integer('threshold', 0.2, 'YOLO sensitivity threshold')
flags.DEFINE_integer('alpha', 0.1, 'YOLO alpha')
flags.DEFINE_integer('iou_threshold', 0.5, 'YOLO iou threshold')
flags.DEFINE_integer('num_class', 20, 'Number of classes')
flags.DEFINE_integer('num_box', 2, 'Number of boxes')
flags.DEFINE_integer('grid_size', 7, 'Number of boxes')
flags.DEFINE_integer('image_width', 480, 'Width of image')
flags.DEFINE_integer('image_height', 640, 'Height of image')


class YoloNode(object):

    def __init__(self, yolo):
        self.bridge = CvBridge()
        self.image_rgb_topic = "/camera/rgb/image_color"
        self.image_depth_topic = "/camera/depth_registered/image"
        self.rgb_image_sub = rospy.Subscriber(self.image_rgb_topic,
                                              Image,
                                              self.image_callback)
        self.depth_image_sub = rospy.Subscriber(self.image_depth_topic,
                                                Image,
                                                self.depth_callback)

        self.image_depth = None
        self.tf_topic = 'tensorflow/object/location'
        self.pub_img_pos = rospy.Publisher(
            self.tf_topic, ObjectLocation, queue_size=1)

        self.img_width = None
        self.img_height = None
        self.depth_width = None
        self.depth_height = None

    def image_callback(self, data):
        try:
            image_depth_copy = deepcopy(self.image_depth)
            cv_image = self.bridge.imgmsg_to_cv2(data, "bgr8")
            self.img_width, self.img_height, _ = cv_image.shape
            # Do detection
            results = yolo.detect_from_kinect(cv_image)
            # Get the distance
            if(image_depth_copy is not None):
                self.calculate_distance(results, image_depth_copy)
        except CvBridgeError as e:
            print(e)

    def depth_callback(self, data):
        try:
            cv_depth_image = self.bridge.imgmsg_to_cv2(data, "16UC1")
            self.depth_width, self.depth_height, _ = cv_depth_image.shape
            self.image_depth = cv_depth_image
        except CvBridgeError as e:
            print(e)

    def calculate_distance(self, results, image_depth):
        # Only publish if you see a cone and the closest
        # Loop through all the bounding boxes and find min
        nearest_object_dist = sys.maxsize
        detected = False
        bounding_box = None
        for i in range(len(results)):
            # for now grab puppy since we cant detect cones
            if(results[i][0] == 'car'):
                detected = True
                x = int(results[i][1])
                y = int(results[i][2])
                w = int(results[i][3])//2
                h = int(results[i][4])//2

                x1 = x - w
                y1 = y - h
                x2 = x + w
                y2 = y + h
                x_center = (x1 + x2) // 2
                y_center = (y1 + y2) // 2

                # sanity check
                if(x_center > 640 or y_center > 480):
                    break

                center_pixel_depth = image_depth[y_center, x_center]
                distance = float(center_pixel_depth)
                print("Distance of object {} from target : \
                      {}".format(i, distance))

                #self.draw_bounding_box(results, i)
                if distance < nearest_object_dist:
                    nearest_object_dist = distance
                    bounding_box = [x, y, w, h]

        if(detected):
            # Publish the distance and bounding box
            object_topic = self.construct_topic(
                bounding_box, nearest_object_dist)
            rospy.loginfo(self.pub_img_pos)
            self.pub_img_pos.publish(object_topic)

    # use this function to draw the bounding box
    # of the detected object for testing purposes
    def draw_bounding_box(self, boxes, index):
        img = np.zeros((self.img_width, self.img_height, 3), np.uint8)
        img[:, :] = (255, 0, 0)
        x = int(boxes[index][1])
        y = int(boxes[index][2])
        w = int(boxes[index][3])//2
        h = int(boxes[index][4])//2
        x1 = x - w
        y1 = y - h
        x2 = x + w
        y2 = y + h

        x_center = (x1 + x2) // 2
        y_center = (y1 + y2) // 2

        cv2.rectangle(img, (x-w, y-h), (x+w, y+h), (0, 255, 0), 2)
        cv2.circle(img, (x_center, y_center), 5, (0, 0, 255), -1)
        bb_name = 'bounding_box_{0}.jpg'.format(index)
        cv2.imwrite(bb_name, img)

    def construct_topic(self, bounding_box, distance):
        obj_loc = ObjectLocation()
        obj_loc.x_pos = bounding_box[0]
        obj_loc.y_pos = bounding_box[1]
        obj_loc.width = bounding_box[2]
        obj_loc.height = bounding_box[3]
        obj_loc.distance = distance
        return obj_loc


if __name__ == '__main__':
    parent_dir = os.path.dirname(os.getcwd())
    image_dir = parent_dir + '/core/yolo/images/'
    weight_dir = parent_dir + '/core/yolo/weights/'

    parser = argparse.ArgumentParser()
    parser.add_argument(
                        '--weights',
                        type=str,
                        default=weight_dir + 'YOLO_small.ckpt')
    parser.add_argument(
                        '--load_test_file',
                        type=str,
                        default=image_dir + 'puppy.jpg')
    parser.add_argument(
                        '--save_test_file',
                        type=str,
                        default=image_dir + 'puppy_out.jpg')
    parser.add_argument('--alpha', type=int, default=0.1)
    parser.add_argument('--threshold', type=int, default=0.2)
    parser.add_argument('--iou_threshold', type=int, default=0.5)
    parser.add_argument('--num_class', type=int, default=20)
    parser.add_argument('--num_box', type=int, default=2)
    parser.add_argument('--grid_size', type=int, default=7)
    parser.add_argument('--image_width', type=int, default=480)
    parser.add_argument('--image_height', type=int, default=640)

    FLAGS = parser.parse_args()

    # Create yolo detector instance
    yolo = Yolo_tf(FLAGS)
    # Run the Yolo ros node
    yolonode = YoloNode(yolo)
    rospy.init_node('YoloNode', anonymous=True)
    # what rate do we want?
    #r = rospy.Rate(50)

    try:
        rospy.spin()
    except KeyboardInterrupt:
        print("Shutting down")