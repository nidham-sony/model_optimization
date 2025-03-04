# Copyright 2022 Sony Semiconductor Israel, Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
from typing import Callable, List, Tuple, Union

import numpy as np
from torch.nn import Module
from tqdm import tqdm
import copy
import torch
from model_compression_toolkit.core.common.logger import Logger
from model_compression_toolkit.core.pytorch.back2framework.pytorch_model_builder import PyTorchModelBuilder
from model_compression_toolkit.gptq.common.gptq_graph import get_kernel_attribute_name_for_gptq
from model_compression_toolkit.gptq.common.gptq_training import GPTQTrainer
from model_compression_toolkit.gptq.common.gptq_config import GradientPTQConfigV2, RoundingType
from model_compression_toolkit.core.common import Graph, BaseNode
from model_compression_toolkit.core.common.framework_info import FrameworkInfo
from model_compression_toolkit.core.common.framework_implementation import FrameworkImplementation
from model_compression_toolkit.core.pytorch.constants import BIAS
from model_compression_toolkit.core.pytorch.utils import to_torch_tensor, set_model, torch_tensor_to_numpy
from model_compression_toolkit.gptq.pytorch.graph_info import get_gptq_trainable_parameters, \
    get_weights_for_loss, get_soft_rounding_reg
from model_compression_toolkit.gptq.pytorch.quantizer.quantization_builder import quantization_builder
from model_compression_toolkit.gptq.common.gptq_constants import REGULARIZATION_VALUES
from model_compression_toolkit import quantizers_infrastructure as qi
from model_compression_toolkit.quantizers_infrastructure import PytorchQuantizationWrapper


class PytorchGPTQTrainer(GPTQTrainer):
    """
    Pytorch GPTQ training class for fine-tuning a quantized model
    """

    def __init__(self,
                 graph_float: Graph,
                 graph_quant: Graph,
                 gptq_config: GradientPTQConfigV2,
                 fw_impl: FrameworkImplementation,
                 fw_info: FrameworkInfo,
                 representative_data_gen: Callable):
        """
        Build two models from a graph: A teacher network (float model) and a student network (quantized model).
        Use the dataset generator to pass images through the teacher and student networks to get intermediate
        layers outputs. Use the outputs to compute the observed loss and to back-propagate the error
        in the student network, to minimize it in the next similar steps.
        All parameters (such as number of iterations, optimizer, etc.) are in GradientPTQConfig.
        Args:
            graph_float: Graph to build a float networks from.
            graph_quant: Graph to build a quantized networks from.
            gptq_config: GradientPTQConfigV2 with parameters about the tuning process.
            fw_impl: FrameworkImplementation object with a specific framework methods implementation.
            fw_info: Framework information
            representative_data_gen: Dataset to use for inputs of the models.
        """
        super().__init__(graph_float, graph_quant, gptq_config, fw_impl, fw_info, representative_data_gen)
        self.loss_list = []
        self.input_scale = 1
        if self.float_user_info.input_scale != self.gptq_user_info.input_scale:
            Logger.error("Input scale mismatch between float and GPTQ networks")  # pragma: no cover
        else:
            self.input_scale = self.gptq_user_info.input_scale

        trainable_weights, trainable_bias, trainable_threshold, trainable_temperature = get_gptq_trainable_parameters(
            self.fxp_model,
            add_bias=self.gptq_config.train_bias)

        self.flp_weights_list, self.fxp_weights_list = get_weights_for_loss(self.fxp_model)
        if not (len(self.compare_points) == len(trainable_weights) == len(self.flp_weights_list) == len(
                self.fxp_weights_list)):
            Logger.error(
                "GPTQ: Mismatch between number of compare points, number of layers with trainable weights " +
                "and number of float and quantized weights for loss")

        self.optimizer_with_param = self.get_optimizer_with_param(trainable_weights,
                                                                  trainable_bias,
                                                                  trainable_threshold)

        self.weights_for_average_loss = to_torch_tensor(self.compute_jacobian_based_weights(representative_data_gen))

    def _is_gptq_applicable(self,
                            node: BaseNode) -> bool:
        """
        A function for deciding if a layer should be fine-tuned during GPTQ.
        Args:
            node (BaseNode): Node for quantization decision
        Returns:
            A boolean whether the layer is to be wrapped with a Quantization Wrapper.
        """

        if node.is_weights_quantization_enabled() and not self.fw_info.is_kernel_op(node.type):
            Logger.error(f"GPTQ Error: Quantizing node {node.name} of type {node.type} "
                         f"without a kernel isn't supported.")
        return node.is_weights_quantization_enabled()

    def gptq_wrapper(self, n: BaseNode, layer: Module) -> Union[qi.PytorchQuantizationWrapper, Module]:
        """
        A function which takes a computational graph node and a pytorch layer and perform the quantization wrapping.

        Args:
            n: A node of mct graph.
            layer: A pytorch layer

        Returns: Wrapped layer if the layer should be wrap, otherwise returns the layer as is.
        """

        if self._is_gptq_applicable(n):
            weights_quantizers, activation_quantizers = quantization_builder(n, self.gptq_config)
            return qi.PytorchQuantizationWrapper(layer,
                                                 weights_quantizers=weights_quantizers,
                                                 activation_quantizers=activation_quantizers)
        else:
            return layer

    def build_gptq_model(self):
        """
        Build the GPTQ model with QuantizationWrappers
        Returns:
            Quantized graph for GPTQ fine-tuning, GPTQ graph user info
        """
        gptq_model, gptq_user_info = PyTorchModelBuilder(graph=self.graph_quant,
                                                         append2output=self.compare_points,
                                                         fw_info=self.fw_info,
                                                         wrapper=self.gptq_wrapper,
                                                         return_float_outputs=True).build_model()

        return gptq_model, gptq_user_info

    def train(self, representative_data_gen: Callable):
        """
          GPTQ Training using pytorch framework
          Args:
              representative_data_gen: Dataset generator to get images.
          Returns:
              Graph after GPTQ training
          """
        # Set Optimizers
        for (optimizer, params) in self.optimizer_with_param:
            optimizer.param_groups.clear()
            optimizer.add_param_group({'params': params})

        # Set models mode
        set_model(self.float_model, False)
        set_model(self.fxp_model, True)
        self._set_requires_grad()

        # ----------------------------------------------
        # Training loop
        # ----------------------------------------------
        self.micro_training_loop(representative_data_gen, self.gptq_config.n_epochs)

    def compute_gradients(self,
                          y_float: List[torch.Tensor],
                          input_tensors: List[torch.Tensor]) -> Tuple[torch.Tensor, List[np.ndarray]]:
        """
        Get outputs from both teacher and student networks. Compute the observed error,
        and use it to compute the gradients and applying them to the student weights.
        Args:
            y_float: A list of reference tensor from the floating point network.
            input_tensors: A list of Input tensors to pass through the networks.
        Returns:
            Loss and gradients.
        """

        # Forward-pass
        y_fxp = self.fxp_model(input_tensors)

        # Loss
        loss_value = self.gptq_config.loss(y_fxp,
                                           y_float,
                                           self.fxp_weights_list,
                                           self.flp_weights_list,
                                           self.compare_points_mean,
                                           self.compare_points_std,
                                           self.weights_for_average_loss)

        reg_value = self.gptq_config.quantizer_config.get_regularization_value(
            self.fxp_model,
            **{REGULARIZATION_VALUES: self._get_quantizer_regularization_values(self.gptq_config.rounding_type)})

        loss_value += reg_value

        # Back-pass
        loss_value.backward()

        # Get gradients
        grads = []
        for param in self.fxp_model.parameters():
            if param.requires_grad and param.grad is not None:
                grads.append(torch_tensor_to_numpy(param.grad))

        return loss_value, grads

    def micro_training_loop(self,
                            data_function: Callable,
                            n_epochs: int):
        """
        This function run a micro training loop on given set of parameters.
        Args:
            data_function: A callable function that give a batch of samples.
            n_epochs: Number of update iterations of representative dataset.
        """
        for _ in tqdm(range(n_epochs)):
            for data in tqdm(data_function()):
                input_data = [d * self.input_scale for d in data]
                input_tensor = to_torch_tensor(input_data)
                y_float = self.float_model(input_tensor)  # running float model
                loss_value, grads = self.compute_gradients(y_float, input_tensor)
                # Run one step of gradient descent by updating the value of the variables to minimize the loss.
                for (optimizer, _) in self.optimizer_with_param:
                    optimizer.step()
                    optimizer.zero_grad()
                if self.gptq_config.log_function is not None:
                    self.gptq_config.log_function(loss_value.item(),
                                                  torch_tensor_to_numpy(grads),
                                                  torch_tensor_to_numpy(self.optimizer_with_param[0][-1]))
                self.loss_list.append(loss_value.item())
                Logger.debug(f'last loss value: {self.loss_list[-1]}')

    def update_graph(self) -> Graph:
        """
        Update a graph using GPTQ after minimizing the loss between the float model's output
        and the quantized model's outputs.
        Returns:
            Updated graph after GPTQ.
        """
        graph_quant = copy.copy(self.graph_quant)

        # Update graph after training
        for name, layer in self.fxp_model.named_modules():
            if isinstance(layer, PytorchQuantizationWrapper):
                node = self.graph_quant.find_node_by_name(name)
                if len(node) != 1:
                    Logger.error(f"Can't update GPTQ graph due to missing layer named: {name}")
                node = node[0]
                kernel_attribute = get_kernel_attribute_name_for_gptq(layer_type=node.type,
                                                                      fw_info=self.fw_info)
                weights, weight_quant_config, activation_quant_config = \
                    layer.weights_quantizers[kernel_attribute].update_layer_quantization_params(layer)
                for weight_attr, weight in weights.items():
                    node.set_weights_by_keys(weight_attr, self.fw_impl.to_numpy(weight))
                for config_attr, config_value in weight_quant_config.items():
                    node.final_weights_quantization_cfg.set_quant_config_attr(config_attr, config_value)
                for config_attr, config_value in activation_quant_config.items():
                    node.final_activation_quantization_cfg.set_quant_config_attr(config_attr, config_value)
                if self.gptq_config.train_bias and hasattr(layer.layer, BIAS):
                    node.set_weights_by_keys(BIAS, self.fw_impl.to_numpy(getattr(layer.layer, BIAS)))

        return graph_quant

    def _set_requires_grad(self):
        """
        Set require_grad flag for trainable parameters for GPTQ training
        """
        # Float model: freeze all the parameters in the network
        for param in self.float_model.parameters():
            param.requires_grad = False

        # Fxp model: unfreeze bias trainable parameters
        for layer in self.fxp_model.modules():
            if isinstance(layer, PytorchQuantizationWrapper):
                if hasattr(layer.layer, BIAS):
                    bias = getattr(layer.layer, BIAS)
                    bias.requires_grad = self.gptq_config.train_bias

    def _get_quantizer_regularization_values(self, rounding_type: RoundingType) -> List[torch.Tensor]:
        """
        Mapping between a rounding type to its matching regularization method.

        Args:
            rounding_type: GPTQ rounding type.

        Returns: A regularization computation method.

        """
        if rounding_type == RoundingType.SoftQuantizer:
            return get_soft_rounding_reg(self.fxp_model)
        else:
            return []
