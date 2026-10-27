import onnxruntime as ort

from app.core.config import get_settings


def session_options() -> ort.SessionOptions:
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    opts.intra_op_num_threads = get_settings().ORT_INTRA_THREADS
    opts.inter_op_num_threads = 1
    opts.add_session_config_entry("session.intra_op.allow_spinning", "0")
    return opts
