import numpy as np
from pandas.core.api import DataFrame as DataFrame
import torch

from dataclasses import dataclass
from typing import List, Type
from .utils import  Match

import tqdm

import pandas as pd
from collections import namedtuple

from common.metadata_db import MetadataDB
from dataclasses import asdict

from .hidden_states import HiddenStates
from enum import Enum
from .query import DataFrameQuery
from pathlib import Path
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

#Define a type hint 
Array = Type[np.ndarray]
Tensor = Type[torch.Tensor]

class Match(Enum):
    CORRECT = "correct"
    WRONG = "wrong"
    ALL = "all"
class Layer(Enum):
    LAST = "last"
    SUM = "sum"
    
class Metrics():
    def __init__(self, db: MetadataDB, metrics_list: List, path_result: Path) -> None:
      self.db = db
      self.metrics_list = metrics_list
      self.df = self.set_dataframes()
      self.path_result = path_result
      self.tensor_path = Path(path_result, "tensor_files")
    
    def set_dataframes(self) -> pd.DataFrame:
      """
      Aggregate in a dataframe the hidden states of all instances
      ----------
      hidden_states: pd.DataFrame(num_instances, num_layers, model_dim)
      """
      df = pd.read_sql("SELECT * FROM metadata", self.db.conn)
      df["train_instances"] = df["train_instances"].astype(str)
      df.drop(columns=["id"],inplace = True)
      df.drop_duplicates(subset = ["id_instance"],inplace = True, ignore_index = True) # why there are duplicates???
      return df
        
    def evaluate(self) -> List[pd.DataFrame]:
      """
      Compute all the implemented metrics
      Output
      ----------
      pandas DataFrame
      """
      df_out = {}
      for metric in tqdm.tqdm(self.metrics_list, desc = "Computing metrics"):
        logging.info(f'Computing {metric}...')
        out = self._compute_metric(metric)
        out.to_pickle(Path(self.path_result,f'{metric.replace(":","_")}.pkl'))
        
      return df_out
    
    def _compute_metric(self, metric) -> pd.DataFrame:
      if metric == "shot_metric":
        return self.shot_metrics()
      elif metric == "letter_overlap":
        return self._compute_letter_overlap()
      elif metric == "subject_overlap":
        return self._compute_subject_overlap()
      elif metric == "letter_overlap_cluster":
        return self._compute_letter_overlap_cluster() 
      elif metric == "subject_overlap_cluster":
        return self._compute_subject_overlap_cluster()  
      elif metric == "base_finetune_overlap":
        return self._compute_base_finetune_overlap()
      elif metric == "intrinsic_dim":
        return self._compute_intrinsic_dim()
      elif metric == "last_layer_id_diff":
        return self._compute_layer_id_diff()
      else:
        raise NotImplementedError
    
    def _compute_letter_overlap_cluster(self) -> pd.DataFrame:
      hidden_states = HiddenStates(self.df, self.tensor_path)
      return hidden_states.clustering_label(label = "only_ref_pred")
    
    def _compute_subject_overlap_cluster(self) -> pd.DataFrame:
      hidden_states = HiddenStates(self.df, self.tensor_path)
      return hidden_states.clustering_label(label = "dataset")
    
    def _compute_layer_id_diff(self):
      shot_metric_path = Path(self.path_result, 'shot_metric.pkl')
      id_path = Path(self.path_result, 'intrinsic_dim.pkl')
      try:
        shot_metrics_df = pd.read_pickle(shot_metric_path)
        id_df = pd.read_pickle(id_path)
      except FileNotFoundError:
        print("You need to computer intrinisic dimension and shot metrics first")
      return self.get_last_layer_id_diff(id_df, shot_metrics_df)
    
    def _compute_letter_overlap(self, condition=None) -> pd.DataFrame:
      hidden_states = HiddenStates(self.df, self.tensor_path)
      return hidden_states.label_overlap(balanced = condition,label = "only_ref_pred")
    
    def _compute_letter_overlap_temporary(self) -> pd.DataFrame:
      hidden_states = HiddenStates(self.df, self.tensor_path)
      return hidden_states.letter_overlap()
    
    def _compute_subject_overlap(self, condition=None) -> pd.DataFrame:
      hidden_states = HiddenStates(self.df, self.tensor_path)
      return hidden_states.label_overlap(balanced = condition, label="dataset")
    
    def _compute_intrinsic_dim(self) -> pd.DataFrame:
      hidden_states = HiddenStates(self.df, self.tensor_path)
      return hidden_states.intrinsic_dim()

    def shot_metrics(self):
      """
      Compute all the implemented metrics
      Output
      ----------
      InstanceResult object
      """
      hidden_states = HiddenStates(self.df, self.tensor_path)
      return hidden_states.shot_metrics()
    
    def _compute_base_finetune_overlap(self) -> pd.DataFrame:
      hidden_states = HiddenStates(self.df, self.tensor_path)
      return hidden_states.point_overlap()
    
    
    def get_last_layer_id_diff(self, id_df, shot_metrics_df) -> pd.DataFrame:
      """
      Compute the difference in ID between the last layer of two runs
      Output
      ----------
      Dict[layer: List[Array(num_layers, num_layers)]]
      """
      # The last token is always the same, thus its first layer activation (embedding) is always the same
      rows = []
      shot_metrics_df.drop(["dataset"], axis=1, inplace=True)
      shot_metrics_df= shot_metrics_df.groupby(['train_instances','model']).mean().reset_index()
      query_template = {"match": "all",
                  "method": "last"}
      query = DataFrameQuery(query_template)
      id_df = query.apply_query(id_df)
      df = pd.merge(id_df,shot_metrics_df, on=['train_instances','model'], how='inner')
      return df
      
  

  
  
