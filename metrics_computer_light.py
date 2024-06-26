from pathlib import Path
from metrics.intrinisic_dimension import IntrinsicDimension
from metrics.utils import TensorStorageManager, DataFrameQuery
from common.globals_vars import _OUTPUT_DIR_TRANSPOSED
from enum import Enum
from common.utils import *

import argparse
import importlib
import logging
from logging_utils.logging_config import setup_logging

import pdb
import datetime
now = datetime.datetime.now()

def set_log_name():
    job_name = os.getenv('SLURM_JOB_NAME')
    if job_name:
        return job_name
    else: 
        return f"metrics_{now.hour}{now.minute}{now.second}"

logger = setup_logging(set_log_name())


class MetricName(Enum):
    INTRINSIC_DIMENSION = ("metrics.intrinisic_dimension", "IntrinsicDimension")
    LABEL_OVERLAP = ("metrics.overlap", "LabelOverlap")
    POINT_OVERLAP = ("metrics.overlap", "PointOverlap")
    PROBE = ("metrics.probe", "LinearProbe")


def metric_function(name):
    try:
        metric_info = MetricName[name.upper()].value
        module = importlib.import_module(metric_info[0])
        return getattr(module, metric_info[1])
    except KeyError:
        raise ValueError(f"Unknown metric function {name}")
    except AttributeError:
        raise ImportError(f"Could not import the specified class from the module")


def create_queries(models):
    queries = []
    for model in models:
        for shot in [0, 2, 5]:
            if "70" in model and shot == 5 and "chat" not in model:
                shot = 4
            elif "70" in model and "chat" in model and shot == 5:
                continue
            queries.append(
                {"method": "last", "model_name": model, "train_instances": shot}
            )
    return queries


def main():
    # Getting commandline arguments
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--conf-path", help="Path to configuration file", required=False
    )
    args, remaining_argv = parser.parse_known_args()
    if args.conf_path:
        # Load arguments from config file
        config_args = read_config(args.conf_path)

        # Update the parser with new arguments from config file
        parser.set_defaults(**config_args)

    parser.add_argument(
        "--models",
        nargs="+",
        action="append",
        type=str,
        help="Model from which we take the hidden states",
    )
    parser.add_argument(
        "--metrics",
        nargs="+",
        action="append",
        type=str,
        help="Which metric to compute",
    )
    parser.add_argument(
        "--variations", action="append", type=str, help="Variations applied"
    )
    parser.add_argument(
        "--labels",
        nargs="+",
        action="append",
        type=str,
        help="Which ground truth to probe",
    )
    args = parser.parse_args(remaining_argv)
    print(args.variations)

    models = args.models
    metrics = args.metrics
    labels = args.labels
    variations = json.loads(args.variations)

    logger.info(
        f"Metrics computer started\nModels:{models}\nMetrics:{metrics}\nVariations:{variations}"
    )

    # models = [
    #    "meta-llama-Llama-2-7b-hf",
    #    "meta-llama-Llama-2-7b-chat-hf",
    #    "meta-llama-Llama-2-13b-hf",
    #    "meta-llama-Llama-2-13b-chat-hf",
    #    "meta-llama-Llama-2-70b-hf",
    #    "meta-llama-Llama-2-70b-chat-hf",
    #    "meta-llama-Llama-3-8b-hf",
    #    "meta-llama-Llama-3-8b-chat-hf",
    #    "meta-llama-Llama-3-70b-hf",
    #    "meta-llama-Llama-3-70b-chat-hf",
    #    "meta-llama-Llama-3-8b-ft-hf",
    # ]

    ## List of variations to apply
    # variations = {
    #    "intrinsic_dimension": "None",
    #    "point_overlap": "cosine",
    #    "label_overlap": "balanced_letter",
    #    "cka": "rbf",
    # }

    # List of metrics to compute
    # metrics = ["intrinsic_dimension", "probe", "label_overlap"]
    for metric in metrics:
        metric_class = metric_function(metric)

        # Create queries for hidden states
        queries = create_queries(models)
        metric_instance = metric_class(
            queries=queries,
            tensor_storage=None,
            variations=variations,
            storage_logic="npy",
        )
        try:
            # Probing like metrics require ground truth
            if metric == "probe" or metric == "label_overlap":
                if not labels:
                    raise ValueError(
                        "Probe and LabelOverlap metrics require a label to be specified"
                    )
                for label_iter in labels:
                    result = metric_instance.main(label=label_iter)

                    result_path = (
                        _OUTPUT_DIR_TRANSPOSED / "result" / f"{metric}_{label_iter}.pkl"
                    )
                    result.to_pickle(result_path)
            else:
                result = metric_instance.main()
                result_path = _OUTPUT_DIR_TRANSPOSED / "result" / f"{metric}.pkl"
                result.to_pickle(result_path)

            logging.info(f"Metric {metric} computed successfully")
        except Exception as e:
            logger.error(f"Error computing metric {metric}: {e}")


if __name__ == "__main__":
    main()
