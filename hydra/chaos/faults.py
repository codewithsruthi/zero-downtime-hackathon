from __future__ import annotations

import json
import random
import re

from hydra.errors import AcquisitionError

FAULTS = {}


def fault(name):
    def deco(fn):
        FAULTS[name] = fn
        return fn

    return deco


@fault("http_403")
def http_403(_payload, _cfg):
    raise AcquisitionError("Forbidden (chaos)", http_status=403, error_type="HTTPError")


@fault("captcha_wall")
def captcha_wall(_payload, _cfg):
    return "<html><body><h1>Verify you are human</h1><div id='captcha'></div></body></html>"


@fault("selector_drift")
def selector_drift(payload, _cfg):
    return re.sub(r'class="(repo|item|row)-', r'class="v2-\1-', payload)


@fault("field_rename")
def field_rename(payload, cfg):
    data = json.loads(payload)
    old, new = cfg.get("from", "price"), cfg.get("to", "current_price")
    records = data if isinstance(data, list) else [data]
    for rec in records:
        if old in rec:
            rec[new] = rec.pop(old)
    return json.dumps(data)


@fault("type_change")
def type_change(payload, cfg):
    data = json.loads(payload)
    field = cfg.get("field", "stars")
    records = data if isinstance(data, list) else [data]
    for rec in records:
        if field in rec and rec[field] is not None:
            rec[field] = str(rec[field])
    return json.dumps(data)


@fault("null_flood")
def null_flood(payload, cfg):
    field, rate = cfg.get("field"), cfg.get("rate", 0.6)
    rng = random.Random(cfg.get("seed", 42))
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        lines = payload.splitlines()
        if not lines:
            return payload
        header = lines[0].split(",")
        if field not in header:
            return payload
        idx = header.index(field)
        out = [lines[0]]
        for line in lines[1:]:
            cols = line.split(",")
            if len(cols) > idx and rng.random() < rate:
                cols[idx] = ""
            out.append(",".join(cols))
        return "\n".join(out)
    for rec in data:
        if rng.random() < rate:
            rec[field] = None
    return json.dumps(data)


@fault("volume_collapse")
def volume_collapse(payload, cfg):
    keep = cfg.get("keep", 3)
    try:
        data = json.loads(payload)
        return json.dumps(data[:keep])
    except json.JSONDecodeError:
        lines = payload.splitlines()
        if not lines:
            return payload
        return "\n".join(lines[: keep + 1])


@fault("poison_record")
def poison_record(payload, cfg):
    idx = cfg.get("at", 4)
    marker = cfg.get("marker", "__POISON__")
    if payload.lstrip().startswith("{") or payload.lstrip().startswith("["):
        data = json.loads(payload)
        if isinstance(data, list) and len(data) > idx:
            data[idx]["_poison"] = marker
            data[idx]["_invalid_utf8"] = True
        return json.dumps(data)
    lines = payload.split("\n")
    if len(lines) > idx:
        lines[idx] = lines[idx] + marker
    return "\n".join(lines)
