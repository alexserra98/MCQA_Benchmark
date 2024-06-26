import os
from pathlib import Path
import argparse
import logging
from dataset_utils.scenario_adapter import ScenarioAdapter
from generation.generation import Huggingface_client
from common.metadata_db import MetadataDB
from common.tensor_storage import TensorStorage
import common.globals_vars as g
from common.utils import *
from safetensors.numpy import save_file
import gc
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s-%(message)s')


working_path = Path(os.getcwd())

#Getting commandline arguments
parser = argparse.ArgumentParser()
parser.add_argument('--conf-path', help='Path to configuration file', required=False)
args, remaining_argv = parser.parse_known_args()

if args.conf_path:
    # Load arguments from config file
    config_args = read_config(args.conf_path)

    # Update the parser with new arguments from config file
    parser.set_defaults(**config_args)   

parser.add_argument('--dataset-folder', type=str, help='The name of the dataset folder')
parser.add_argument('--model-name',nargs='+', action='append', type=str, help='The name of the model')
parser.add_argument('--dataset',  nargs='+', action='append', type=str, help='The name of the dataset')
parser.add_argument('--shots-list', type=int, nargs='+',  action='append',help='The name of the output directory')

args = parser.parse_args(remaining_argv)
# Now you can use args.model_name to get the model name
dataset_folder = args.dataset_folder
models_names = args.model_name
datasets = args.dataset
shots_list = args.shots_list
print(f"Starting inference on {dataset_folder} with {models_names} and {datasets} with {shots_list} number of shots")


# Getting the dataset
# find files inside datasets that contain the name of the dataset
logging.info("Getting the datasets...")

# Instantiating model and tokenizer



_TENSOR_FILE = "tensor_files"
result_path = Path(g._OUTPUT_DIR, f'{dataset_folder}_result')
result_path.mkdir(parents=True, exist_ok=True)
metadata_db = MetadataDB(Path(result_path,'metadata.db'))
tensor_storage = TensorStorage(Path(result_path,_TENSOR_FILE))

for model_name in models_names:
    logging.info("Loading model and tokenizer...")
    client = Huggingface_client(model_name)
    model_path = Path(Path(result_path,_TENSOR_FILE), model_name.replace("/","-"))
    model_path.mkdir(exist_ok=True,parents=True)
    for dataset in datasets:
        db_rows = []
        dataset_path = Path(model_path,dataset)
        dataset_path.mkdir(exist_ok=True,parents=True)
        
        
        for num_of_shots in shots_list:
            logging.info("Starting inference on %s with %s number of shots...",
                        dataset, num_of_shots)
            scenario_builder = ScenarioAdapter(dataset_folder,dataset,num_of_shots,model_name,-1)
            #dataset construction
            scenario = scenario_builder.build()

            #representation extraction
            hidden_states_rows_i, logits_rows_i, db_rows_i = client.make_request(scenario,metadata_db)
            
            # Skipping if already cached

            if not hidden_states_rows_i or not logits_rows_i  or not db_rows_i:
                logging.info("Skipping inference on %s with %s train instances...",
                        dataset, shots_list)
                continue
            
            # Saving tensors
            tensor_path = Path(dataset_path,str(num_of_shots))
            tensor_path.mkdir(exist_ok=True,parents=True)
            tensor_storage.save_tensors(hidden_states_rows_i.values(),hidden_states_rows_i.keys(), f'{model_name.replace("/","-")}/{dataset}/{num_of_shots}/hidden_states')
            tensor_storage.save_tensors(logits_rows_i.values(),logits_rows_i.keys(),f'{model_name.replace("/","-")}/{dataset}/{num_of_shots}/logits')
            
            db_rows.extend(db_rows_i)
            
            # Free memory
            del hidden_states_rows_i
            del logits_rows_i
            gc.collect()
            
        logging.info("Saving run results..")
        metadata_db.add_metadata(db_rows)

        

logging.info("Closing...")

metadata_db.close()
