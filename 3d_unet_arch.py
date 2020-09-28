# -*- coding: utf-8 -*-
"""3D UNET ARCH.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1nw67ANQ2wxMuk58DMN_zdYWJF2Ymt0ts
"""

import numpy as np 
import matplotlib.pyplot as plt
import matplotlib
import tensorflow as tf
import os
import sys

!pip install pynrrd


import nrrd
import scipy.ndimage
import scipy.misc
import pickle
import random


INPUT_SIZE = 120 
OUTPUT_SIZE = 120
INPUT_DEPTH = 12 
OFF_IMAGE_FILL = 0 
OFF_LABEL_FILL = 0 
OUTPUT_CLASSES = 4 
OUTPUT_DEPTH = 12

LEARNING_RATE = 0.001 
NUM_STEPS = 10000 
BATCH_SIZE = 3 



class UNetwork():
    
    def conv_batch_relu(self, tensor, filters, kernel = [3,3,3], stride = [1,1,1], is_training = True):
        # Produces the conv_batch_relu combination as in the paper
        padding = 'valid'
        if self.should_pad: padding = 'same'
    
        conv = tf.layers.conv3d(tensor, filters, kernel_size = kernel, strides = stride, padding = padding,
                                kernel_initializer = self.base_init, kernel_regularizer = self.reg_init)
        conv = tf.layers.batch_normalization(conv, training = is_training)
        conv = tf.nn.relu(conv) 
        return conv

    def upconvolve(self, tensor, filters, kernel = 2, stride = 2, scale = 4, activation = None):
        # Upconvolution - two different implementations: the first is as suggested in the original Unet paper and the second is a more recent version
        # Needs to be determined if these do the same thing
        padding = 'valid'
        if self.should_pad: padding = 'same'
        # upsample_routine = tf.keras.layers.UpSampling3D(size = (scale,scale,scale)) # Uses tf.resize_images
        # tensor = upsample_routine(tensor)
        # conv = tf.layers.conv3d(tensor, filters, kernel, stride, padding = 'same',
        #                                 kernel_initializer = self.base_init, kernel_regularizer = self.reg_init)
        # use_bias = False is a tensorflow bug
        conv = tf.layers.conv3d_transpose(tensor, filters, kernel_size = kernel, strides = stride, padding = padding, use_bias=False, 
                                          kernel_initializer = self.base_init,  kernel_regularizer = self.reg_init)
        return conv

    def centre_crop_and_concat(self, prev_conv, up_conv):
        # If concatenating two different sized Tensors, centre crop the first Tensor to the right size and concat
        # Needed if you don't have padding
        p_c_s = prev_conv.get_shape()
        u_c_s = up_conv.get_shape()
        offsets =  np.array([0, (p_c_s[1] - u_c_s[1]) // 2, (p_c_s[2] - u_c_s[2]) // 2, 
                             (p_c_s[3] - u_c_s[3]) // 2, 0], dtype = np.int32)
        size = np.array([-1, u_c_s[1], u_c_s[2], u_c_s[3], p_c_s[4]], np.int32)
        prev_conv_crop = tf.slice(prev_conv, offsets, size)
        up_concat = tf.concat((prev_conv_crop, up_conv), 4)
        return up_concat
        
    def __init__(self, base_filt = 8, in_depth = INPUT_DEPTH, out_depth = OUTPUT_DEPTH,
                 in_size = INPUT_SIZE, out_size = OUTPUT_SIZE, num_classes = OUTPUT_CLASSES,
                 learning_rate = LEARNING_RATE, print_shapes = True, drop = 0.2, should_pad = False):
        # Initialise your model with the parameters defined above
        # Print-shape is a debug shape printer for convenience
        # Should_pad controls whether the model has padding or not
        # Base_filt controls the number of base conv filters the model has. Note deeper analysis paths have filters that are scaled by this value
        # Drop specifies the proportion of dropped activations
        
        self.base_init = tf.truncated_normal_initializer(stddev=0.1) # Initialise weights
        self.reg_init = tf.contrib.layers.l2_regularizer(scale=0.1) # Initialise regularisation (was useful)
        
        self.should_pad = should_pad # To pad or not to pad, that is the question
        self.drop = drop # Set dropout rate
        
        with tf.variable_scope('3DuNet'):
            self.training = tf.placeholder(tf.bool)
            self.do_print = print_shapes
            self.model_input = tf.placeholder(tf.float32, shape = (None, in_depth, in_size, in_size, 1))  
            # Define placeholders for feed_dict
            self.model_labels = tf.placeholder(tf.int32, shape = (None, out_depth, out_size, out_size, 1))
            labels_one_hot = tf.squeeze(tf.one_hot(self.model_labels, num_classes, axis = -1), axis = -2)
            
            if self.do_print: 
                print('Input features shape', self.model_input.get_shape())
                print('Labels shape', labels_one_hot.get_shape())
                
            # Level zero
            conv_0_1 = self.conv_batch_relu(self.model_input, base_filt, is_training = self.training)
            conv_0_2 = self.conv_batch_relu(conv_0_1, base_filt*2, is_training = self.training)
            # Level one
            max_1_1 = tf.layers.max_pooling3d(conv_0_2, [1,2,2], [1,2,2]) # Stride, Kernel previously [2,2,2]
            conv_1_1 = self.conv_batch_relu(max_1_1, base_filt*2, is_training = self.training)
            conv_1_2 = self.conv_batch_relu(conv_1_1, base_filt*4, is_training = self.training)
            conv_1_2 = tf.layers.dropout(conv_1_2, rate = self.drop, training = self.training)
            # Level two
            max_2_1 = tf.layers.max_pooling3d(conv_1_2, [1,2,2], [1,2,2]) # Stride, Kernel previously [2,2,2]
            conv_2_1 = self.conv_batch_relu(max_2_1, base_filt*4, is_training = self.training)
            conv_2_2 = self.conv_batch_relu(conv_2_1, base_filt*8, is_training = self.training)
            conv_2_2 = tf.layers.dropout(conv_2_2, rate = self.drop, training = self.training)
            # Level three
            max_3_1 = tf.layers.max_pooling3d(conv_2_2, [1,2,2], [1,2,2]) # Stride, Kernel previously [2,2,2]
            conv_3_1 = self.conv_batch_relu(max_3_1, base_filt*8, is_training = self.training)
            conv_3_2 = self.conv_batch_relu(conv_3_1, base_filt*16, is_training = self.training)
            conv_3_2 = tf.layers.dropout(conv_3_2, rate = self.drop, training = self.training)
            # Level two
            up_conv_3_2 = self.upconvolve(conv_3_2, base_filt*16, kernel = 2, stride = [1,2,2]) # Stride previously [2,2,2] 
            concat_2_1 = self.centre_crop_and_concat(conv_2_2, up_conv_3_2)
            conv_2_3 = self.conv_batch_relu(concat_2_1, base_filt*8, is_training = self.training)
            conv_2_4 = self.conv_batch_relu(conv_2_3, base_filt*8, is_training = self.training)
            conv_2_4 = tf.layers.dropout(conv_2_4, rate = self.drop, training = self.training)
            # Level one
            up_conv_2_1 = self.upconvolve(conv_2_4, base_filt*8, kernel = 2, stride = [1,2,2]) # Stride previously [2,2,2]
            concat_1_1 = self.centre_crop_and_concat(conv_1_2, up_conv_2_1)
            conv_1_3 = self.conv_batch_relu(concat_1_1, base_filt*4, is_training = self.training)
            conv_1_4 = self.conv_batch_relu(conv_1_3, base_filt*4, is_training = self.training)
            conv_1_4 = tf.layers.dropout(conv_1_4, rate = self.drop, training = self.training)
            # Level zero
            up_conv_1_0 = self.upconvolve(conv_1_4, base_filt*4, kernel = 2, stride = [1,2,2])  # Stride previously [2,2,2]
            concat_0_1 = self.centre_crop_and_concat(conv_0_2, up_conv_1_0)
            conv_0_3 = self.conv_batch_relu(concat_0_1, base_filt*2, is_training = self.training)
            conv_0_4 = self.conv_batch_relu(conv_0_3, base_filt*2, is_training = self.training)
            conv_0_4 = tf.layers.dropout(conv_0_4, rate = self.drop, training = self.training)
            conv_out = tf.layers.conv3d(conv_0_4, OUTPUT_CLASSES, [1,1,1], [1,1,1], padding = 'same')
            self.predictions = tf.expand_dims(tf.argmax(conv_out, axis = -1), -1)
            
            # Note, this can be more easily visualised in a tool like tensorboard; Follows exact same format as in Paper.
            
            if self.do_print: 
                print('Model Convolution output shape', conv_out.get_shape())
                print('Model Argmax output shape', self.predictions.get_shape())
            
            do_weight = True
            loss_weights = [1, 150, 100, 1.0]
            # Weighted cross entropy: approach adapts following code: https://stackoverflow.com/questions/44560549/unbalanced-data-and-weighted-cross-entropy
            ce_loss = tf.nn.softmax_cross_entropy_with_logits(logits=conv_out, labels=labels_one_hot)
            if do_weight:
                weighted_loss = tf.reshape(tf.constant(loss_weights), [1, 1, 1, 1, num_classes]) # Format to the right size
                weighted_one_hot = tf.reduce_sum(weighted_loss*labels_one_hot, axis = -1)
                ce_loss = ce_loss * weighted_one_hot
            
            self.loss = tf.reduce_mean(ce_loss) # Get loss
            
            self.trainer = tf.train.AdamOptimizer(learning_rate=learning_rate)
            
            self.extra_update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS) # Ensure correct ordering for batch-norm to work
            with tf.control_dependencies(self.extra_update_ops):
                self.train_op = self.trainer.minimize(self.loss)

