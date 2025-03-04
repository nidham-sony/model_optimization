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
from typing import Dict, Any, Union

from model_compression_toolkit.core.common import Logger
from model_compression_toolkit.core.common.constants import FOUND_TF

from model_compression_toolkit.quantizers_infrastructure.trainable_infrastructure.common.base_trainable_quantizer import BaseTrainableQuantizer
from model_compression_toolkit.quantizers_infrastructure import TrainableQuantizerWeightsConfig, \
    TrainableQuantizerActivationConfig

if FOUND_TF:
    QUANTIZATION_CONFIG = 'quantization_config'
    from model_compression_toolkit.quantizers_infrastructure.trainable_infrastructure.keras.config_serialization import config_serialization, \
        config_deserialization


    class BaseKerasTrainableQuantizer(BaseTrainableQuantizer):
        def __init__(self,
                     quantization_config: Union[TrainableQuantizerWeightsConfig, TrainableQuantizerActivationConfig]):
            """
            This class is a base quantizer which validates provided quantization config and defines an abstract function which any quantizer needs to implement.
            This class adds to the base quantizer a get_config and from_config functions to enable loading and saving the keras model.
            Args:
                quantization_config: quantizer config class contains all the information about a quantizer configuration.
            """
            super().__init__(quantization_config)

        def get_config(self) -> Dict[str, Any]:
            """

            Returns: Configuration of BaseKerasQuantizer.

            """
            return {QUANTIZATION_CONFIG: config_serialization(self.quantization_config)}

        @classmethod
        def from_config(cls, config: dict):
            """

            Args:
                config(dict): dictonory  of  BaseKerasQuantizer Configuration

            Returns: A BaseKerasQuantizer

            """
            config = config.copy()
            quantization_config = config_deserialization(config[QUANTIZATION_CONFIG])
            # Note that a quantizer only receive quantization config and the rest of define hardcoded inside the speficie quantizer.
            return cls(quantization_config=quantization_config)

else:
    class BaseKerasTrainableQuantizer(BaseTrainableQuantizer):
        def __init__(self,
                     quantization_config: Union[TrainableQuantizerWeightsConfig, TrainableQuantizerActivationConfig]):

            super().__init__(quantization_config)
            Logger.critical('Installing tensorflow and tensorflow_model_optimization is mandatory '
                            'when using BaseKerasQuantizer. '
                            'Could not find Tensorflow package.')  # pragma: no cover
