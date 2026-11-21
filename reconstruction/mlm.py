"""ONNX backend for the RoBERTa engine, using Android's ONNX Runtime (Java) via pyjnius.

logits_at(rows), where rows = [(token_ids, positions), ...], returns one float32
array per row with shape (len(positions), vocab_size).

init() MUST run on the main thread (see Bingo.on_start) so the Java classes are
loaded there. The worker thread can only find classes already loaded."""
import os

import numpy as np


class BackendUnavailable(RuntimeError):
    pass


_J = {}

_NAMES = {
    "Env": "ai.onnxruntime.OrtEnvironment",
    "Session": "ai.onnxruntime.OrtSession",
    "Options": "ai.onnxruntime.OrtSession$SessionOptions",
    "Result": "ai.onnxruntime.OrtSession$Result",
    "Value": "ai.onnxruntime.OnnxValue",
    "Tensor": "ai.onnxruntime.OnnxTensor",
    "ByteBuffer": "java.nio.ByteBuffer",
    "ByteOrder": "java.nio.ByteOrder",
    "HashMap": "java.util.HashMap",
}


def init():
    if _J:
        return
    from jnius import autoclass
    for key, name in _NAMES.items():
        _J[key] = autoclass(name)


def _to_bytes(raw):
    try:
        return bytes(raw)
    except Exception:
        return np.array(list(raw), dtype=np.int8).tobytes()


class OnnxBackend:
    def __init__(self, model_path, pad_id=1, threads=4):
        if not os.path.exists(model_path):
            raise BackendUnavailable("no ONNX model at " + model_path)
        try:
            init()
        except Exception as e:
            raise BackendUnavailable("onnxruntime-android classes not found: %s" % e) from e
        self.pad_id = pad_id
        self.name = "onnxruntime-android:" + os.path.basename(model_path)
        self.env = _J["Env"].getEnvironment()
        opts = _J["Options"]()
        opts.setIntraOpNumThreads(threads)
        self.sess = self.env.createSession(model_path, opts)

    def _long_tensor(self, arr):
        BB, BO = _J["ByteBuffer"], _J["ByteOrder"]
        data = np.ascontiguousarray(arr, dtype=np.int64).tobytes()
        bb = BB.allocateDirect(len(data)).order(BO.nativeOrder())
        try:
            bb.put(data)
        except Exception:
            bb.put(list(np.frombuffer(data, dtype=np.int8)))
        bb.rewind()
        return _J["Tensor"].createTensor(self.env, bb.asLongBuffer(),
                                         [int(x) for x in arr.shape])

    def _run_one(self, ids, pos):
        from jnius import cast
        ids_a = np.array([ids], dtype=np.int64)
        att_a = np.ones_like(ids_a)
        pos_a = np.array([pos], dtype=np.int64)
        tensors = [self._long_tensor(ids_a), self._long_tensor(att_a),
                   self._long_tensor(pos_a)]
        feeds = _J["HashMap"]()
        for name, t in zip(("input_ids", "attention_mask", "positions"), tensors):
            feeds.put(name, t)
        result = self.sess.run(feeds)
        try:
            out = cast("ai.onnxruntime.OnnxTensor", result.get(0))
            fb = out.getByteBuffer()
            fb.rewind()
            heap = _J["ByteBuffer"].allocate(fb.remaining())
            heap.put(fb)
            raw = _to_bytes(heap.array())
            flat = np.frombuffer(raw, dtype=np.float32).copy()
        finally:
            result.close()
            for t in tensors:
                t.close()
        return flat.reshape(len(pos), -1)

    def logits_at(self, rows):
        return [self._run_one(list(ids), list(pos)) for ids, pos in rows]