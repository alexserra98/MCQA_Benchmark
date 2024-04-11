import os
import time
import torch
import numpy as np
from torch.utils.data import DataLoader
from collections import defaultdict
from intrinsic_dimension.pairwise_distances import compute_distances
from intrinsic_dimension.extract_activations import extract_activations
from transformers import PreTrainedModel, LlamaTokenizer
import sys
from accelerate import Accelerator
import pickle


def get_embdims(model, dataloader, target_layers):
    embdims = defaultdict(lambda: None)
    dtypes = defaultdict(lambda: None)

    def get_hook(name, embdims):
        def hook_fn(module, input, output):
            embdims[name] = output.shape[-1]
            dtypes[name] = output.dtype

        return hook_fn

    handles = {}
    for name, module in model.named_modules():
        if name in target_layers:
            handles[name] = module.register_forward_hook(get_hook(name, embdims))

    batch = next(iter(dataloader))
    sys.stdout.flush()
    _ = model(batch["input_ids"].to("cuda"))

    for name, module in model.named_modules():
        if name in target_layers:
            handles[name].remove()

    assert len(embdims) == len(target_layers)
    return embdims, dtypes


def compute_accuracy(predictions, answers):

    # ground_truths is an array of letters, without trailing spaces
    # predictions is an array of tokens

    # we remove spaces in from of the letters
    tot_ans = len(predictions)
    num_correct = 0
    for pred, ans in zip(predictions, answers):
        if pred == ans:
            num_correct += 1
    return num_correct / tot_ans


@torch.inference_mode()
def compute_id(
    accelerator: Accelerator,
    model: PreTrainedModel,
    dataloader: DataLoader,
    tokenizer: LlamaTokenizer,
    target_layers: dict,
    maxk=50,
    dirpath=".",
    filename="",
    use_last_token=False,
    remove_duplicates=True,
    save_distances=True,
    save_repr=False,
    print_every=100,
):
    model = model.eval()
    if accelerator.is_main_process:
        dirpath = str(dirpath).lower()
        os.makedirs(dirpath, exist_ok=True)

    if use_last_token:
        filename = f"{filename}_target"
    else:
        filename = f"{filename}_mean"

    target_layer_names = list(target_layers.values())
    target_layer_labels = list(target_layers.keys())
    accelerator.print("layer_to_extract: ", target_layer_labels)
    embdims, dtypes = get_embdims(model, dataloader, target_layer_names)

    start = time.time()
    extr_act = extract_activations(
        accelerator,
        model,
        dataloader,
        target_layer_names,
        embdims,
        dtypes,
        use_last_token=use_last_token,
        print_every=print_every,
    )
    extr_act.extract(dataloader, tokenizer)
    accelerator.print(f"num_tokens: {extr_act.hidden_size/10**3}k")
    accelerator.print((time.time() - start) / 3600, "hours")

    if accelerator.is_main_process:

        predictions = extr_act.predictions
        constrained_predictions = extr_act.constrained_predictions
        processed_labels = extr_act.targets

        ground_truths = dataloader.dataset["labels"]
        assert torch.all(ground_truths == processed_labels), (
            processed_labels,
            ground_truths,
        )

        answers = dataloader.dataset["answers"]

        answers = np.array([ans.strip() for ans in answers])
        predictions = np.array([tokenizer.decode(pred).strip() for pred in predictions])
        constrained_predictions = np.array(
            [tokenizer.decode(pred).strip() for pred in constrained_predictions]
        )

        acc_pred = compute_accuracy(predictions, answers)
        acc_constrained = compute_accuracy(constrained_predictions, answers)
        accelerator.print("exact_match constrained:", acc_constrained)
        accelerator.print("exact_match:", acc_pred)

        statistics = {
            "subjects": dataloader.dataset["subjects"],
            "answers": answers,
            "predictions": predictions,
            "contrained_predictions": constrained_predictions,
            "accuracy": acc_pred,
            "constrained_accuracy": acc_constrained,
        }

        with open(f"{dirpath}/statistics.pkl", "wb") as f:
            pickle.dump(statistics, f)

        act_dict = extr_act.hidden_states
        for i, (layer, act) in enumerate(act_dict.items()):
            if save_repr:
                torch.save(act, f"{dirpath}/l{target_layer_labels[i]}{filename}.pt")

            act = act.to(torch.float64).numpy()

            save_backward_indices = False
            if remove_duplicates:
                act, idx, inverse = np.unique(
                    act, axis=0, return_index=True, return_inverse=True
                )
                accelerator.print(len(idx), len(inverse))
                if len(idx) == len(inverse):
                    # if no overlapping data has been found return the original ordred array
                    assert len(np.unique(inverse)) == len(inverse)
                    act = act[inverse]
                else:
                    save_backward_indices = True
                accelerator.print(f"num_duplicates = {len(inverse)-len(idx)}")

            accelerator.print(f"{layer} act_shape {act.shape}")
            sys.stdout.flush()

            n_samples = act.shape[0]
            range_scaling = min(1050, n_samples - 1)
            maxk = min(maxk, n_samples - 1)

            start = time.time()
            distances, dist_index, mus, _ = compute_distances(
                X=act,
                n_neighbors=maxk + 1,
                n_jobs=1,
                working_memory=2048,
                range_scaling=range_scaling,
                argsort=False,
            )
            accelerator.print((time.time() - start) / 60, "min")

            if save_distances:
                np.save(
                    f"{dirpath}/l{target_layer_labels[i]}{filename}_dist", distances
                )
                np.save(
                    f"{dirpath}/l{target_layer_labels[i]}{filename}_index", dist_index
                )
            if save_backward_indices:
                np.save(
                    f"{dirpath}/l{target_layer_labels[i]}{filename}_inverse", inverse
                )
            np.save(f"{dirpath}/l{target_layer_labels[i]}{filename}_mus", mus)