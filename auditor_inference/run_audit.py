import argparse
import json
from pathlib import Path
from typing import Any, Dict

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

from engine import rule_engine
from training_prep.formatter import format_auditor_prompt


def load_document(path: str | Path) -> Dict[str, Any]:
    """Load a single JSON document from file."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        doc = json.load(f)
    if not isinstance(doc, dict):
        raise ValueError(f"Document in {p} is not a JSON object")
    return doc


def select_device(device_arg: str) -> torch.device:
    """
    Resolve a device based on the device_arg:
      - 'auto': cuda if available else cpu
      - 'cuda': cuda (error if not available)
      - 'cpu': cpu
    """
    device_arg = device_arg.lower()
    if device_arg == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")

    if device_arg == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but not available.")
        return torch.device("cuda")

    if device_arg == "cpu":
        return torch.device("cpu")

    raise ValueError(f"Unknown device argument: {device_arg!r}")


def load_model_and_tokenizer(
    base_model: str,
    model_dir: str | Path,
    device: torch.device,
):
    """
    Load tokenizer from model_dir, base model from base_model, and
    attach LoRA adapter from model_dir using PeftModel.
    """
    model_dir = str(model_dir)

    tokenizer = AutoTokenizer.from_pretrained(model_dir, use_fast=True)
    if tokenizer.pad_token is None:
        # Many causal LMs have no explicit pad_token; use eos_token
        tokenizer.pad_token = tokenizer.eos_token

    dtype = torch.float16 if device.type == "cuda" else torch.float32

    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=dtype,
        device_map="auto" if device.type == "cuda" else None,
    )

    model = PeftModel.from_pretrained(base, model_dir)
    model.to(device)
    model.eval()

    return model, tokenizer


def generate_audit_output(
    model,
    tokenizer,
    prompt: str,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
    do_sample: bool,
    device: torch.device,
) -> str:
    """
    Run generation for the given prompt and return the decoded text.
    """
    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}

    gen_kwargs: Dict[str, Any] = {
        "max_new_tokens": max_new_tokens,
        "pad_token_id": tokenizer.eos_token_id,
    }

    if do_sample:
        gen_kwargs["do_sample"] = True
        gen_kwargs["temperature"] = float(temperature)
        gen_kwargs["top_p"] = float(top_p)
    else:
        gen_kwargs["do_sample"] = False

    with torch.no_grad():
        output_ids = model.generate(**inputs, **gen_kwargs)

    return tokenizer.decode(output_ids[0], skip_special_tokens=True)


def extract_json_array(text: str) -> Any:
    """
    Extract the FIRST JSON array from the model output.

    Strategy:
      - Find the first '['
      - Walk forward, and every time we see a ']' try to json.loads
        the substring [start:i]. The first one that parses is returned.
      - This tolerates extra text after the array (e.g. ### Meta: ...).
    """
    start = text.find("[")
    if start == -1:
        raise ValueError("No '[' found in completion output; cannot locate JSON array.")

    for i in range(start + 1, len(text) + 1):
        if text[i - 1] == "]":
            candidate = text[start:i]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                # Not a valid array yet, keep extending
                continue

    raise ValueError("Failed to parse any JSON array from completion output.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Corallo TaxOps Auditor LLM (LoRA) on a single document JSON."
    )

    parser.add_argument(
        "--model-dir",
        required=True,
        help="Path to LoRA adapter directory (outputs/auditor_mistral_lora).",
    )
    parser.add_argument(
        "--base-model",
        required=True,
        help="Base HF model name or path (e.g. mistralai/Mistral-7B-v0.1).",
    )
    parser.add_argument(
        "--doc-file",
        required=True,
        help="Path to JSON file with a single document dict.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=512,
        help="Maximum number of new tokens to generate.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="Sampling temperature (used only if --do-sample).",
    )
    parser.add_argument(
        "--top-p",
        type=float,
        default=0.9,
        help="Top-p nucleus sampling (used only if --do-sample).",
    )
    parser.add_argument(
        "--do-sample",
        action="store_true",
        help="Enable sampling instead of greedy decoding.",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Device to use: auto | cuda | cpu (default: auto).",
    )

    args = parser.parse_args()

    print("=== Auditor Inference Configuration ===")
    print(f"model_dir        : {args.model_dir}")
    print(f"base_model       : {args.base_model}")
    print(f"doc_file         : {args.doc_file}")
    print(f"max_new_tokens   : {args.max_new_tokens}")
    print(f"temperature      : {args.temperature}")
    print(f"top_p            : {args.top_p}")
    print(f"do_sample        : {args.do_sample}")
    print(f"device           : {args.device}")
    print("=======================================")

    device = select_device(args.device)
    print(f"Using device: {device}\n")

    # 1. Load document
    doc = load_document(args.doc_file)
    rule_results = rule_engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))

    # 2. Build training-style prompt
    instruction = format_auditor_prompt(doc)
    prompt = f"### Instruction:\n{instruction}\n\n### Response:\n"

    print("=== PROMPT PREVIEW (first 800 chars) ===")
    print(prompt[:800])
    print("\n")

    # 3. Load model + tokenizer
    model, tokenizer = load_model_and_tokenizer(
        base_model=args.base_model,
        model_dir=args.model_dir,
        device=device,
    )

    # 4. Generate output
    full_output = generate_audit_output(
        model=model,
        tokenizer=tokenizer,
        prompt=prompt,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        do_sample=args.do_sample,
        device=device,
    )

    print("=== RAW MODEL OUTPUT (truncated) ===")
    print(full_output[:2000])
    print("\n")

    # 5. Strip prompt prefix to isolate completion
    if full_output.startswith(prompt):
        completion = full_output[len(prompt) :].strip()
    else:
        completion = full_output.strip()

    print("=== COMPLETION (model answer) ===")
    print(completion[:2000])
    print("\n")

    # 6. Try to parse JSON array of findings
    try:
        findings = extract_json_array(completion)
    except Exception as exc:  # noqa: BLE001
        print("Failed to parse JSON array from completion:")
        print(repr(exc))
        findings = []

    merged = []
    if isinstance(findings, list):
        merged.extend(findings)
    merged.extend(rule_results)

    final_payload = {
        "rule_issues": rule_results,
        "llm_findings": findings,
        "merged_findings": merged,
        "metadata": {
            "doc_id": doc.get("doc_id"),
            "doc_type": doc.get("doc_type"),
            "tax_year": doc.get("tax_year"),
            "prompt_preview": prompt[:500],
        },
    }

    print("=== RULE ENGINE FINDINGS ===")
    print(json.dumps(rule_results, indent=2, ensure_ascii=False))

    print("=== FINAL PAYLOAD ===")
    print(json.dumps(final_payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
