"""Three ways to run the same prompt bytes greedily: transformers, llama.cpp, ExecuTorch.

Each engine takes token ids (the prompt is rendered once, by the reference's own chat template,
and every engine tokenises that same string) and returns the generated ids plus, at every step,
the probability of the call-opening token. Imports are lazy so a GGUF-only user never needs
torch's ExecuTorch wheel and vice versa.
"""


def _greedy(start, step, ids, max_new, stop_ids, call_id):
    """Shared loop for engines that expose logits one step at a time."""
    import numpy as np
    logits = np.asarray(start(ids), dtype=np.float64)
    out, p = [], []
    for _ in range(max_new):
        e = np.exp(logits - logits.max())
        p.append(float(e[call_id] / e.sum()) if call_id is not None else None)
        tok = int(logits.argmax())
        out.append(tok)
        if tok in stop_ids:
            break
        logits = np.asarray(step(tok, len(ids) + len(out) - 1), dtype=np.float64)
    return out, p


class HF:
    """The unquantised reference, through transformers, in float32 unless told otherwise."""

    def __init__(self, repo, tokenizer, device="auto", dtype="float32"):
        import torch
        from transformers import AutoModelForCausalLM
        self.torch = torch
        if device == "auto":
            device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.tok = tokenizer
        self.model = AutoModelForCausalLM.from_pretrained(repo, dtype=getattr(torch, dtype)).to(device).eval()

    def tokenize(self, text):
        return self.tok(text, add_special_tokens=False).input_ids

    def token_id(self, s):
        ids = self.tok.convert_tokens_to_ids([s])
        return ids[0] if ids and ids[0] != self.tok.unk_token_id else None

    def decode(self, ids):
        return self.tok.decode(ids, skip_special_tokens=False)

    def generate(self, ids, max_new, stop_ids, call_id):
        t = self.torch
        with t.no_grad():
            g = self.model.generate(
                t.tensor([ids], device=self.device), attention_mask=t.ones(1, len(ids), dtype=t.long, device=self.device),
                max_new_tokens=max_new, do_sample=False, num_beams=1, repetition_penalty=1.0,
                temperature=None, top_p=None, top_k=None, eos_token_id=sorted(stop_ids),
                pad_token_id=next(iter(stop_ids)), output_logits=True, return_dict_in_generate=True)
        out = g.sequences[0, len(ids):].tolist()
        p = [t.softmax(l[0].float(), -1)[call_id].item() if call_id is not None else None for l in g.logits]
        return out, p


class GGUF:
    """A .gguf through llama-cpp-python, every layer on the GPU when there is one."""

    def __init__(self, path, n_ctx=4096):
        from llama_cpp import Llama
        self.llm = Llama(model_path=path, n_ctx=n_ctx, n_gpu_layers=-1, logits_all=False, verbose=False, seed=0)

    def tokenize(self, text):
        return self.llm.tokenize(text.encode(), add_bos=False, special=True)

    def token_id(self, s):
        ids = self.tokenize(s)
        return ids[0] if len(ids) == 1 else None

    def decode(self, ids):
        return self.llm.detokenize(ids, special=True).decode("utf-8", errors="replace")

    def generate(self, ids, max_new, stop_ids, call_id):
        import numpy as np
        llm = self.llm
        # Without logits_all the wrapper keeps no logits, so read the context's last row directly.
        last = lambda: np.ctypeslib.as_array(llm._ctx.get_logits_ith(-1), shape=(llm.n_vocab(),)).copy()

        def start(ids):
            llm.reset()
            llm.eval(ids)
            return last()

        def step(tok, _pos):
            llm.eval([tok])
            return last()

        return _greedy(start, step, ids, max_new, stop_ids, call_id)


class PTE:
    """A compiled ExecuTorch .pte (export_llm layout: forward(tokens, input_pos) -> logits)."""

    def __init__(self, path, tokenizer_json):
        import torch
        # export_llm files use the LLM custom ops (KV cache update, SDPA) and quantised embedding
        # kernels; importing these registers them with the runtime before the method loads.
        import executorch.extension.llm.custom_ops.custom_ops  # noqa: F401
        import executorch.kernels.quantized  # noqa: F401
        from executorch.runtime import Runtime
        from tokenizers import Tokenizer
        self.torch = torch
        self.program = Runtime.get().load_program(path)
        self.tok = Tokenizer.from_file(tokenizer_json)
        # export_llm stores its limits as constant methods; a static-shape export takes one token.
        meta = lambda name, default: self.program.load_method(name).execute([])[0] if name in self.program.method_names else default
        self.chunk = int(meta("get_max_seq_len", 1)) if bool(meta("enable_dynamic_shape", False)) else 1

    def tokenize(self, text):
        return self.tok.encode(text, add_special_tokens=False).ids

    def token_id(self, s):
        return self.tok.token_to_id(s)

    def decode(self, ids):
        return self.tok.decode(ids, skip_special_tokens=False)

    def generate(self, ids, max_new, stop_ids, call_id):
        t = self.torch
        # A fresh method per row: KV and conv state live in the method's buffers, and a runner
        # that carries them from one prompt to the next was one of the two causes the OpenWeights
        # study found behind the lost calls.
        method = self.program.load_method("forward")

        def run(tokens, pos):
            out = method.execute([t.tensor([tokens], dtype=t.long), t.tensor([pos], dtype=t.long)])[0]
            return out.reshape(-1, out.shape[-1])[-1].float().numpy()

        def start(ids):
            for i in range(0, len(ids), self.chunk):
                last = run(ids[i:i + self.chunk], i)
            return last

        return _greedy(start, lambda tok, pos: run([tok], pos), ids, max_new, stop_ids, call_id)
