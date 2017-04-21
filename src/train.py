"""
    Author: Mohamed K. Eid (mohamedkeid@gmail.com)
    Description: Executable script for training a new captioning model.
"""

import helpers
import logging
import math
import numpy as np
import tensorflow as tf
import time

import stv.configuration as stv_configuration
from attention import Attention
from caption_extractor import CaptionExtractor
from decoder import Decoder
from neighbor import Neighbor
from stv.encoder_manager import EncoderManager
from vgg.fcn16_vgg import FCN16VGG as Vgg16
from vocab import Vocab

FLAGS = tf.flags.FLAGS
helpers.config_model_flags()
helpers.config_logging(env='training')

# Optimization flags
tf.flags.DEFINE_integer('batch_size', 16, 'Mini-Batch size of images')
tf.flags.DEFINE_integer('epochs', 100, 'Number of training iterations')
tf.flags.DEFINE_float('learning_rate', 4e-4, 'Optimizer learning rate')
tf.flags.DEFINE_float('learning_rate_dec_factor', .8, 'Factor in which the learning rate decreases')
tf.flags.DEFINE_integer('learning_rate_dec_freq', 3, 'How often (iterations) the learning rate decreases')
tf.flags.DEFINE_integer('learning_rate_dec_thresh', 10, 'Number of iterations before learning rate starts decreasing')

# Misc flags
tf.flags.DEFINE_float('epsilon', 1e-8, 'Tiny value to for log parameters')
tf.flags.DEFINE_integer('print_every', 100, 'How often (iterations) to log the current progress of training')
tf.flags.DEFINE_integer('save_every', 1000, 'How often (iterations) to save the current state of the model')


config = helpers.get_session_config()
with tf.Session(config=config) as sess:
    # Init
    vocab = Vocab()
    k = math.sqrt(FLAGS.kk)

    # Initialize placeholders
    candidate_captions_ph = tf.placeholder(dtype=tf.string, shape=[None, FLAGS.n * 5])
    caption_encoding_ph = tf.placeholder(dtype=tf.float32, shape=[None, FLAGS.stv_size])
    image_ph = tf.placeholder(dtype=tf.float32, shape=[None, FLAGS.train_height, FLAGS.train_width, 3])
    image_conv_encoding_ph = tf.placeholder(dtype=tf.float32, shape=[None, k, k, FLAGS.conv_size])
    image_fc_encoding_ph = tf.placeholder(dtype=tf.float32, shape=[None, k, k, 4096])
    image_name_ph = tf.placeholder(dtype=tf.string)
    labels_ph = tf.placeholder(tf.int32, shape=(None, ))
    learning_rate_ph = tf.placeholder(dtype=tf.float32, shape=[1])
    rnn_inputs_ph = tf.placeholder(dtype=tf.float32, shape=[None, None, 5])
    training_fc_encodings_ph = tf.placeholder(dtype=tf.float32, shape=[helpers.get_training_size(), k, k, 4096])
    training_filenames_ph = tf.placeholder(dtype=tf.string, shape=[helpers.get_training_size()])
    seq_len_ph = tf.placeholder(dtype=tf.int32, shape=[None, ])

    # Initialize auxiliary
    image_shape = [1, FLAGS.train_height, FLAGS.train_width, 3]
    neighbor = Neighbor(image_fc_encoding_ph, training_fc_encodings_ph, training_filenames_ph)

    # Initialize encoders
    with tf.name_scope('encoders'):
        vgg = Vgg16()
        vgg.build(image_ph, image_shape[1:])
        conv_encoding = vgg.pool5
        fc_encoding = vgg.fc7

    # Initialize guidance caption extractor and skip-thought-vector model
    extractor = CaptionExtractor()
    stv = EncoderManager()
    stv_uni_config = stv_configuration.model_config()
    stv.load_model(stv_uni_config, FLAGS.stv_vocab_file, FLAGS.stv_embeddings_file, FLAGS.stv_checkpoint_path)

    # Attention model and decoder
    tatt = Attention(conv_encoding, caption_encoding_ph)
    #decoder = Decoder(tatt.context_vector, rnn_inputs_ph)

    # Set up ops for decoding the caption
    #predicted_index = tf.argmax(decoder.output, axis=1)
    #predicted_word = tf.gather(vocab.list, predicted_index)

    """"
    # Loss ops
    targets_one_hot = tf.one_hot(indices=labels_ph, depth=FLAGS.vocab_size, axis=1, dtype=tf.int32)
    targets = tf.unstack(targets_one_hot, axis=1)
    losses = [tf.nn.sparse_softmax_cross_entropy_with_logits(labels=target, logits=logits)
              for logit, target in zip(logits, targets)]
    loss = tf.reduce_mean(losses)

    # Optimization ops

    with tf.name_scope('optimization'):
        optimizer = tf.train.AdamOptimizer(learning_rate_ph)

        # Attention optimization ops
        attention_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='attention')
        attention_grads = optimizer.compute_gradients(loss, attention_vars)
        update_attention = optimizer.apply_gradients(attention_grads)

        # Decoder optimization ops
        decoder_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='decoder')
        decoder_grads = optimizer.compute_gradients(loss, decoder_vars)
        update_decoder = optimizer.apply_gradients(decoder_grads)

        update_step = tf.group(update_attention, update_decoder)
    """

    # Training data ops
    example_image, example_filename = helpers.next_example(height=FLAGS.train_height, width=FLAGS.train_width)
    capacity = FLAGS.batch_size * 2
    batch_examples, batch_filenams = tf.train.batch([example_image, example_filename],
                                                    FLAGS.batch_size,
                                                    num_threads=8,
                                                    capacity=capacity)
    all_examples, all_filenames = tf.train.batch([example_image, example_filename],
                                                 helpers.get_training_size(),
                                                 num_threads=8,
                                                 capacity=10000)

    # Initialize session and threads then begin training
    logging.info("Begining training..")
    sess.run(tf.global_variables_initializer())
    coord = tf.train.Coordinator()
    threads = tf.train.start_queue_runners(coord=coord)
    start_time = time.time()
    saver = tf.train.Saver()

    # Evaluate training examples now since they do not need to recomputed in our loop
    all_examples_eval = all_examples.eval()
    all_filenames_eval = all_filenames.eval()

    # Optimization loop
    for e in range(FLAGS.epochs):
        num_iterations = math.floor(helpers.get_training_size() // FLAGS.batch_size)

        # Iterate through our entire training dataset
        for i in range(num_iterations + 1):
            # Compute image encdings
            example_images = batch_examples.eval()
            example_conv_encodings = conv_encoding.eval(feed_dict={image_ph: example_images})
            examples_fc_encoding = fc_encoding.eval(feed_dict={image_ph: example_images})
            training_fc_encodings = fc_encoding.eval(feed_dict={image_ph: all_examples_eval})

            # Get nearest neighboring images
            neighbor_dict = {
                image_fc_encoding_ph: examples_fc_encoding,
                training_fc_encodings_ph: training_fc_encodings,
                training_filenames_ph: all_filenames_eval}
            nearest_neighbors = neighbor.nearest.eval(feed_dict=neighbor_dict)

            # Get guidance caption encodings
            guidance_captions = extractor.get_guidance_caption(nearest_neighbors)
            guidance_caption_encodings = stv.encode(guidance_captions, batch_size=FLAGS.batch_size, use_eos=True)

            # Set up vars for update
            rnn_inputs = vocab.get_bos_rnn_input()
            feed_dict = {caption_encoding_ph: guidance_caption_encodings,
                         image_conv_encoding_ph: example_conv_encodings,
                         rnn_inputs_ph: np.array(rnn_inputs)}

            # Update weights
            for _ in range(FLAGS.max_caption_size):
                # If the prediction was <eos>, break the loop

                # Make the next input for the decoder
                predicted_1hot = helpers.index_to_1hot(word_index)
                predicted_1hot = [predicted_1hot]
                rnn_inputs = np.concatenate((rnn_inputs, predicted_1hot), axis=1)
                feed_dict[rnn_inputs_ph] = np.array(rnn_inputs)

            # Decrement the learning rate if the desired threshold has been surpassed
            if i > FLAGS.learning_rate_dec_threh and i % FLAGS.learning_rate_dec_freq == 0:
                FLAGS.learning_rate /= FLAGS.learning_rate_dec_factor

            # Log loss
            if i % FLAGS.print_every == 0:
                logging.info("Epoch %03d | Iteration %06d | Loss %.03f" % (e, i, l))

            # Occasionally save model
            if i % FLAGS.save_every == 0:
                helpers.save_model(saver, helpers.get_new_model_path)

    # Alert that training has been completed and print the run time
    elapsed = time.time() - start_time
    logging.info("Training complete. The session took %.2f seconds to complete." % elapsed)
    coord.request_stop()
    coord.join(threads)

    # Save the trained model join threads
    helpers.save_model(saver, helpers.get_new_model_path())
    coord.request_stop()
    coord.join(threads)
