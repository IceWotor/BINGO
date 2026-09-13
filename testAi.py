from transformers import AutoTokenizer, AutoModelForCausalLM

model_name = "Qwen/Qwen3-0.6B"

tokenizer = AutoTokenizer.from_pretrained(model_name)

model = AutoModelForCausalLM.from_pretrained(
    model_name,
    device_map="auto"
)

ocr_text = "Cinematography the art or science of [MASK] in a visual [MASK] (as for movies, television, or video games)"

messages = [
    {
        "role": "user",
        "content": f"""Correct the OCR errors in this text.

You are an OCR text reconstruction system for academic material.

Your task is to reconstruct corrupted OCR text using the provided
term and definition as context.

TERM:
Photosynthesis

DEFINITION:
The process by which plants convert light energy into chemical energy.

OCR TEXT:
Photosynthsis is the procss by wich plants cnvert lght energy into chemcal energy.

Instructions:
1. Identify the academic term.
2. Understand the definition.
3. Use the term and definition to determine what the corrupted words
   are supposed to be.
4. Correct spelling and obvious OCR errors.
5. Preserve the original meaning.
6. Do not add information that is not supported by the provided text.
7. Return only the reconstructed text.
8. Every [MASK] is a missing word, replace those with the missing words.

RECONSTRUCTED TEXT:
{ocr_text}"""
    }
]

text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
    enable_thinking=False
)

inputs = tokenizer(
    [text],
    return_tensors="pt"
).to(model.device)

outputs = model.generate(
    **inputs,
    max_new_tokens=100
)

result = tokenizer.decode(
    outputs[0][inputs["input_ids"].shape[-1]:],
    skip_special_tokens=True
)

print("\nAI reconstruction:")
print(result)