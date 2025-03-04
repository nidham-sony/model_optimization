# Copyright 2021 Sony Semiconductor Israel, Inc. All rights reserved.
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

from model_compression_toolkit.core.common.quantization.debug_config import DebugConfig
from model_compression_toolkit.gptq.common.gptq_config import GradientPTQConfig, RoundingType, GradientPTQConfigV2
from model_compression_toolkit.gptq.common.gptq_quantizer_config import GPTQQuantizerConfig, SoftQuantizerConfig
from model_compression_toolkit.core.common.quantization import quantization_config
from model_compression_toolkit.core.common.mixed_precision import mixed_precision_quantization_config
from model_compression_toolkit.core.common.quantization.quantization_config import QuantizationConfig, \
    QuantizationErrorMethod, DEFAULTCONFIG
from model_compression_toolkit.core.common.quantization.core_config import CoreConfig
from model_compression_toolkit.core.common import target_platform
from model_compression_toolkit.core.tpc_models.get_target_platform_capabilities import get_target_platform_capabilities
from model_compression_toolkit.core.common.mixed_precision.kpi_tools.kpi import KPI
from model_compression_toolkit.core.common.mixed_precision.mixed_precision_quantization_config import \
    MixedPrecisionQuantizationConfig, MixedPrecisionQuantizationConfigV2
from model_compression_toolkit.qat.common.qat_config import QATConfig, TrainingMethod
from model_compression_toolkit.core.common.logger import set_log_folder
from model_compression_toolkit.core.common.data_loader import FolderImageLoader
from model_compression_toolkit.core.common.framework_info import FrameworkInfo, ChannelAxis
from model_compression_toolkit.core.common.defaultdict import DefaultDict
from model_compression_toolkit.core.common import network_editors as network_editor

from model_compression_toolkit.core.keras.quantization_facade import keras_post_training_quantization, \
    keras_post_training_quantization_mixed_precision
from model_compression_toolkit.ptq.keras.quantization_facade import keras_post_training_quantization_experimental
from model_compression_toolkit.gptq.keras.quantization_facade import \
    keras_gradient_post_training_quantization_experimental
from model_compression_toolkit.gptq.keras.quantization_facade import get_keras_gptq_config
from model_compression_toolkit.qat.keras.quantization_facade import keras_quantization_aware_training_init, \
    keras_quantization_aware_training_finalize
from model_compression_toolkit.qat.pytorch.quantization_facade import pytorch_quantization_aware_training_init, \
    pytorch_quantization_aware_training_finalize
from model_compression_toolkit.core.pytorch.quantization_facade import pytorch_post_training_quantization, \
    pytorch_post_training_quantization_mixed_precision
from model_compression_toolkit.ptq.pytorch.quantization_facade import pytorch_post_training_quantization_experimental
from model_compression_toolkit.gptq.pytorch.quantization_facade import \
    pytorch_gradient_post_training_quantization_experimental
from model_compression_toolkit.gptq.pytorch.quantization_facade import get_pytorch_gptq_config

from model_compression_toolkit.core.keras.kpi_data_facade import keras_kpi_data, keras_kpi_data_experimental
from model_compression_toolkit.core.pytorch.kpi_data_facade import pytorch_kpi_data, pytorch_kpi_data_experimental

from model_compression_toolkit.quantizers_infrastructure.inferable_infrastructure.keras.load_model import keras_load_quantized_model

from model_compression_toolkit.exporter.model_exporter import tflite_export_model, TFLiteExportMode, keras_export_model, KerasExportMode, pytorch_export_model, PyTorchExportMode

__version__ = "1.8.0"
