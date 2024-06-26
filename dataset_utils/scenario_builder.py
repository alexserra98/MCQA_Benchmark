import os
from dataclasses import dataclass, field
from typing import Any, Dict, List
from datasets import load_dataset
import random
from tqdm import tqdm
import string
from abc import ABC, abstractmethod
import random

_TMP = True
_KNOWN_DATASET_ALIASES: Dict[str, str] = {
    "mmlu": "Stevross/mmlu",
    "commonsenseqa": "tau/commonsense_qa"
}
def map_aliases(dataset):
    if len(dataset.split(":"))==2:
        dataset = f'{_KNOWN_DATASET_ALIASES.get(dataset.split(":")[0],dataset.split(":")[0])}:{dataset.split(":")[1]}'
    return dataset


@dataclass
class RequestInstance():
    question: str
    prompt: str
    letter_gold: str
    token_gold: int = None


@dataclass
class Scenario():
    dataset: str
    shots: int
    model_name: str
    requests_instances: List[RequestInstance] = field(default_factory=list)
    output_mapping: List[str] = field(default_factory=dict)
    

        
class ScenarioBuilder(ABC):
    """
    Abstract class for building a scenario.
    
    :param shots: The number of shots to include in the prompt
    :param model_name: The name of the model to use
    :param number_of_instances: The number of instances from the orginal dataset to include in the scenario
    :method retrieve_dataset: Retrieve the dataset from the Huggingface library
    :method construct_request_instance: Construct the request instances with prompt and metadata
    :method build: Build the scenario
    """
    
    def __init__(self, shots, model_name, number_of_instances = -1):
        self.shots = shots
        self.model_name = model_name
        self.number_of_instances = number_of_instances
        
    
    def retrieve_dataset(self):
        """
        Retrieve the dataset from the Huggingface library
        """
        dataset_name = list(self.dataset.split(":", 1) if ":" in self.dataset else (self.dataset,))
        dataset_name[0]=_KNOWN_DATASET_ALIASES.get(dataset_name[0],dataset_name[0])
        try:
            dataset = load_dataset(*dataset_name, trust_remote_code=True)
        except Exception as e:
            error : str = f'Huggingface error {e}, peraphs you didnt specify the subdataset?'
            raise ValueError(error)
        return dataset
    
    @abstractmethod
    def construct_request_instance(self) -> List[RequestInstance]:
        """
        Construct the request instances object from scenario instances
        """
        raise NotImplementedError
    

    def build(self) -> Scenario:
        """
        Build the scenario object
        """
        self.requests_instances, output_mapping = self.construct_request_instance()
        print(f'Example of prompt: {self.requests_instances[0].prompt}')
  
        return Scenario(self.dataset, 
                        self.shots, 
                        self.model_name, 
                        self.requests_instances,
                        output_mapping 
                        )
    
