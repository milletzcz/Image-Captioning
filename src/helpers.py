"""
    Author: Mohamed K. Eid (mohamedkeid@gmail.com)
    Description:
"""

import logging
import numpy as np
import os
import pickle
import tensorflow as tf
import skimage
import skimage.io
import skimage.transform
from scipy.misc import toimage
from functools import reduce


def get_annotations_path():
    return get_lib_path() + '/annotations/'


def get_captions_path(train=True):
    if train:
        return get_annotations_path() + '/captions_train2014.json'
    else:
        return get_annotations_path() + '/captions_val2014.json'


def get_cosine_similarity(a, b):
    a_norm = get_l2_norm(a)
    b_norm = get_l2_norm(b)
    ab = tf.matmul(b, a, transpose_b=True)
    similarity = ab / (a_norm * b_norm)
    return similarity


def get_current_path():
    return os.path.dirname(os.path.realpath(__file__)) + '/../'


def get_data(name):
    if pickle_exists(name):
        return load_obj(name)
    else:
        return {}


def get_lib_path():
    return get_current_path() + '/lib/'


def get_l2_norm(t):
    t = tf.squeeze(t)
    norm = tf.sqrt(tf.reduce_sum(tf.square(t)))
    return norm


def get_training_path():
    return get_lib_path() + '/train2014/'


def get_training_size():
    path = get_training_path()
    return len([f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))])


def get_training_next_path():
    for root, dirs, files in os.walk(get_training_path()):
        for name in files:
            if ".jpg" in name:
                return os.path.join(root, name)
            else:
                return get_training_next_path()


# Return a resized numpy array of an image specified by its path
def load_image2(path, height=None, width=None):
    # Load image
    img = skimage.io.imread(path) / 255.0
    if height is not None and width is not None:
        ny = height
        nx = width
    elif height is not None:
        ny = height
        nx = img.shape[1] * ny / img.shape[0]
    elif width is not None:
        nx = width
        ny = img.shape[0] * nx / img.shape[1]
    else:
        ny = img.shape[0]
        nx = img.shape[1]
    return skimage.transform.resize(img, (ny, nx))


def next_example(height, width):
    # Ops for getting training images, from retrieving the filenames to reading the data
    regex = get_training_path() + '/*.jpg'
    filenames = tf.train.match_filenames_once(regex)
    filename_queue = tf.train.string_input_producer(filenames)
    reader = tf.WholeFileReader()
    _, file = reader.read(filename_queue)

    img = tf.image.decode_jpeg(file, channels=3)
    img = tf.image.resize_images(img, [height, width])

    return img, 0


def pickle_exists(name):
    return os.path.exists(get_lib_path() + name + '.pkl')


def save_model(session, saver, path):
    logging.info("Proceeding to save weights at '%s'" % path)
    saver.save(session, path)
    logging.info("Weights have been saved.")


def save_obj(obj, name):
    with open(get_lib_path() + name + '.pkl', 'wb') as f:
        pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)


def load_obj(name):
    with open(get_lib_path() + name + '.pkl', 'rb') as f:
        x = pickle.load(f)
        return x
