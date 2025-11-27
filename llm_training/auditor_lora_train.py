"""
Colab-friendly LoRA fine-tuning script for the Corallo TaxOps Auditor LLM.

Dependencies (install in Colab or your GPU env, not added to project requirements):
!pip install torch transformers peft accelerate bitsandbytes tqdm
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_jsonl(path: str) -> List[Dict[str, str]]:
    """
    Load a JSONL file where each line is a dict with 'input' and 'output'.
    Skip empty lines. Raise a ValueError if the file is malformed.
    """
    records: List[Dict[str, str]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for idx, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Malformed JSON on line {idx} of {path}: {exc}") from exc
            if not isinstance(obj, dict) or "input" not in obj or "output" not in obj:
                raise ValueError(f"Line {idx} of {path} must contain 'input' and 'output'")
            records.append(obj)
    return records


def build_conversation_example(example: Dict[str, str]) -> str:
    """
    Take a training example with 'input' and 'output' and build a single
    text sequence for causal LM training.
    """
    return f"### Instruction:\n{example['input']}\n\n### Response:\n{example['output']}"


@dataclass
class TrainConfig:
    train_file: str
    val_file: Optional[str]
    base_model: str
    output_dir: str
    batch_size: int = 2
    grad_accum_steps: int = 8
    learning_rate: float = 2e-4
    max_steps: int = 500
    max_seq_len: int = 2048
    use_4bit: bool = False
    gradient_checkpointing: bool = False


def parse_args() -> TrainConfig:
    parser = argparse.ArgumentParser(description="LoRA fine-tuning for Corallo TaxOps Auditor.")
    parser.add_argument("--train-file", required=True, help="Path to training JSONL.")
    parser.add_argument("--val-file", help="Optional path to validation JSONL.")
    parser.add_argument("--base-model", required=True, help="HF model name or local path.")
    parser.add_argument("--output-dir", required=True, help="Directory to save LoRA adapter and tokenizer.")
    parser.add_argument("--batch-size", type=int, default=2, help="Per-device batch size.")
    parser.add_argument("--grad-accum-steps", type=int, default=8, help="Gradient accumulation steps.")
    parser.add_argument("--learning-rate", type=float, default=2e-4, help="Learning rate.")
    parser.add_argument("--max-steps", type=int, default=500, help="Total training steps.")
    parser.add_argument("--max-seq-len", type=int, default=2048, help="Max sequence length.")
    parser.add_argument("--use-4bit", action="store_true", help="Enable 4-bit loading (QLoRA style).")
    parser.add_argument(
        "--gradient-checkpointing",
        action="store_true",
        help="Enable gradient checkpointing to reduce memory usage.",
    )
    args = parser.parse_args()
    cfg = TrainConfig(
        train_file=args.train_file,
        val_file=args.val_file,
        base_model=args.base_model,
        output_dir=args.output_dir,
        batch_size=args.batch_size,
        grad_accum_steps=args.grad_accum_steps,
        learning_rate=args.learning_rate,
        max_steps=args.max_steps,
        max_seq_len=args.max_seq_len,
        use_4bit=args.use_4bit,
        gradient_checkpointing=args.gradient_checkpointing,
    )
    print("Training configuration:")
    for k, v in asdict(cfg).items():
        print(f"  {k}: {v}")
    return cfg


def main() -> None:
    cfg = parse_args()

    # Heavy imports kept inside main to avoid affecting environments without ML deps.
    import torch
    from torch.utils.data import Dataset
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
        default_data_collator,
    )
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    class TextDataset(Dataset):
        def __init__(self, texts: List[str]) -> None:
            self.texts = texts

        def __len__(self) -> int:
            return len(self.texts)

        def __getitem__(self, idx: int) -> str:
            return self.texts[idx]

    # Load data
    train_records = load_jsonl(cfg.train_file)
    train_texts = [build_conversation_example(rec) for rec in train_records]
    train_dataset = TextDataset(train_texts)

    eval_dataset = None
    if cfg.val_file:
        val_records = load_jsonl(cfg.val_file)
        val_texts = [build_conversation_example(rec) for rec in val_records]
        eval_dataset = TextDataset(val_texts)

    # Tokenizer
    tokenizer = AutoTokenizer.from_pretrained(cfg.base_model, use_fast=True)
    tokenizer.padding_side = "right"
    tokenizer.truncation_side = "right"
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def collate_fn(batch: List[str]) -> Dict[str, torch.Tensor]:
        encoded = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=cfg.max_seq_len,
            return_tensors="pt",
        )
        encoded["labels"] = encoded["input_ids"].clone()
        return encoded

    # Model
    model_kwargs: Dict[str, Any] = {}
    if cfg.use_4bit:
        model_kwargs.update(
            {
                "load_in_4bit": True,
                "bnb_4bit_quant_type": "nf4",
                "bnb_4bit_use_double_quant": True,
                "bnb_4bit_compute_dtype": torch.bfloat16 if torch.cuda.is_available() else torch.float16,
            }
        )
    model = AutoModelForCausalLM.from_pretrained(cfg.base_model, **model_kwargs)

    if cfg.use_4bit:
        model = prepare_model_for_kbit_training(model)

    if cfg.gradient_checkpointing and hasattr(model, "gradient_checkpointing_enable"):
        model.gradient_checkpointing_enable()
        if hasattr(model, "config"):
            model.config.use_cache = False

    lora_config = LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],  # tweak per-architecture if needed
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Training arguments
    bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    fp16 = torch.cuda.is_available() and not bf16
    import inspect

    training_kwargs = {
        "output_dir": cfg.output_dir,
        "per_device_train_batch_size": cfg.batch_size,
        "per_device_eval_batch_size": cfg.batch_size,
        "gradient_accumulation_steps": cfg.grad_accum_steps,
        "learning_rate": cfg.learning_rate,
        "max_steps": cfg.max_steps,
        "warmup_steps": max(1, int(0.03 * cfg.max_steps)),
        "logging_steps": 10,
        "save_steps": 100,
        "save_total_limit": 3,
        "fp16": fp16,
        "bf16": bf16,
        "report_to": [],
    }

    sig_params = set(inspect.signature(TrainingArguments.__init__).parameters.keys())
    if eval_dataset is not None:
        if "evaluation_strategy" in sig_params:
            training_kwargs["evaluation_strategy"] = "steps"
            training_kwargs["eval_steps"] = 100
        else:
            training_kwargs["do_eval"] = True
            training_kwargs["eval_steps"] = 100
    else:
        if "evaluation_strategy" in sig_params:
            training_kwargs["evaluation_strategy"] = "no"

    if cfg.gradient_checkpointing and "gradient_checkpointing" in sig_params:
        training_kwargs["gradient_checkpointing"] = True

    training_args = TrainingArguments(**training_kwargs)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=collate_fn,
    )

    trainer.train()

    Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(cfg.output_dir)
    tokenizer.save_pretrained(cfg.output_dir)

    cfg_path = Path(cfg.output_dir) / "training_args.json"
    with cfg_path.open("w", encoding="utf-8") as handle:
        json.dump(asdict(cfg), handle, indent=2)
    print(f"Saved adapter and tokenizer to {cfg.output_dir}")


if __name__ == "__main__":
    main()
