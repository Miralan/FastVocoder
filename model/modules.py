import torch
import torch.nn as nn

import math
import numpy as np

from layers import Conv1d1x1


def get_sinusoid_encoding_table(n_position, d_hid, padding_idx=None):
    ''' Sinusoid position encoding table '''

    def cal_angle(position, hid_idx):
        return position / np.power(10000, 2 * (hid_idx // 2) / d_hid)

    def get_posi_angle_vec(position):
        return [cal_angle(position, hid_j) for hid_j in range(d_hid)]

    sinusoid_table = np.array([get_posi_angle_vec(pos_i)
                               for pos_i in range(n_position)])

    sinusoid_table[:, 0::2] = np.sin(sinusoid_table[:, 0::2])  # dim 2i
    sinusoid_table[:, 1::2] = np.cos(sinusoid_table[:, 1::2])  # dim 2i+1

    if padding_idx is not None:
        # zero vector for padding dimension
        sinusoid_table[padding_idx] = 0.

    return torch.FloatTensor(sinusoid_table)


def overlap_and_add(signal, frame_step):
    """Reconstructs a signal from a framed representation.

    Adds potentially overlapping frames of a signal with shape
    `[..., frames, frame_length]`, offsetting subsequent frames by `frame_step`.
    The resulting tensor has shape `[..., output_size]` where

        output_size = (frames - 1) * frame_step + frame_length

    Args:
        signal: A [..., frames, frame_length] Tensor. All dimensions may be unknown, and rank must be at least 2.
        frame_step: An integer denoting overlap offsets. Must be less than or equal to frame_length.

    Returns:
        A Tensor with shape [..., output_size] containing the overlap-added frames of signal's inner-most two dimensions.
        output_size = (frames - 1) * frame_step + frame_length

    Based on https://github.com/tensorflow/tensorflow/blob/r1.12/tensorflow/contrib/signal/python/ops/reconstruction_ops.py
    """
    outer_dimensions = signal.size()[:-2]
    frames, frame_length = signal.size()[-2:]

    # gcd=Greatest Common Divisor
    subframe_length = math.gcd(frame_length, frame_step)
    subframe_step = frame_step // subframe_length
    subframes_per_frame = frame_length // subframe_length
    output_size = frame_step * (frames - 1) + frame_length
    output_subframes = output_size // subframe_length

    subframe_signal = signal.view(*outer_dimensions, -1, subframe_length)

    frame = torch.arange(0, output_subframes).unfold(0, subframes_per_frame, subframe_step)
    frame = signal.new_tensor(frame).long()  # signal may in GPU or CPU
    frame = frame.contiguous().view(-1)

    result = signal.new_zeros(*outer_dimensions, output_subframes, subframe_length)
    device_of_result = result.device
    result.index_add_(-2, frame.to(device_of_result), subframe_signal)
    result = result.view(*outer_dimensions, -1)
    return result


class BasisSignalLayer(nn.Module):
    """ Basis Signal """

    def __init__(self, basis_signal_weight, L=64):
        super(BasisSignalLayer, self).__init__()
        self.layer = nn.Linear(basis_signal_weight.size(0), basis_signal_weight.size(1), bias=False)
        self.layer.weight = nn.Parameter(basis_signal_weight)
        self.L = L

    def forward(self, weight):
        source = self.layer(weight)
        source = overlap_and_add(source, self.L // 2)
        return source


class LastLinear(nn.Module):
    def __init__(self, hidden_channel, out_channel):
        super(LastLinear, self).__init__()
        self.activation = nn.LeakyReLU(negative_slope=0.2)
        self.bn_1 = nn.BatchNorm1d(hidden_channel)
        self.linear_1 = Conv1d1x1(hidden_channel, hidden_channel, bias=True)
        self.bn_2 = nn.BatchNorm1d(hidden_channel)
        self.linear_2 = Conv1d1x1(hidden_channel, out_channel, bias=True)

    def forward(self, x):
        x = self.activation(x)
        x = self.bn_1(x)
        x = self.linear_1(x)
        x = self.activation(x)
        x = self.bn_2(x)
        x = self.linear_2(x)
        return x