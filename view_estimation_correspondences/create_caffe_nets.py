import os
import sys
from warnings import warn

# Import global variables
view_estimation_correspondences_path = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(view_estimation_correspondences_path))
import global_variables as gv

# Import Caffe
sys.path.append(gv.g_pycaffe_path)
import caffe
from caffe.proto import caffe_pb2
from google.protobuf import text_format
from caffe import layers as L
from caffe import params as P

# Define paths
train_models_root_path = os.path.join(gv.g_render4cnn_root_folder, 'train')

# Define common fillers and parameters
DEFAULT_LRN_PARAM = dict(local_size=5, alpha=0.0001, beta=0.75)
DEFAULT_DECAY_PARAM = [dict(decay_mult=1), dict(decay_mult=0)]
DEFAULT_WEIGHT_FILLER = dict(type='gaussian', std=0.01)
DEFAULT_BIAS_FILLER = dict(type='constant', value=0)
DEFAULT_DROPOUT_RATIO = 0.5
DEFAULT_ANGLE_NAMES = ['azimuth', 'elevation', 'tilt']
DEFAULT_LOSS_WEIGHTS = [1, 1, 1]

# Parameters for angle softmax+loss
DEFAULT_SOFTMAX_VIEW_LOSS_PARAM_A = dict(bandwidth=15, sigma=5, pos_weight=1, neg_weight=0, period=360)
DEFAULT_SOFTMAX_VIEW_LOSS_PARAM_ET = dict(bandwidth=5, sigma=3, pos_weight=1, neg_weight=0, period=360)
DEFAULT_VIEW_LOSS_PARAMS = [DEFAULT_SOFTMAX_VIEW_LOSS_PARAM_A, DEFAULT_SOFTMAX_VIEW_LOSS_PARAM_ET, DEFAULT_SOFTMAX_VIEW_LOSS_PARAM_ET]
# Parameters for angle accuracy
DEFAULT_ACCURACY_VIEW_PARAM_A = dict(tol_angle=15, period=360)
DEFAULT_ACCURACY_VIEW_PARAM_ET = dict(tol_angle=5, period=360)
DEFAULT_ACCURACY_VIEW_PARAMS = [DEFAULT_ACCURACY_VIEW_PARAM_A, DEFAULT_ACCURACY_VIEW_PARAM_ET, DEFAULT_ACCURACY_VIEW_PARAM_ET]

# Default solver
DEFAULT_SOLVER_DICT = dict(
    train_net=None,
    test_net=None,
    test_iter=15,
    test_interval=2000,
    base_lr=0.001,
    lr_policy='step',
    gamma=0.1,
    stepsize=100000,
    max_iter=100000,
    display=100,
    momentum=0.9,
    weight_decay=0.0005,
    snapshot=1000,
    snapshot_prefix=None,
    solver_mode='GPU'
)

'''
Merge the given dictionaries and return the result.
@args:
    dict_args (args of type dict): The dictionaries to merge together.
'''
def merge_dicts(*dict_args):
    res = dict()
    for dict_arg in dict_args:
        res.update(dict_arg)
    return res

'''
Generate solver text from a dictionary.
@args
    d (dict): The dictionary to generate solver text from.
'''
def dict_to_solver_text(d, allow_empty=False):
    ret = ''
    for key, value in d.iteritems():
        if value is None:
            if allow_empty:
                warn('Generating solver with empty parameter %s' % key)
            else:
                raise Exception('Solver dictionary has empty parameter %s' % key)
        # Figure out if the value needs quotes around it. Strings generally need quotes, except for some stupid cases
        if isinstance(value, basestring) and key not in ['solver_mode']:
            value = '"%s"' % value
        ret += '%s: %s\n' % (key, value)
    return ret

'''
Create an in-place ReLU layer.
@args
    name (str): Name of the ReLU layer
    bottom (str): Name of the blob to apply ReLU to
'''
def relu(name, bottom):
    return L.ReLU(name=name, bottom=bottom, top=bottom, in_place=True)

'''
Create an in-place Dropout layer.
@args
    name (str): Name of the Dropout layer
    bottom (str): Name of the blob to apply Dropout to
    dropout_ratio (float): How often to drop out the activation
'''
def dropout(name, bottom, dropout_ratio=DEFAULT_DROPOUT_RATIO):
    return L.Dropout(name=name, bottom=bottom, top=bottom, in_place=True, dropout_param=dict(
        dropout_ratio=dropout_ratio
    ))

'''
Create an InnerProduct (FC) layer with given filler and decay parameters.
@args
    name (str): Name of the InnerProduct layer
    bottom (str): Name of the input blob for the InnerProduct layer
    num_output (int): Number of outputs for the InnerProduct layer
    weight_filler (dict): The parameters for the weight filler
    bias_filler (dict): The parameters of the bias filler
'''
def innerproduct(name, bottom, num_output, weight_filler=DEFAULT_WEIGHT_FILLER, bias_filler=DEFAULT_BIAS_FILLER):
    return L.InnerProduct(name=name, bottom=bottom, param=DEFAULT_DECAY_PARAM, inner_product_param=dict(
        num_output=num_output, weight_filler=weight_filler, bias_filler=bias_filler
    ))

'''
Create a LRN layer with given parameters.
@args
    name (str): Name of the LRN layer
    bottom (str): Name of the input blob for the LRN layer

'''
def lrn(name, bottom, lrn_param=DEFAULT_LRN_PARAM):
    return L.LRN(name=name, bottom=bottom, lrn_param=lrn_param)

'''
Augment the given network specification with a conv layer with optional activation wrappers. Layers are automatically generated based on the name of the base conv layer.
The wrappers are generated in order and named as follows: conv## -> relu## -> pool## -> norm##
@args
    net_spec (caffe.NetSpec): The network specification to augment
    name (str): Name of the base conv layer
    bottom (str): Name of the input blob for the base conv layer
    use_relu (bool): Whether to apply ReLU activation to the base conv layer
    pooling_param (dict): Parameters for the pooling layer, if desired
    lrn_param (dict): Parameters for the LRN layer, if desired
'''
def add_wrapped_conv_layer(net_spec, name, bottom, conv_param, param=None, use_relu=True, pooling_param=None, lrn_param=None):
    assert(name[:4] == 'conv')
    if param:
        net_spec[name] = L.Convolution(name=name, bottom=bottom, param=param, convolution_param=conv_param)
    else:
        net_spec[name] = L.Convolution(name=name, bottom=bottom, convolution_param=conv_param)
    out_name = name
    if use_relu:
        relu_name = name.replace('conv', 'relu')
        net_spec[relu_name] = relu(relu_name, name)
        out_name = name
    if pooling_param:
        pool_name = name.replace('conv', 'pool')
        net_spec[pool_name] = L.Pooling(name=pool_name, bottom=name, pooling_param=pooling_param)
        out_name = pool_name
    if lrn_param:
        lrn_name = name.replace('conv', 'norm')
        net_spec[lrn_name] = lrn(lrn_name, out_name, lrn_param=lrn_param)
        out_name = lrn_name
    return out_name

'''
Augment the given network specification with an InnerProduct (FC) layer with optional activation wrappers. Layers are automatically generated based on the name of the base InnerProduct layer.
The wrappers are generated in order and named as follows: fc## -> relu## -> drop##
@args
    net_spec (caffe.NetSpec): The network specification to augment
    name (str): Name of the base conv layer
    bottom (str): Name of the input blob for the base FC layer
    num_output (int): The number of outputs for the base FC layer
    use_relu (bool): Whether to apply ReLU activation to the base FC layer
    dropout_ratio (float): The dropout ratio, if desired
'''
def add_wrapped_fc_layer(net_spec, name, bottom, num_output, use_relu=True, dropout_ratio=-1):
    assert(name[:2] == 'fc')
    net_spec[name] = innerproduct(name, bottom, num_output)
    if use_relu:
        relu_name = name.replace('fc', 'relu')
        net_spec[relu_name] = relu(relu_name, name)
    if dropout_ratio >= 0:
        dropout_name = name.replace('fc', 'drop')
        net_spec[dropout_name] = dropout(dropout_name, name)
    return name

'''
Augment the given network specification with prediction layers.
@args
    net_spec (caffe.NetSpec): The network specification augment
    name_prefix (str): The string to append to each output
    bottom (str): Name of the input blob for the prediction layers
    num_output (int): The number of outputs for each prediction layer
    angle_names (str): The names of the angles to predict
'''
def add_prediction_layers(net_spec, name_prefix, bottom, num_output=4320, angle_names=DEFAULT_ANGLE_NAMES):
    for angle_name in angle_names:
        pred_name = name_prefix + angle_name
        net_spec[pred_name] = innerproduct(pred_name, bottom, num_output)

'''
Augment the given network specification with loss and accuracy layers.
@args
    net_spec (caffe.NetSpec): The network specification augment
    name_prefix (str): The string to append to each output
    bottom (str): Name of the input blob for the prediction layers
    num_output (int): The number of outputs for each prediction layer
    angle_names (str): The names of the angles to predict
'''
def add_loss_acc_layers(net_spec, bottom_prefixes, angle_names=DEFAULT_ANGLE_NAMES, loss_weights=DEFAULT_LOSS_WEIGHTS, loss_param_arr=DEFAULT_VIEW_LOSS_PARAMS, acc_param_arr=DEFAULT_ACCURACY_VIEW_PARAMS):
    assert(len(angle_names) == len(loss_weights) == len(loss_param_arr) == len(acc_param_arr))
    for i, angle_name in enumerate(angle_names):
        # Add loss layer for current angle
        loss_name = 'loss_' + angle_name
        bottom = [x + angle_name for x in bottom_prefixes]
        net_spec[loss_name] = L.SoftmaxWithViewLoss(name=loss_name, bottom=bottom, loss_weight=loss_weights[i], softmax_with_view_loss_param=loss_param_arr[i])
        # Add accuracy layer for current angle
        acc_name = 'accuracy_' + angle_name
        net_spec[acc_name] = L.AccuracyView(name=acc_name, bottom=bottom, accuracy_view_param=acc_param_arr[i])


def train_model_r4cnnpp(lmdb_paths, batch_size, crop_size=gv.g_images_resize_dim, imagenet_mean_file=gv.g_image_mean_binaryproto_file):
    train_data_lmdb_path = lmdb_paths[0]
    train_label_lmdb_path = lmdb_paths[1]
    data_transform_param = dict(
        crop_size=crop_size,
        mean_file=imagenet_mean_file,
        mirror=False
    )

    n = caffe.NetSpec()
    # Data layers
    # n['data'] = L.Data(name='data', batch_size=batch_size, backend=P.Data.LMDB, include=dict(phase=caffe.TRAIN), source=train_data_lmdb_path, transform_param=data_transform_param)
    # n['label'] = L.Data(name='label', batch_size=batch_size, backend=P.Data.LMDB, include=dict(phase=caffe.TRAIN), source=train_label_lmdb_path)
    n['data'] = L.Data(name='data', batch_size=batch_size, backend=P.Data.LMDB, source=train_data_lmdb_path, transform_param=data_transform_param)
    n['label'] = L.Data(name='label', batch_size=batch_size, backend=P.Data.LMDB, source=train_label_lmdb_path)
    n['label_class'], n['label_azimuth'], n['label_elevation'], n['label_tilt'] = L.Slice(name='labe-slice', bottom='label', ntop=4, slice_param=dict(
        slice_dim=1, slice_point=[1,2,3]
    ))
    n['silence-label_class'] = L.Silence(name='silence-label_class', bottom='label_class', ntop=0)

    # Image (Render for CNN) features
    conv1_param = dict(num_output=96, kernel_size=11, stride=4)
    pool1_param = dict(pool=P.Pooling.MAX, kernel_size=3, stride=2)
    conv2_param = dict(num_output=256, pad=2, kernel_size=5, group=2)
    pool2_param = dict(pool=P.Pooling.MAX, kernel_size=3, stride=2)
    conv3_param = dict(num_output=384, pad=1, kernel_size=3)
    conv4_param = dict(num_output=384, pad=1, kernel_size=3, group=2)
    conv5_param = dict(num_output=256, pad=1, kernel_size=3, group=2)
    pool5_param = dict(pool=P.Pooling.MAX, kernel_size=3, stride=2)
    conv1_out_name = add_wrapped_conv_layer(n, 'conv1', 'data', conv1_param, pooling_param=pool1_param, lrn_param=DEFAULT_LRN_PARAM)
    conv2_out_name = add_wrapped_conv_layer(n, 'conv2', conv1_out_name, conv2_param, pooling_param=pool2_param, lrn_param=DEFAULT_LRN_PARAM)
    conv3_out_name = add_wrapped_conv_layer(n, 'conv3', conv2_out_name, conv3_param)
    conv4_out_name = add_wrapped_conv_layer(n, 'conv4', conv3_out_name, conv4_param, param=DEFAULT_DECAY_PARAM)
    conv5_out_name = add_wrapped_conv_layer(n, 'conv5', conv4_out_name, conv5_param, param=DEFAULT_DECAY_PARAM, pooling_param=pool5_param)
    fc6_out_name = add_wrapped_fc_layer(n, 'fc6', conv5_out_name, 4096, dropout_ratio=DEFAULT_DROPOUT_RATIO)
    fc7_out_name = add_wrapped_fc_layer(n, 'fc7', fc6_out_name, 4096, dropout_ratio=DEFAULT_DROPOUT_RATIO)
    fc8_out_name = add_wrapped_fc_layer(n, 'fc8', fc7_out_name, 4096, dropout_ratio=DEFAULT_DROPOUT_RATIO)
    fc9_out_name = add_wrapped_fc_layer(n, 'fc9', fc8_out_name, 4096, dropout_ratio=DEFAULT_DROPOUT_RATIO)

    # Prediction and loss layers
    add_prediction_layers(n, 'pred_', fc9_out_name)
    add_loss_acc_layers(n, ['pred_', 'label_'])

    return n.to_proto()


if __name__ == '__main__':
    # Set LMDB paths
    train_lmdbs_root = gv.g_corresp_syn_images_lmdb_folder
    train_lmdb_paths = [os.path.join(train_lmdbs_root, lmdb_name) for lmdb_name in ['image_lmdb', 'viewpoint_label_lmdb']]
    test_lmdbs_root = gv.g_corresp_real_images_test_lmdb_folder
    test_lmdb_paths = [os.path.join(test_lmdbs_root, lmdb_name) for lmdb_name in ['image_lmdb', 'viewpoint_label_lmdb']]

    # Set model and solver paths
    model_root = os.path.join(gv.g_render4cnn_root_folder, 'train', 'c_new')
    model_train_path = os.path.join(model_root, 'syn-train.prototxt')
    model_test_path = os.path.join(model_root, 'syn-test.prototxt')
    solver_path = os.path.join(model_root, 'solver_syn.prototxt')

    # Generate train model prototxt file
    train_model = train_model_r4cnnpp(train_lmdb_paths, 64)
    with open(model_train_path, 'w') as f:
        f.write(str(train_model))
    # Generate test model prototxt file
    test_model = train_model_r4cnnpp(test_lmdb_paths, 64)
    with open(model_test_path, 'w') as f:
        f.write(str(test_model))

    non_default_params = dict(train_net=model_train_path, test_net=model_test_path, snapshot_prefix='syn')
    all_params = merge_dicts(DEFAULT_SOLVER_DICT, non_default_params)
    solver_text = dict_to_solver_text(all_params)
    with open(solver_path, 'w') as f:
        f.write(solver_text)