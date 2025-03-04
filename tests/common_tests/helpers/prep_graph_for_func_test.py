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
import numpy as np

from model_compression_toolkit import DEFAULTCONFIG, CoreConfig, DebugConfig
from model_compression_toolkit.core.common.mixed_precision.bit_width_setter import set_bit_widths
from model_compression_toolkit.core.common.mixed_precision.mixed_precision_search_facade import search_bit_width
from model_compression_toolkit.core.common.model_collector import ModelCollector
from model_compression_toolkit.core.common.quantization.quantization_analyzer import analyzer_graph
from model_compression_toolkit.core.common.quantization.quantization_params_generation.qparams_computation import \
    calculate_quantization_params
from model_compression_toolkit.core.runner import get_finalized_graph, read_model_to_graph, _init_tensorboard_writer, \
    _prepare_model_for_quantization

from model_compression_toolkit.core.tpc_models.default_tpc.latest import generate_tp_model, \
    get_op_quantization_configs

import model_compression_toolkit as mct

tp = mct.target_platform


def prepare_graph_with_configs(in_model, fw_impl, fw_info, representative_dataset, get_tpc_func,
                               qc=DEFAULTCONFIG, mixed_precision_enabled=False):
    # TPC
    base_config, op_cfg_list = get_op_quantization_configs()

    # To override the default TP in the test - pass a TPC generator function that includes a generation of the TP
    # and doesn't use the TP that is passed from outside.
    _tp = generate_tp_model(base_config, base_config, op_cfg_list, "function_test")
    tpc = get_tpc_func("function_test", _tp)

    # Read Model
    graph = read_model_to_graph(in_model,
                                representative_data_gen=representative_dataset,
                                tpc=tpc,
                                fw_info=fw_info,
                                fw_impl=fw_impl)

    # Finalize graph with quantization configs
    graph = get_finalized_graph(graph,
                                tpc=tpc,
                                quant_config=qc,
                                fw_info=fw_info,
                                fw_impl=fw_impl,
                                mixed_precision_enable=mixed_precision_enabled)

    return graph


def prepare_graph_with_quantization_parameters(in_model, fw_impl, fw_info, representative_dataset, get_tpc_func,
                                               input_shape, qc=DEFAULTCONFIG, mixed_precision_enabled=False):
    graph = prepare_graph_with_configs(in_model, fw_impl, fw_info, representative_dataset, get_tpc_func,
                                       qc, mixed_precision_enabled)

    analyzer_graph(node_analyze_func=fw_impl.attach_sc_to_node,
                   graph=graph,
                   fw_info=fw_info,
                   qc=qc)

    mi = ModelCollector(graph,
                        fw_impl=fw_impl,
                        fw_info=fw_info)

    for i in range(10):
        mi.infer([np.random.randn(*input_shape)])

    calculate_quantization_params(graph,
                                  fw_info=fw_info,
                                  fw_impl=fw_impl)

    return graph


def prepare_graph_set_bit_widths(in_model,
                                 fw_impl,
                                 representative_data_gen,
                                 target_kpi,
                                 n_iter,
                                 quant_config,
                                 fw_info,
                                 network_editor,
                                 analyze_similarity,
                                 tpc):

    # Config
    quantization_config, mp_config = quant_config.separate_configs()
    core_config = CoreConfig(quantization_config=quantization_config,
                             mixed_precision_config=mp_config,
                             debug_config=DebugConfig(analyze_similarity=analyze_similarity,
                                                      network_editor=network_editor))

    tb_w = _init_tensorboard_writer(fw_info)

    # convert old representative dataset generation to a generator
    def _representative_data_gen():
        for _ in range(n_iter):
            yield representative_data_gen()

    graph = read_model_to_graph(in_model,
                                _representative_data_gen,
                                tpc,
                                fw_info,
                                fw_impl)

    tg = _prepare_model_for_quantization(graph,
                                         _representative_data_gen,
                                         tpc,
                                         core_config,
                                         fw_info,
                                         tb_w,
                                         fw_impl)

    ######################################
    # Finalize bit widths
    ######################################
    if target_kpi is not None:
        assert core_config.mixed_precision_enable
        if core_config.mixed_precision_config.configuration_overwrite is None:

            bit_widths_config = search_bit_width(tg,
                                                 fw_info,
                                                 fw_impl,
                                                 target_kpi,
                                                 core_config.mixed_precision_config,
                                                 _representative_data_gen)
        else:
            bit_widths_config = core_config.mixed_precision_config.configuration_overwrite

    else:
        bit_widths_config = []

    tg = set_bit_widths(core_config.mixed_precision_enable,
                        tg,
                        bit_widths_config)

    return tg
